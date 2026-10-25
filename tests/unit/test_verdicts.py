"""Unit tests for the pure canonical-verdict policy layer."""

from __future__ import annotations

import pytest

from corsair.contracts import (
    ArtifactRef,
    AuditDecision,
    Feedback,
    FixStatus,
    Observation,
    RoleObservation,
    RoleOutcome,
    Verdict,
)
from corsair.policies.verdicts import (
    SessionOutcome,
    case_verdict,
    session_verdict,
    status_outcome,
)
from tests.unit.test_evidence import SOURCE_DIGEST, _audit, _prepared

_ARTIFACT = ArtifactRef(sha256="d" * 64, size=0, media_type="application/json")


def _role(outcome: RoleOutcome, lines: list[int], exit_code: int) -> RoleObservation:
    return RoleObservation(
        outcome=outcome,
        target_executed=True,
        covered_lines=lines,
        reason="role",
        native_exit_code=exit_code,
    )


def _observation(
    control: RoleObservation | None,
    adversarial: RoleObservation | None,
    *,
    cleanup: bool = True,
    artifact: ArtifactRef | None = _ARTIFACT,
    feedback: Feedback | None = None,
    source_digest: str = SOURCE_DIGEST,
) -> Observation:
    return Observation(
        operation_id="op",
        source_digest=source_digest,
        submission_digest="c" * 64,
        control=control,
        adversarial=adversarial,
        artifact=artifact,
        cleanup_confirmed=cleanup,
        feedback=feedback,
    )


_HELD = _role(RoleOutcome.HELD, [4], 0)
_VIOLATION = _role(RoleOutcome.VIOLATION, [4], 1)


def _demonstrated() -> Observation:
    return _observation(_HELD, _VIOLATION)


def _clean_negative() -> Observation:
    return _observation(_HELD, _role(RoleOutcome.HELD, [4], 0))


# --- session_verdict -------------------------------------------------------


def test_likely_exploitable_requires_a_confirmed_differential():
    outcome = session_verdict(
        _prepared(), _demonstrated(), _audit(), FixStatus.DEMONSTRATION_BLOCKED
    )
    assert outcome == SessionOutcome(outcome.verdict, outcome.reason)
    assert outcome.verdict is Verdict.LIKELY_EXPLOITABLE
    assert outcome.clean_negative is False


def test_exploit_that_also_violates_on_the_fix_is_not_differential():
    outcome = session_verdict(_prepared(), _demonstrated(), _audit(), FixStatus.NOT_BLOCKED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.reason == "not_differential"


@pytest.mark.parametrize("fix", [FixStatus.UNVERIFIED, FixStatus.NOT_REQUESTED])
def test_unconfirmed_fix_differential_is_never_decisive(fix: FixStatus):
    outcome = session_verdict(_prepared(), _demonstrated(), _audit(), fix)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.reason == "fix differential unverified"


def test_coverage_miss_blocks_any_decisive_session():
    # Adversarial run never executed the declared finding line.
    observation = _observation(_HELD, _role(RoleOutcome.VIOLATION, [], 1))
    outcome = session_verdict(_prepared(), observation, _audit(), FixStatus.DEMONSTRATION_BLOCKED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.reason == "declared target line not covered in both runs"
    assert outcome.clean_negative is False


def test_absent_target_line_cannot_be_a_clean_negative():
    prepared = _prepared().model_copy(
        update={"finding": _prepared().finding.model_copy(update={"line": None})}
    )
    outcome = session_verdict(prepared, _clean_negative(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.clean_negative is False


def test_clean_negative_is_a_signal_not_a_label():
    outcome = session_verdict(_prepared(), _clean_negative(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.clean_negative is True
    assert outcome.reason == "clean_negative"


def test_rejected_audit_is_non_decisive():
    outcome = session_verdict(
        _prepared(),
        _demonstrated(),
        _audit(AuditDecision.REJECT),
        FixStatus.DEMONSTRATION_BLOCKED,
    )
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.clean_negative is False


def test_blocked_gate_is_unable_to_run_even_without_cleanup():
    observation = _observation(
        None,
        None,
        cleanup=False,
        feedback=Feedback(gate="sandbox", reason="image unavailable", operational=True),
    )
    outcome = session_verdict(_prepared(), observation, _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.UNABLE_TO_RUN


def test_infrastructure_fault_is_error():
    observation = _observation(_HELD, _VIOLATION, artifact=None)
    outcome = session_verdict(_prepared(), observation, _audit(), FixStatus.DEMONSTRATION_BLOCKED)
    assert outcome.verdict is Verdict.ERROR


def test_completed_run_without_confirmed_cleanup_is_error():
    observation = _observation(_HELD, _VIOLATION, cleanup=False)
    outcome = session_verdict(_prepared(), observation, _audit(), FixStatus.DEMONSTRATION_BLOCKED)
    assert outcome.verdict is Verdict.ERROR


# --- case_verdict ----------------------------------------------------------


def _le() -> SessionOutcome:
    return SessionOutcome(Verdict.LIKELY_EXPLOITABLE, "le")


def _neg() -> SessionOutcome:
    return SessionOutcome(Verdict.INCONCLUSIVE, "clean_negative", clean_negative=True)


def _unable() -> SessionOutcome:
    return SessionOutcome(Verdict.UNABLE_TO_RUN, "blocked")


def _error() -> SessionOutcome:
    return SessionOutcome(Verdict.ERROR, "faulted")


def _inconclusive() -> SessionOutcome:
    return SessionOutcome(Verdict.INCONCLUSIVE, "nothing")


def test_any_exploitable_session_wins():
    verdict, _ = case_verdict([_le(), _error(), _neg()])
    assert verdict is Verdict.LIKELY_EXPLOITABLE


def test_lone_clean_negative_is_never_likely_not_exploitable():
    verdict, _ = case_verdict([_neg()], negative_threshold=2)
    assert verdict is Verdict.INCONCLUSIVE


def test_two_independent_clean_negatives_reach_likely_not_exploitable():
    verdict, reason = case_verdict([_neg(), _neg()], negative_threshold=2)
    assert verdict is Verdict.LIKELY_NOT_EXPLOITABLE
    assert "sensitivity:unverified" in reason


def test_negative_threshold_is_honoured():
    verdict, _ = case_verdict([_neg(), _neg()], negative_threshold=3)
    assert verdict is Verdict.INCONCLUSIVE


def test_all_unable_sessions_aggregate_to_unable_to_run():
    verdict, _ = case_verdict([_unable(), _unable()])
    assert verdict is Verdict.UNABLE_TO_RUN


def test_error_without_any_decisive_signal_is_error():
    verdict, _ = case_verdict([_error(), _inconclusive()])
    assert verdict is Verdict.ERROR


def test_no_sessions_is_inconclusive():
    verdict, _ = case_verdict([])
    assert verdict is Verdict.INCONCLUSIVE


@pytest.mark.parametrize(
    ("status_reason", "expected"),
    [
        (("ERROR", "boom"), Verdict.ERROR),
        (("CANCELLED", "stopped"), Verdict.ERROR),
        (("BLOCKED", "gate"), Verdict.UNABLE_TO_RUN),
        (("COMPLETED", "nothing"), Verdict.INCONCLUSIVE),
    ],
)
def test_status_outcome_maps_non_evaluated_sessions(status_reason, expected):
    from corsair.contracts import ExecutionStatus

    status, reason = status_reason
    assert status_outcome(ExecutionStatus(status), reason).verdict is expected
