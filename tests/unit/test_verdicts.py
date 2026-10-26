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


def test_exploit_demonstrated_without_any_fixed_revision():
    """The vulnerable-revision control/exploit differential alone earns the label
    when no fixed revision was supplied. A fixed revision is optional confirmation,
    not a precondition."""
    outcome = session_verdict(_prepared(), _demonstrated(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome == SessionOutcome(outcome.verdict, outcome.reason)
    assert outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED
    assert outcome.clean_negative is False


def test_exploit_demonstrated_confirmed_by_a_blocking_fixed_revision():
    """A fixed revision on which the exploit no longer violates confirms the label."""
    outcome = session_verdict(
        _prepared(), _demonstrated(), _audit(), FixStatus.DEMONSTRATION_BLOCKED
    )
    assert outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED
    assert outcome.clean_negative is False


def test_exploit_that_also_violates_on_the_fix_is_withheld():
    """If the exploit still violates on the supplied fixed revision, the fix is
    incomplete or the demonstration is suspect; the label is withheld, not awarded."""
    outcome = session_verdict(_prepared(), _demonstrated(), _audit(), FixStatus.NOT_BLOCKED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert "still violates on the fixed revision" in outcome.reason


def test_unevaluable_fixed_revision_falls_back_to_the_vulnerable_differential():
    """A fixed revision was supplied but its run could not be cleanly evaluated
    (UNVERIFIED). The sound vulnerable-revision differential is not retracted, so
    the label still stands -- confirmation was merely unavailable."""
    outcome = session_verdict(_prepared(), _demonstrated(), _audit(), FixStatus.UNVERIFIED)
    assert outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_application_claim_proven_only_at_component_is_component_scoped():
    """An application-scope claim whose differential genuinely holds at the component
    seam -- but whose application reachability was not established -- is the explicit
    COMPONENT_EXPLOIT_DEMONSTRATED label, not the full application-scope one and not a
    soft INCONCLUSIVE."""
    from corsair.contracts import Scope

    finding = _prepared().finding.model_copy(update={"claim_scope": Scope.APPLICATION})
    prepared = _prepared().model_copy(update={"finding": finding})
    outcome = session_verdict(prepared, _demonstrated(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED
    assert outcome.clean_negative is False


def test_coverage_miss_blocks_any_decisive_session():
    # Adversarial run never executed the declared finding line.
    observation = _observation(_HELD, _role(RoleOutcome.VIOLATION, [], 1))
    outcome = session_verdict(_prepared(), observation, _audit(), FixStatus.DEMONSTRATION_BLOCKED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.reason == "declared target line not covered in both runs"
    assert outcome.clean_negative is False


def test_absent_target_line_is_unable_to_run_not_a_clean_negative():
    """With no declared line there is no target to bind to: the session cannot be
    decisive in either direction, so it is UNABLE_TO_RUN and never a clean negative."""
    prepared = _prepared().model_copy(
        update={"finding": _prepared().finding.model_copy(update={"line": None})}
    )
    outcome = session_verdict(prepared, _clean_negative(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.UNABLE_TO_RUN
    assert outcome.clean_negative is False


def test_absent_target_line_cannot_demonstrate_an_exploit():
    """The false-negative guard also holds in the positive direction: a reproduced
    violation against an unbound target is UNABLE_TO_RUN, never EXPLOIT_DEMONSTRATED."""
    prepared = _prepared().model_copy(
        update={"finding": _prepared().finding.model_copy(update={"line": None})}
    )
    outcome = session_verdict(prepared, _demonstrated(), _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.UNABLE_TO_RUN


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
    return SessionOutcome(Verdict.EXPLOIT_DEMONSTRATED, "le")


def _neg() -> SessionOutcome:
    return SessionOutcome(Verdict.INCONCLUSIVE, "clean_negative", clean_negative=True)


def _unable() -> SessionOutcome:
    return SessionOutcome(Verdict.UNABLE_TO_RUN, "blocked")


def _error() -> SessionOutcome:
    return SessionOutcome(Verdict.ERROR, "faulted")


def _inconclusive() -> SessionOutcome:
    return SessionOutcome(Verdict.INCONCLUSIVE, "nothing")


def _component() -> SessionOutcome:
    return SessionOutcome(Verdict.COMPONENT_EXPLOIT_DEMONSTRATED, "component")


def test_any_exploitable_session_wins():
    verdict, _ = case_verdict([_le(), _error(), _neg()])
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_component_demonstration_is_decisive_over_a_clean_negative():
    verdict, _ = case_verdict([_component(), _neg()])
    assert verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED


def test_full_application_scope_outranks_a_component_demonstration():
    verdict, _ = case_verdict([_component(), _le()])
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_lone_clean_negative_is_never_likely_not_exploitable():
    verdict, _ = case_verdict([_neg()], negative_threshold=2)
    assert verdict is Verdict.INCONCLUSIVE


def test_two_independent_clean_negatives_reach_likely_not_exploitable():
    verdict, reason = case_verdict([_neg(), _neg()], negative_threshold=2)
    assert verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED
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
