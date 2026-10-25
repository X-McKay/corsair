"""Deterministic policy for evidence observations.

A passing adversarial probe is not a clearance. The only affirmative result is a
trusted, complete secret-disclosure demonstration with a healthy control and an
accepted audit; all negative or incomplete evidence remains inconclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    Disposition,
    ExecutionStatus,
    FixStatus,
    Observation,
    PreparedCase,
    RoleObservation,
    RoleOutcome,
    Scope,
    Verdict,
)


def _blocked(observation: Observation) -> bool:
    return observation.feedback is not None and observation.feedback.operational


def _native_role_valid(role: RoleObservation, expected: RoleOutcome) -> bool:
    """Perform the small policy-level portion of native evidence validation."""
    if role.outcome is not expected or not role.target_executed:
        return False
    if type(role.native_exit_code) is not int or role.native_exit_code < 0:
        return False
    if expected is RoleOutcome.HELD:
        return role.native_exit_code == 0
    if expected is RoleOutcome.VIOLATION:
        return role.native_exit_code != 0
    return False


def _roles_are_executable(observation: Observation) -> bool:
    return bool(
        observation.control is not None
        and observation.adversarial is not None
        and observation.control.target_executed
        and observation.adversarial.target_executed
        and type(observation.control.native_exit_code) is int
        and observation.control.native_exit_code >= 0
        and type(observation.adversarial.native_exit_code) is int
        and observation.adversarial.native_exit_code >= 0
    )


def fix_status(observation: Observation | None) -> FixStatus:
    """Classify a separately-run fixed revision without treating it as a clearance."""
    if (
        observation is None
        or observation.artifact is None
        or _blocked(observation)
        or not observation.cleanup_confirmed
        or not _roles_are_executable(observation)
    ):
        return FixStatus.UNVERIFIED
    assert observation.control is not None
    assert observation.adversarial is not None
    if _native_role_valid(observation.control, RoleOutcome.HELD) and _native_role_valid(
        observation.adversarial, RoleOutcome.VIOLATION
    ):
        return FixStatus.NOT_BLOCKED
    if _native_role_valid(observation.control, RoleOutcome.HELD) and _native_role_valid(
        observation.adversarial, RoleOutcome.HELD
    ):
        return FixStatus.DEMONSTRATION_BLOCKED
    return FixStatus.UNVERIFIED


def decide(
    prepared: PreparedCase, observation: Observation, audit: AuditOutput
) -> tuple[Disposition, ExecutionStatus, str]:
    """Return a conservative disposition and execution status for one observation."""
    if _blocked(observation):
        assert observation.feedback is not None
        return Disposition.INCONCLUSIVE, ExecutionStatus.BLOCKED, observation.feedback.reason
    if observation.artifact is None:
        return (
            Disposition.INCONCLUSIVE,
            ExecutionStatus.ERROR,
            "persisted evidence artifact is missing",
        )
    if observation.source_digest != prepared.source.sha256:
        return (
            Disposition.INCONCLUSIVE,
            ExecutionStatus.ERROR,
            "evidence source digest does not match case",
        )
    if not observation.cleanup_confirmed:
        return (
            Disposition.INCONCLUSIVE,
            ExecutionStatus.ERROR,
            "container cleanup was not independently confirmed",
        )
    if observation.control is None or observation.adversarial is None:
        return (
            Disposition.INCONCLUSIVE,
            ExecutionStatus.ERROR,
            "both role observations are required",
        )
    if audit.feedback is not None and audit.feedback.operational:
        return Disposition.INCONCLUSIVE, ExecutionStatus.BLOCKED, audit.feedback.reason
    if any(
        role.outcome is RoleOutcome.ERROR for role in (observation.control, observation.adversarial)
    ):
        return Disposition.INCONCLUSIVE, ExecutionStatus.ERROR, "trusted probe execution errored"
    if not _roles_are_executable(observation):
        return Disposition.INCONCLUSIVE, ExecutionStatus.COMPLETED, "probe evidence was invalid"

    control = observation.control
    adversarial = observation.adversarial
    if control.outcome is RoleOutcome.INVALID or adversarial.outcome is RoleOutcome.INVALID:
        return Disposition.INCONCLUSIVE, ExecutionStatus.COMPLETED, "probe evidence was invalid"

    # A failing control invalidates an exploit demonstration; a benign adversarial
    # outcome is intentionally not a refutation or non-exploitability claim.
    demonstrated = _native_role_valid(control, RoleOutcome.HELD) and _native_role_valid(
        adversarial, RoleOutcome.VIOLATION
    )
    if not demonstrated:
        return (
            Disposition.INCONCLUSIVE,
            ExecutionStatus.COMPLETED,
            "no reproducible secret-disclosure demonstration was observed",
        )

    if audit.review is None:
        return Disposition.INCONCLUSIVE, ExecutionStatus.COMPLETED, "independent audit is missing"
    if audit.review.decision is not AuditDecision.ACCEPT:
        return Disposition.INCONCLUSIVE, ExecutionStatus.COMPLETED, audit.review.reason
    if prepared.finding.claim_scope is Scope.APPLICATION:
        return (
            Disposition.CONDITIONAL,
            ExecutionStatus.COMPLETED,
            "component-only evidence supports the finding but not an application-wide claim",
        )
    return Disposition.SUPPORTED, ExecutionStatus.COMPLETED, audit.review.reason


@dataclass(frozen=True)
class SessionOutcome:
    """The canonical outcome of one independent investigation session.

    ``clean_negative`` is a session-level signal, not a verdict: a single clean
    negative is never decisive. The aggregator counts independent clean negatives
    and only promotes them to EXPLOIT_NOT_DEMONSTRATED once the threshold is met.
    """

    verdict: Verdict
    reason: str
    clean_negative: bool = False


def _audit_accepts(audit: AuditOutput) -> bool:
    return audit.review is not None and audit.review.decision is AuditDecision.ACCEPT


def _line_covered_in_both(prepared: PreparedCase, observation: Observation) -> bool:
    """The exact declared finding line must execute in BOTH the control and the
    adversarial run before a session may be decisive. This is the primary guard
    against a false EXPLOIT_NOT_DEMONSTRATED: a negative we did not actually reach
    is never a clean negative."""
    line = prepared.finding.line
    if line is None or observation.control is None or observation.adversarial is None:
        return False
    return (
        line in observation.control.covered_lines and line in observation.adversarial.covered_lines
    )


def session_verdict(
    prepared: PreparedCase,
    observation: Observation,
    audit: AuditOutput,
    fix: FixStatus,
) -> SessionOutcome:
    """Decide the canonical outcome of ONE independent session. Pure; no I/O or SDK.

    The internal ``decide()`` supplies the conservative disposition/execution
    status; this layer adds the coverage gate and the confirmed fixed-revision
    differential that a decisive verdict requires.
    """
    _disposition, execution_status, reason = decide(prepared, observation, audit)

    # 1. Infrastructure fault on the vulnerable revision: the session proved nothing.
    if execution_status is ExecutionStatus.ERROR:
        return SessionOutcome(Verdict.ERROR, reason)

    # 2. Target not found / unsupported scope / build-replay failed all surface as
    #    an operational BLOCKED gate from decide(); the session could not run. This
    #    is checked before cleanup because a gate that never ran a probe legitimately
    #    has nothing to clean up.
    if execution_status in {ExecutionStatus.BLOCKED, ExecutionStatus.CANCELLED}:
        return SessionOutcome(Verdict.UNABLE_TO_RUN, reason)

    # 3. A completed run whose container cleanup was not independently confirmed is
    #    an integrity fault (decide() already yields ERROR here; kept explicit).
    if not observation.cleanup_confirmed:
        return SessionOutcome(Verdict.ERROR, reason)

    # 3. Exact target-line coverage gate: without it the session cannot be decisive.
    if not _line_covered_in_both(prepared, observation):
        return SessionOutcome(Verdict.INCONCLUSIVE, "declared target line not covered in both runs")

    assert observation.control is not None and observation.adversarial is not None
    control_held = _native_role_valid(observation.control, RoleOutcome.HELD)
    adversarial_violation = _native_role_valid(observation.adversarial, RoleOutcome.VIOLATION)
    adversarial_held = _native_role_valid(observation.adversarial, RoleOutcome.HELD)
    accepted = _audit_accepts(audit)

    # 4. EXPLOIT_DEMONSTRATED requires a healthy control, a reproduced violation, an
    #    accepted audit, and a CONFIRMED fixed-revision differential.
    if control_held and adversarial_violation and accepted:
        if fix is FixStatus.DEMONSTRATION_BLOCKED:
            return SessionOutcome(Verdict.EXPLOIT_DEMONSTRATED, reason)
        if fix is FixStatus.NOT_BLOCKED:
            return SessionOutcome(Verdict.INCONCLUSIVE, "not_differential")
        return SessionOutcome(Verdict.INCONCLUSIVE, "fix differential unverified")

    # 5. Clean negative: healthy control, the exploit did NOT violate, accepted
    #    audit, coverage gate passed. A session-level signal, never itself a label.
    if control_held and adversarial_held and accepted:
        return SessionOutcome(Verdict.INCONCLUSIVE, "clean_negative", clean_negative=True)

    # 6. Anything else is non-decisive.
    return SessionOutcome(Verdict.INCONCLUSIVE, reason)


def status_outcome(execution_status: ExecutionStatus, reason: str) -> SessionOutcome:
    """Map a session that produced no evaluable observation to a session outcome."""
    if execution_status in {ExecutionStatus.ERROR, ExecutionStatus.CANCELLED}:
        return SessionOutcome(Verdict.ERROR, reason)
    if execution_status is ExecutionStatus.BLOCKED:
        return SessionOutcome(Verdict.UNABLE_TO_RUN, reason)
    return SessionOutcome(Verdict.INCONCLUSIVE, reason)


def case_verdict(
    sessions: list[SessionOutcome], negative_threshold: int = 2
) -> tuple[Verdict, str]:
    """Aggregate independent sessions into one canonical case verdict. Pure.

    EXPLOIT_NOT_DEMONSTRATED is deliberately the hardest verdict to reach: it needs
    at least ``negative_threshold`` independent clean negatives and no exploitable
    session, and it is only ever scoped to the exact finding/payloads/revision/
    runtime that were exercised (sensitivity:unverified).
    """
    if not sessions:
        return Verdict.INCONCLUSIVE, "no sessions"
    if any(session.verdict is Verdict.EXPLOIT_DEMONSTRATED for session in sessions):
        return Verdict.EXPLOIT_DEMONSTRATED, "a session reproduced an exploitable differential"
    clean_negatives = sum(1 for session in sessions if session.clean_negative)
    if clean_negatives >= negative_threshold:
        return (
            Verdict.EXPLOIT_NOT_DEMONSTRATED,
            "independent clean negatives scoped to finding/payloads/revision/runtime "
            "(sensitivity:unverified)",
        )
    if all(session.verdict is Verdict.UNABLE_TO_RUN for session in sessions):
        return Verdict.UNABLE_TO_RUN, "no session could run"
    if any(session.verdict is Verdict.ERROR for session in sessions):
        return Verdict.ERROR, "a session faulted without any decisive signal"
    return Verdict.INCONCLUSIVE, "no decisive signal across sessions"
