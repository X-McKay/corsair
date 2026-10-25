"""Workflow-boundary regression tests: the outcome-blind retry feedback and the
canonical verdict's handling of a later terminal operational failure."""

from __future__ import annotations

from corsair.contracts import (
    AuditDecision,
    ExecutionStatus,
    FixStatus,
    InvestigationResult,
    RoundResult,
    Verdict,
    validate_root_identity,
)
from corsair.workflows.investigation import (
    _BLIND_RETRY_REASON,
    _aggregate_case_verdict,
    _retry_feedback,
)
from tests.unit.test_evidence import _audit, _prepared
from tests.unit.test_verdicts import _clean_negative, _demonstrated

_DECISION_OUTCOME_REASON = "no reproducible secret-disclosure demonstration was observed"


def _result(**updates) -> InvestigationResult:
    base = InvestigationResult(
        run_id="run",
        case_id="case",
        disposition="INCONCLUSIVE",
        execution_status=ExecutionStatus.COMPLETED,
        reason="completed",
    )
    return base.model_copy(update=updates)


# --- finding 1: the producer never learns the exploit outcome on retry --------


def test_retry_feedback_never_forwards_the_run_outcome_when_audit_accepts():
    """A completed round the auditor accepted leaves nothing the producer may see:
    the retry carries a fixed, outcome-free instruction, never decide()'s reason."""
    feedback = _retry_feedback(_audit(AuditDecision.ACCEPT))
    assert feedback.reason == _BLIND_RETRY_REASON
    assert "disclosure" not in feedback.reason
    assert _DECISION_OUTCOME_REASON not in feedback.reason


def test_retry_feedback_forwards_only_the_structural_audit_rejection():
    """A rejecting auditor formed its reason without any run result, so that
    structural/semantic reason is the one corrective signal a retry may carry."""
    feedback = _retry_feedback(_audit(AuditDecision.REJECT))
    assert feedback.gate == "audit"
    assert feedback.reason == "reviewed"


# --- finding 2: a later terminal failure is not masked by an earlier round -----


def _round(index: int, observation, audit) -> RoundResult:
    from corsair.contracts import ProducerDecision, ProducerOutput, ProducerProposal
    from tests.unit.test_evidence import _submission

    producer = ProducerOutput(
        decision=ProducerDecision(root=ProducerProposal(submission=_submission()))
    )
    return RoundResult(index=index, producer=producer, observation=observation, audit=audit)


def test_later_operational_failure_overrides_an_earlier_clean_negative():
    """Round 1 is a covered clean negative; round 2 fails operationally. The
    canonical verdict must carry the operational error, not the earlier round."""
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="provider unavailable")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.ERROR


def test_a_confirmed_demonstration_survives_a_later_failure():
    """A positively demonstrated exploit is a fact; a later failure does not erase it."""
    rounds = [_round(1, _demonstrated(), _audit())]
    result = _result(
        execution_status=ExecutionStatus.ERROR,
        reason="later fault",
        fix_status=FixStatus.DEMONSTRATION_BLOCKED,
    )
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_completed_clean_negative_alone_is_inconclusive_at_threshold_two():
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.COMPLETED, reason="completed")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.INCONCLUSIVE


# --- finding 3: the API/CLI boundary reserves operation-suffix headroom --------


def test_root_identity_rejects_lengths_that_leave_no_suffix_headroom():
    import pytest

    validate_root_identity("r" * 60)
    with pytest.raises(ValueError, match="operation suffixes"):
        validate_root_identity("r" * 61)
