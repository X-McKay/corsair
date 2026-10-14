"""Frozen experiment rules and native sensitivity checks, never model-authored execution."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from evals.experiments.probe_validation.calibration import calibrate
from evals.experiments.probe_validation.scoring import classify

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / 'evals/experiments/probe_validation'


def test_experiment_rubric_and_before_inputs_stay_frozen():
    path = EXPERIMENT / 'rubric-v1.json'
    assert sha256(path.read_bytes()).hexdigest() == path.with_suffix('.sha256').read_text().strip()
    rubric = json.loads(path.read_text())
    from evals.cases import load_set
    # The frozen rubric names the single files these sets were moved from; each now lives as a per-case set.
    moved = {'evals/evidence_assessment/unit_test_cases_v2.json': 'unit',
             'evals/evidence_assessment/unit_transfer_cases_v2.json': 'unit-transfer'}
    for group in rubric['validity_sets'].values():
        cases = load_set('evidence_assessment', moved[group['source']])
        assert {case.name: sha256(json.dumps(case.input, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                for case in cases} == group['inputs']
        assert {case.name: all(case.oracle['expected'].values()) for case in cases} == group['expected_valid']


@pytest.mark.parametrize('expected,decision,result', [
    (True, 'supported', 'correct_approval'), (False, 'supported', 'dangerous_false_approval'),
    (True, 'invalid', 'false_rejection'), (False, 'invalid', 'correct_rejection'),
    (True, 'unsupported', 'abstention_on_valid'), (False, 'unsupported', 'abstention_on_invalid'),
    (True, None, 'missing_decision'),
])
def test_experiment_decisions_keep_abstention_separate(expected, decision, result):
    assert classify(expected, decision) == result


@pytest.mark.parametrize('failure,result', [('contract', 'contract_failure'), ('task', 'task_failure'),
                                          ('evaluator', 'evaluator_defect')])
def test_failed_attempt_is_never_a_correct_semantic_rejection(failure, result):
    assert classify(False, 'invalid', failure=failure) == result


def test_native_calibration_exposes_copied_and_vacuous_pairs(tmp_path):
    report = calibrate(tmp_path / 'calibration')
    assert report['pairs']['meaningful']['security_distinguishes']
    assert not report['pairs']['copied']['security_distinguishes']
    assert not report['pairs']['vacuous']['security_distinguishes']
    for pair in report['pairs'].values():
        assert pair['control_healthy']
        assert {run['patch_sha256'] for run in pair['runs'].values()} == {pair['patch_sha256']}
        for run in pair['runs'].values():
            assert len(run['outcomes']) == 2
            assert all(outcome['outcome'] in ('passed', 'failed') for outcome in run['outcomes'])
    unsafe = report['pairs']['meaningful']['runs']['unsafe']['outcomes'][1]
    assert unsafe['failure']['type'] == 'AssertionError'
    assert unsafe['failure']['function'] == 'test_security_preserves_query_structure'


def structured_review():
    from corsair.agents.evidence_assessment.contracts import ValidityReview, EvidenceReference
    from evals.cases import load_set
    case = load_set('evidence_assessment', 'unit')[0]
    return ValidityReview[EvidenceReference].model_validate(case.oracle['scripted_review'])


def test_shared_projection_distinguishes_known_defect_from_uncertainty():
    from evals.experiments.probe_validation.scoring import structured_decision
    review = structured_review()
    assert structured_decision(review) == 'supported'
    unknown = review.exploit.model_copy(update={'production_binding': review.exploit.production_binding.model_copy(
        update={'status': 'unknown', 'definition_site': None})})
    assert structured_decision(review.model_copy(update={'exploit': unknown})) == 'unsupported'
    defect = review.control.model_copy(update={'assertion': review.control.assertion.model_copy(update={'status': 'vacuous'})})
    assert structured_decision(review.model_copy(update={'control': defect, 'exploit': unknown})) == 'invalid'
    # Precedence is independent of role ordering: unknown control, known exploit defect.
    unknown_control = review.control.model_copy(update={'production_binding': review.control.production_binding.model_copy(
        update={'status': 'unknown', 'definition_site': None})})
    bad_exploit = review.exploit.model_copy(update={'input_exercise': review.exploit.input_exercise.model_copy(update={'status': 'different'})})
    assert structured_decision(review.model_copy(update={'control': unknown_control, 'exploit': bad_exploit})) == 'invalid'


@pytest.mark.parametrize('preconditions', ['missing', 'unknown'])
def test_missing_precondition_evidence_is_abstention_not_a_semantic_defect(preconditions):
    from evals.experiments.probe_validation.scoring import structured_decision
    review = structured_review()
    probe = review.exploit.model_copy(update={'input_exercise': review.exploit.input_exercise.model_copy(
        update={'preconditions': preconditions})})
    assert structured_decision(review.model_copy(update={'exploit': probe})) == 'unsupported'


def test_missing_review_and_historical_boolean_review_are_not_projected_as_approval():
    from evals.experiments.probe_validation.scoring import structured_decision
    assert structured_decision(None) is None
    with pytest.raises(ValueError, match='current structured'):
        structured_decision({'source_linked': True, 'condition_exercised': True,
                             'assertions_relevant': True, 'dependency_scope_valid': True})
