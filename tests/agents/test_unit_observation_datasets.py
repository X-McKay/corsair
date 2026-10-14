"""Frozen native unit cases exercise agents without a mandatory effect recorder."""
import asyncio
from pathlib import Path

import pytest

from evals.fixture_e2e.case import BASELINE_TEST, CASES, FIXTURE, fixture_case
from evals.test_authoring.evaluate import EvaluationBudget as AuthoringBudget
from evals.test_authoring.evaluate import dataset as authoring_dataset, evaluate as authoring_evaluate, passed as authoring_passed
from evals.test_planning.evaluate import EvaluationBudget as PlanningBudget
from evals.test_planning.evaluate import check_manifest, dataset as planning_dataset, evaluate as planning_evaluate, passed as planning_passed


@pytest.mark.parametrize('name', CASES)
def test_fixture_captures_both_revision_sources(name):
    case = fixture_case(name)
    assert set(case.review_sources) == {'baseline', 'candidate'}
    for revision, captured in case.review_sources.items():
        assert captured.source_sha256 == case.revision_sources[revision]
        assert {file.path: file.content for file in captured.files} == {
            'documents.py': (FIXTURE / CASES[name][revision] / 'documents.py').read_text(),
            'test_existing.py': BASELINE_TEST,
        }


def test_frozen_unit_cases_have_no_low_level_recorder():
    check_manifest('unit')
    planning, authoring = planning_dataset('unit'), authoring_dataset('unit')
    assert {case.name for case in planning.cases} == {case.name for case in authoring.cases}
    for case in authoring.cases:
        inputs = case.inputs.inputs
        assert not inputs.environment.witness_facilities
        assert inputs.plan.control.observation.kind == inputs.plan.security.observation.kind == 'dependency_call'
        assert inputs.plan.control.witness is inputs.plan.security.witness is None


def test_unit_planning_and_authoring_frozen_scripted_cases(tmp_path: Path):
    # The authoring runner is an injected port. Native fixture execution is covered separately.
    planning = asyncio.run(planning_evaluate(tmp_path / 'planning', PlanningBudget(repeat=1), cases='unit'))
    authoring = asyncio.run(authoring_evaluate(tmp_path / 'authoring', AuthoringBudget(repeat=1), cases='unit'))
    assert planning_passed(planning) and len(planning.cases) == 2
    assert authoring_passed(authoring) and len(authoring.cases) == 2


def test_native_assertion_facts_survive_environment_handoff():
    from corsair.agents.environment.frameworks import FRAMEWORKS
    from corsair.agents.test_authoring.prompts import authoring_prompt

    case = fixture_case()
    assert FRAMEWORKS['pytest'].assertion_facts[0] in case.environment.assertion_facts
    author = authoring_dataset('unit').cases[0].inputs.inputs
    for framework in ('pytest', 'minitest'):
        # Renderer has no language branch: admitted operator facts travel in existing environment data.
        environment = author.environment.model_copy(update={
            'framework': framework, 'assertion_facts': FRAMEWORKS[framework].assertion_facts})
        rendered = authoring_prompt(author.model_copy(update={'environment': environment}))
        assert FRAMEWORKS[framework].assertion_facts[0] in rendered


def test_unit_authoring_eval_accepts_native_dependency_mock(monkeypatch):
    from evals.test_authoring.evaluate import FILES, ScriptedRun, ScriptedRunner, authoring_checks, scripted_model
    from corsair.agents.test_authoring.agent import create_test_authoring_agent
    from corsair.agents.test_authoring.dependencies import AuthoringDependencies
    from corsair.agents.test_authoring.prompts import authoring_prompt

    case = authoring_dataset('unit').cases[0]
    text = FILES['sql_unit'].replace('from queries import lookup_account',
        'from unittest.mock import Mock\nfrom queries import lookup_account')
    text = text.replace('database = RecordingDatabase()', 'database = Mock(wraps=RecordingDatabase()); database.calls = database._mock_wraps.calls')
    monkeypatch.setitem(FILES, 'sql_unit', text)
    oracle = case.metadata.model_copy(update={'security_assertion_lines': (28,)})
    inputs = case.inputs.inputs
    agent = create_test_authoring_agent(scripted_model(inputs, oracle))
    result = agent.run_sync(authoring_prompt(inputs), deps=AuthoringDependencies(inputs, ScriptedRunner((ScriptedRun(status="discovered"),))))
    assert all(authoring_checks(inputs, result.output, oracle).values())


@pytest.mark.parametrize('attack', ["alice' OR 2=2 --", "alice' OR '1'='1", 'account "alice\' OR \'x\'=\'x\' --"'])
def test_versioned_plan_oracle_accepts_equivalent_reviewed_condition(attack):
    from evals.test_planning.evaluate import plan_checks
    case = planning_dataset('unit-v2').cases[0]
    plan = authoring_dataset('unit').cases[0].inputs.inputs.plan
    plan = plan.model_copy(update={'security': plan.security.model_copy(update={'input': attack})})
    assert plan_checks(case.inputs, plan, case.metadata)['adversarial_input']
    # Historical v1 criterion is preserved, never retroactively rescored as a success.
    original = planning_dataset('unit').cases[0]
    assert not plan_checks(original.inputs, plan, original.metadata)['adversarial_input']


@pytest.mark.parametrize('input_text', ['ordinary alice', 'OR 1=2', "OR 'x'='y'", 'OR anything', 'Alice OR 1=1', "alice' OR 1=2 --", "alice' OR 'x'='y"])
def test_versioned_condition_patterns_do_not_accept_arbitrary_text(input_text):
    from evals.test_planning.evaluate import plan_checks
    case = planning_dataset('unit-v2').cases[0]
    plan = authoring_dataset('unit').cases[0].inputs.inputs.plan
    plan = plan.model_copy(update={'security': plan.security.model_copy(update={'input': input_text})})
    assert not plan_checks(case.inputs, plan, case.metadata)['adversarial_input']
