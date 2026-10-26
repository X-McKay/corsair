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
    _operation_prefix,
    _retry_feedback,
    _session_outcome,
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


def test_a_component_demonstration_survives_a_later_failure():
    from corsair.contracts import Scope

    prepared = _prepared().model_copy(
        update={
            "finding": _prepared().finding.model_copy(update={"claim_scope": Scope.APPLICATION})
        }
    )
    rounds = [_round(1, _demonstrated(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="later fault")
    verdict = _aggregate_case_verdict(prepared, rounds, result)
    assert verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED


def test_completed_clean_negative_alone_is_inconclusive_at_threshold_two():
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.COMPLETED, reason="completed")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.INCONCLUSIVE


# --- independent sessions: only case_verdict promotes clean negatives ----------


def test_two_independent_clean_negative_sessions_are_exploit_not_demonstrated():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    assert first.clean_negative
    rounds = [_round(1, _clean_negative(), _audit())]
    verdict = _aggregate_case_verdict(_prepared(), rounds, _result(), [first])
    assert verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED


def test_second_session_operational_failure_is_not_a_clean_negative():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="provider unavailable")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result, [first])
    assert verdict is Verdict.ERROR


def test_second_session_that_never_ran_a_round_stays_inconclusive():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    verdict = _aggregate_case_verdict(_prepared(), [], _result(), [first])
    assert verdict is Verdict.INCONCLUSIVE


def test_a_demonstration_in_the_second_session_is_exploit_demonstrated():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    rounds = [_round(1, _demonstrated(), _audit())]
    verdict = _aggregate_case_verdict(_prepared(), rounds, _result(), [first])
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_later_sessions_use_disjoint_operation_ids_with_suffix_headroom():
    root = "r" * 60
    assert _operation_prefix(root, 1) == root
    second = _operation_prefix(root, 2)
    assert second != root and second.startswith(f"{root}.")
    validate_root_identity(root)
    from pydantic import TypeAdapter

    from corsair.contracts.common import Identifier

    TypeAdapter(Identifier).validate_python(f"{second}.fix16")


# --- finding 3: the API/CLI boundary reserves operation-suffix headroom --------


def test_root_identity_rejects_lengths_that_leave_no_suffix_headroom():
    import pytest

    validate_root_identity("r" * 60)
    with pytest.raises(ValueError, match="operation suffixes"):
        validate_root_identity("r" * 61)
