"""Experiment-only outcome accounting; no semantic parser or model-facing policy."""
from typing import Literal

Decision = Literal['supported', 'invalid', 'unsupported']


def classify(expected_valid: bool, decision: Decision | None, *,
             failure: Literal['contract', 'task', 'evaluator'] | None = None) -> str:
    """A missing/invalid response is never a successful semantic rejection.

    This scores the declared decision against a reviewed fixture label. Whether a cited
    explanation correctly establishes the defect is an independent review dimension.
    """
    if failure is not None:
        return {'contract': 'contract_failure', 'task': 'task_failure', 'evaluator': 'evaluator_defect'}[failure]
    if decision is None:
        return 'missing_decision'
    if decision == 'unsupported':
        return 'abstention_on_valid' if expected_valid else 'abstention_on_invalid'
    if decision == 'supported':
        return 'correct_approval' if expected_valid else 'dangerous_false_approval'
    if decision == 'invalid':
        return 'false_rejection' if expected_valid else 'correct_rejection'
    raise ValueError('unknown review decision')


def structured_decision(review) -> Decision | None:
    """Project current structured facts onto the experiment rubric, without rescoring raw reports.

    Explicit defects take precedence over unresolved checks. Missing preconditions are
    epistemic here: the schema does not distinguish an absent fixture from absent proof
    of its establishment. Missing reviews remain missing, never an invalid decision.
    Historical blanket booleans cannot supply the per-probe distinctions this needs.
    """
    from corsair.agents.evidence_assessment.contracts import ValidityReview

    if review is None:
        return None
    if not isinstance(review, ValidityReview):
        raise ValueError('shared rubric projection requires a current structured validity review')
    unresolved = False
    for role, probe in (('control', review.control), ('exploit', review.exploit)):
        expected_input = 'benign' if role == 'control' else 'reported_adversarial'
        expected_assertion = 'benign_behavior' if role == 'control' else 'security_property'
        binding, supplied, assertion, dependencies = (
            probe.production_binding.status, probe.input_exercise.status,
            probe.assertion.status, probe.dependencies.scope)
        if (binding in ('copied', 'replaced')
                or supplied not in (expected_input, 'unknown')
                or assertion not in (expected_assertion, 'unknown')
                or dependencies in ('entry_point_replaced', 'security_logic_replaced')):
            return 'invalid'
        unresolved |= ('unknown' in (binding, supplied, assertion, dependencies)
                       or probe.input_exercise.preconditions != 'established')
    return 'unsupported' if unresolved else 'supported'
