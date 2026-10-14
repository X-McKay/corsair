"""Matched input preservation, SDK budget accounting and draft-only pilot receipts."""
import asyncio
from dataclasses import replace
import json

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from evals.experiments.split_authoring.cases import load_cases
from evals.experiments.split_authoring.contracts import DraftingInput
from evals.experiments.split_authoring.evaluate import Budget, evaluate, run_arm


def test_matched_pilot_preserves_original_sources_and_property():
    import yaml
    from pathlib import Path
    original = yaml.safe_load(Path('evals/test_authoring/cases-unit.yaml').read_text())['cases']
    for frozen, old in zip(load_cases(), original, strict=True):
        base = frozen['inputs']
        old = old['inputs']['inputs']
        assert base['source_files'] == old['source_files']
        assert base['property_plan']['control_input'] == old['plan']['control']['input']
        assert base['property_plan']['adversarial_input'] == old['plan']['security']['input']
        assert base['property_plan']['citations'] == old['plan']['citations']
        assert base['control_test_path'] != base['exploit_test_path']
        for role in ('pair', 'control'):
            value = DraftingInput(role=role, **base)
            assert 'expected_output' not in value.model_dump_json()
            assert 'fixture_id' not in value.model_dump_json()


def test_native_scripted_matched_arms_retain_frozen_control_and_pending_validity(tmp_path):
    report = asyncio.run(evaluate(tmp_path / 'run'))
    assert len(report['attempts']) == report['draft_completed'] == 4
    assert report['valid_pairs'] is None
    for case in load_cases():
        pair = json.loads((tmp_path / 'run' / case['name'] / '0/pair/receipt.json').read_text())
        split = json.loads((tmp_path / 'run' / case['name'] / '0/split/receipt.json').read_text())
        assert pair['base_input_sha256'] == split['base_input_sha256']
        assert pair['patch_sha256'] == split['patch_sha256']
        assert len(pair['files']) == len(split['files']) == 2
        assert pair['usage']['requests'] == 3
        assert split['usage']['requests'] == 6
        assert split['stages'][1]['usage_before'] == split['stages'][0]['usage_cumulative']
        assert split['stages'][1]['input']['frozen_control'] == split['stages'][0]['output']['files']
        assert split['valid_pair'] is None
        for stage in split['stages']:
            assert len(stage['source_sha256']) == len(stage['draft_schema_sha256']) == 64
            assert stage['messages'] and stage['prompt']
            assert stage['failure'] is None


def test_split_budget_is_cumulative_across_native_calls():
    receipt = asyncio.run(run_arm(load_cases()[0]['inputs'], 'split', budget=replace(Budget(), request_limit=4)))
    assert not receipt['draft_completed']
    assert len(receipt['stages']) == 2
    assert receipt['stages'][0]['failure'] is None
    assert receipt['stages'][1]['failure']['type'] == 'UsageLimitExceeded'
    assert receipt['usage']['requests'] == 4
    assert receipt['files'] == []


def test_blocked_control_never_starts_exploit():
    roles = []
    def model_factory(inputs):
        roles.append(inputs.role)
        def respond(messages, info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                {'draft': {'status': 'blocked', 'layer': 'source', 'reason': 'No supported source seam'}})])
        return FunctionModel(respond)
    receipt = asyncio.run(run_arm(load_cases()[0]['inputs'], 'split', model_factory=model_factory))
    assert roles == ['control']
    assert len(receipt['stages']) == 1
    assert not receipt['draft_completed']
    assert receipt['stages'][0]['output']['status'] == 'blocked'


def test_deadline_failure_never_starts_exploit():
    receipt = asyncio.run(run_arm(load_cases()[0]['inputs'], 'split', budget=replace(Budget(), task_seconds=0)))
    assert not receipt['draft_completed']
    assert len(receipt['stages']) == 1
    assert receipt['stages'][0]['failure']['type'] == 'TimeoutError'
    assert receipt['usage']['requests'] == 0


def test_split_tool_budget_is_not_reset_for_exploit():
    receipt = asyncio.run(run_arm(load_cases()[0]['inputs'], 'split', budget=replace(Budget(), tool_calls_limit=4)))
    assert not receipt['draft_completed']
    assert receipt['stages'][0]['failure'] is None
    assert receipt['stages'][1]['failure']['type'] == 'UsageLimitExceeded'
    assert receipt['usage']['tool_calls'] <= 4


def test_large_admitted_control_keeps_handoff_failure_and_later_attempts(tmp_path, monkeypatch):
    from evals.experiments.split_authoring import evaluate as harness
    original = harness.scripted_model
    def select(inputs):
        if inputs.role != 'control' or " + account + " not in inputs.source_files[0].content:
            return original(inputs)
        step = 0
        def respond(messages, info):
            nonlocal step
            step += 1
            if step == 1:
                return ModelResponse(parts=[ToolCallPart('write_test_file',
                    {'path': inputs.control_test_path, 'content': '# ' + 'x' * 20000})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                {'draft': {'status': 'drafted', 'limitations': ['Independent review pending']}})])
        return FunctionModel(respond)
    monkeypatch.setattr(harness, 'scripted_model', select)
    report = asyncio.run(harness.evaluate(tmp_path / 'run'))
    assert len(report['attempts']) == 4
    assert report['draft_completed'] == 3
    failed = next(item for item in report['attempts'] if item['failure_classification'])
    assert failed['failure_classification'] == 'handoff_admission'
    receipt = json.loads((tmp_path / 'run' / failed['receipt']).read_text())
    assert receipt['stages'][0]['output']['status'] == 'drafted'
    assert len(receipt['stages'][0]['output']['files'][0]['content']) > 16384
    handoff = receipt['stages'][1]
    assert handoff['role'] == 'exploit'
    assert handoff['messages'] == [] and handoff['prompt'] is None
    assert handoff['usage_before'] == handoff['usage_cumulative'] == receipt['usage']
    assert receipt['valid_pair'] is None and not receipt['draft_completed']
    assert report['attempts'][-1]['draft_completed']


def test_unknown_variant_is_rejected_without_creating_evidence(tmp_path):
    import pytest
    with pytest.raises(ValueError, match='variant'):
        asyncio.run(run_arm(load_cases()[0]['inputs'], 'unknown'))
    with pytest.raises(ValueError, match='variant'):
        asyncio.run(evaluate(tmp_path / 'run', arm='unknown'))
    assert not (tmp_path / 'run').exists()


def test_tailored_roles_have_distinct_skills_and_joint_gets_equivalent_content():
    from evals.experiments.split_authoring.prompts import role_skills
    control, exploit, joint = [role_skills(role) for role in ("control", "exploit", "pair")]
    assert set(control) == {"draft-control"}
    assert set(exploit) == {"draft-exploit"}
    assert joint == control | exploit
    assert "security fix" in control["draft-control"]
    assert "adversarial" in exploit["draft-exploit"]
    assert all(not role_skills(role, "legacy") for role in ("control", "exploit", "pair"))


def test_version_two_preserves_sources_and_changes_only_shared_property_contract():
    from copy import deepcopy
    for old, new in zip(load_cases(1), load_cases(2), strict=True):
        comparable = deepcopy(new)
        assert new["inputs"]["property_plan"]["security_property"] != old["inputs"]["property_plan"]["security_property"]
        comparable["inputs"]["property_plan"]["security_property"] = old["inputs"]["property_plan"]["security_property"]
        assert comparable == old
