"""Native eval-only review plumbing: provenance, abstention, citations and frozen binding."""
import json
from hashlib import sha256

import pytest
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from corsair.agents.evidence_assessment.contracts import ValidityInput
from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
from evals.evidence_assessment.challenge import challenge_prompt, create_challenge_agent
from evals.evidence_assessment.unit_test import dataset


def inputs():
    return next(case.inputs for case in dataset().cases if case.name == 'real-seam-return-and-exception')


def cite(item_id, start=1, end=1):
    return {'item_id': item_id, 'start_line': start, 'end_line': end}


def observation(statement, *ids):
    return {'statement': statement, 'citations': [cite(item) for item in ids]}


def draft(decision='supported'):
    def probe(role):
        return {'binding': observation('Read the actual production import, call and definition', 'patch', 'baseline-source'),
            'input': observation('Actual benign argument' if role == 'control' else 'Actual reported adversarial argument',
                                 'patch', 'test-plan', 'reported-condition'),
            'assertion': observation('Actual pass condition establishes the scoped property',
                                     'patch', 'test-plan', 'reported-condition')}
    return {'reviews': [{'revision': 'baseline', 'control': probe('control'), 'exploit': probe('exploit'),
        'challenge': observation('Checked actual binding and pass conditions; no counterexample found within this captured scope',
                                 'patch', 'baseline-source'),
        'defects': [observation('Concrete test-local entry point bypasses production', 'patch')] if decision == 'invalid' else [],
        'unsupported': ['Actual target definition unavailable'] if decision == 'unsupported' else [],
        'decision': decision}]}


def scripted(output, *, omit=()):
    data = inputs()
    async def respond(messages, info):
        reads = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
                 and p.tool_name == 'read_evidence']
        for item in data.items:
            if item.item_id in omit:
                continue
            end = max((read.end_line for read in reads if read.item_id == item.item_id), default=0)
            if end < len(item.content.splitlines()):
                return ModelResponse(parts=[ToolCallPart('read_evidence', {'item_id': item.item_id, 'start_line': end + 1})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
    return FunctionModel(respond)


def run(output, data=None, **script_kwargs):
    data = data or inputs()
    with models.override_allow_model_requests(False):
        return create_challenge_agent(scripted(output, **script_kwargs), output_retries=0).run_sync(
            challenge_prompt(data), deps=AssessmentDependencies(data),
            usage_limits=UsageLimits(request_limit=20, tool_calls_limit=18)).output


@pytest.mark.parametrize('decision', ['supported', 'invalid', 'unsupported'])
def test_challenge_decisions_are_bound_to_exact_frozen_inputs(decision):
    data = inputs()
    result = run(draft(decision), data)
    review = result.reviews[0]
    assert review.decision == decision
    assert review.source_sha256 == data.revision_sources['baseline']
    assert review.observation_plan_sha256 == data.plan.review_digest
    retained = review.model_dump(exclude={'artifact_sha256', 'observation_plan_sha256', 'source_sha256'})
    assert review.artifact_sha256 == sha256(json.dumps(retained, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert review.control.binding.citations[0].quote
    assert review.exploit.input.citations[0].quote


def test_unsupported_is_not_a_supported_semantic_approval():
    result = run(draft('unsupported'))
    assert result.reviews[0].unsupported
    assert not result.reviews[0].defects
    assert result.reviews[0].decision != 'supported'


@pytest.mark.parametrize('change', ['supported-defect', 'invalid-no-defect', 'unsupported-no-gap'])
def test_challenge_cannot_approve_defects_or_make_ungrounded_decisions(change):
    output = draft()
    review = output['reviews'][0]
    if change == 'supported-defect':
        review['defects'] = [observation('A real copied-target defect', 'patch')]
    elif change == 'invalid-no-defect':
        review['decision'] = 'invalid'
    else:
        review['decision'] = 'unsupported'
    with pytest.raises(UnexpectedModelBehavior):
        run(output)


@pytest.mark.parametrize('item_id', ['patch', 'test-plan', 'reported-condition', 'baseline-source'])
def test_challenge_requires_current_run_evidence_reads(item_id):
    with pytest.raises(UnexpectedModelBehavior):
        run(draft(), omit=(item_id,))


def test_challenge_cannot_borrow_untrusted_source_identity():
    data = inputs()
    changed = data.model_copy(update={'items': tuple(
        item.model_copy(update={'source_sha256': '0' * 64}) if item.kind == 'source' else item for item in data.items)})
    with pytest.raises(UnexpectedModelBehavior):
        run(draft(), changed)


def test_challenge_output_and_prompt_do_not_expose_oracle_labels_or_runtime_results():
    data = inputs()
    assert isinstance(data, ValidityInput)
    prompt = challenge_prompt(data)
    assert all(marker not in prompt for marker in ('expected_valid', 'scripted_review', 'real-seam-return-and-exception'))
    result = run(draft())
    assert not hasattr(result, 'gate_result') and not hasattr(result, 'evidence')


def test_challenge_context_citations_need_not_repeat_in_every_probe_fact():
    output = draft()
    review = output['reviews'][0]
    for role in ('control', 'exploit'):
        for field in ('input', 'assertion'):
            review[role][field]['citations'] = [cite('patch')]
    review['challenge']['citations'] += [cite('test-plan'), cite('reported-condition')]
    assert run(output).reviews[0].decision == 'supported'


@pytest.mark.parametrize('variant,cases,count', [('challenge', 'unit', 7), ('challenge', 'transfer', 3), ('current', 'transfer', 3)])
def test_comparison_cli_evaluator_preserves_frozen_inputs_and_records_separate_dimensions(tmp_path, variant, cases, count):
    import asyncio
    from evals.evidence_assessment.challenge import evaluate
    destination = tmp_path / f'{variant}-{cases}'
    assert asyncio.run(evaluate(destination, variant=variant, cases=cases, repeat=1))
    configuration = json.loads((destination / 'configuration.json').read_text())
    report = json.loads((destination / 'report.json').read_text())
    outcomes = json.loads((destination / 'outcomes.json').read_text())
    assert len(configuration['input_hashes']) == count
    assert configuration['max_concurrency'] == 1 and configuration['task_retries'] == 0
    assert configuration['budget']['task_seconds'] == 1200
    assert configuration['rationale_adequacy'] == 'unqualified_requires_independent_review'
    assert outcomes['attempts'] == count and not report['failures']
    assert all(case['assertions']['read_grounding']['value'] for case in report['cases'])
    assert all(case['labels']['rationale_adequacy']['value'] == 'not_independently_reviewed' for case in report['cases'])
    assert len(list(destination.glob('attempt-*.json'))) == count
