"""Deterministic policy for evidence observations.

A passing adversarial probe is not a clearance. The only affirmative result is a
trusted, complete secret-disclosure demonstration with a healthy control and an
accepted audit; all negative or incomplete evidence remains inconclusive.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

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
    RoundResult,
    Scope,
    Submission,
    Verdict,
    digest,
)
from corsair.contracts.recipes import CLEAN_NEGATIVE_QUALIFIED_KINDS


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
    negative is never decisive. The aggregator counts clean negatives with DISTINCT
    ``candidate_key`` values and only promotes them to EXPLOIT_NOT_DEMONSTRATED once
    the threshold is met. ``candidate_key`` is the session's terminal-round candidate
    (``candidate_key(submission)``); an outcome without one cannot show independence.
    """

    verdict: Verdict
    reason: str
    clean_negative: bool = False
    candidate_key: str | None = None


def candidate_key(submission: Submission) -> str:
    """The canonical identity of a session's candidate: the exploit payload's digest.

    Only the adversarial payload is evidence about the finding; a different benign
    control, hypothesis or plan adds no diversity. The floor is an exact digest of the
    canonical JSON value, so near-duplicates (``../x`` and ``./../x``) still count as
    distinct candidates (ADR 0004, distinct candidates addendum).
    """
    return digest({"exploit_payload": submission.exploit_payload})


def terminal_round(rounds: Sequence[RoundResult]) -> RoundResult | None:
    """A session's deciding round: its last round with both an observation and an audit."""
    return next(
        (
            item
            for item in reversed(rounds)
            if item.observation is not None and item.audit is not None
        ),
        None,
    )


def terminal_outcome(
    prepared: PreparedCase, terminal: RoundResult, fix: FixStatus
) -> SessionOutcome:
    """``session_verdict`` of a session's terminal round, keyed by that round's candidate."""
    assert terminal.observation is not None and terminal.audit is not None
    outcome = session_verdict(prepared, terminal.observation, terminal.audit, fix)
    submission = terminal.producer.submission_for_verification()
    if submission is None:
        return outcome
    return replace(outcome, candidate_key=candidate_key(submission))


def distinct_clean_negatives(sessions: Iterable[SessionOutcome]) -> int:
    """Clean-negative sessions counted once per distinct candidate; a repeated exploit
    payload adds no independent negative and an unkeyed clean negative adds none."""
    return len(
        {
            session.candidate_key
            for session in sessions
            if session.clean_negative and session.candidate_key is not None
        }
    )


def clean_negative_withheld(kind: str) -> str:
    """The fixed reason a held, covered, accepted pair is not a clean negative."""
    return f"clean negative withheld: auditor rubric not qualified for {kind}"


def _audit_accepts(audit: AuditOutput) -> bool:
    return audit.review is not None and audit.review.decision is AuditDecision.ACCEPT


def _line_covered_in_both(prepared: PreparedCase, observation: Observation) -> bool:
    """The exact target line must execute in BOTH the control and the adversarial
    run before a session may be decisive. This is the primary guard against a false
    EXPLOIT_NOT_DEMONSTRATED: a negative we did not actually reach is never a clean
    negative. The target is the declared finding line as bound in code at prepare
    to the statement line coverage reports (``PreparedCase.bound_line``)."""
    line = prepared.bound_line
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
    status; this layer adds the target-binding and exact-coverage gates and treats
    the fixed revision as optional confirmation of the vulnerable-revision
    differential, never as a precondition for EXPLOIT_DEMONSTRATED.
    """
    disposition, execution_status, reason = decide(prepared, observation, audit)

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

    # 4. Target binding: a decisive verdict is only ever about the exact declared
    #    finding line. Without a line there is no target to bind to, so the session
    #    is UNABLE_TO_RUN rather than a silent negative -- the primary guard against
    #    a demonstration (or clean negative) credited to a target we never located.
    if prepared.finding.line is None:
        return SessionOutcome(
            Verdict.UNABLE_TO_RUN, "finding declares no target line to bind the demonstration to"
        )

    # 5. Exact target-line coverage gate: the bound target line must execute in BOTH
    #    the control and adversarial runs before the session may be decisive.
    if not _line_covered_in_both(prepared, observation):
        return SessionOutcome(Verdict.INCONCLUSIVE, "declared target line not covered in both runs")

    assert observation.control is not None and observation.adversarial is not None
    control_held = _native_role_valid(observation.control, RoleOutcome.HELD)
    adversarial_violation = _native_role_valid(observation.adversarial, RoleOutcome.VIOLATION)
    adversarial_held = _native_role_valid(observation.adversarial, RoleOutcome.HELD)
    accepted = _audit_accepts(audit)

    # 6. EXPLOIT_DEMONSTRATED rests on the control-vs-exploit differential on the
    #    VULNERABLE revision: a healthy control, a reproduced violation, an accepted
    #    audit, and the coverage gate above. A fixed revision is optional
    #    confirmation, never a precondition (ADR 0004). The only outcome that blocks
    #    the label is a fixed revision on which the exploit STILL violates
    #    (FixStatus.NOT_BLOCKED): the fix is incomplete or the demonstration is
    #    suspect, so the label is withheld rather than silently awarded.
    if control_held and adversarial_violation and accepted:
        if fix is FixStatus.NOT_BLOCKED:
            return SessionOutcome(
                Verdict.INCONCLUSIVE,
                "exploit still violates on the fixed revision; "
                "fix incomplete or demonstration suspect",
            )
        # Scope classification (code-decided, no model). decide() returns
        # CONDITIONAL exactly when the finding claimed APPLICATION scope but the
        # probe exercised only the component callable directly (the sole scope
        # signal in the evidence model: finding.claim_scope, bound to the recipe
        # that drives the component seam, never the application entry point). The
        # differential genuinely holds at the component, but reachability to the
        # claimed application entry point was not established, so the demonstration
        # is scoped to the component rather than over-claimed as application-wide.
        if disposition is Disposition.CONDITIONAL:
            return SessionOutcome(Verdict.COMPONENT_EXPLOIT_DEMONSTRATED, reason)
        return SessionOutcome(Verdict.EXPLOIT_DEMONSTRATED, reason)

    # 7. Clean negative: healthy control, the exploit did NOT violate, accepted
    #    audit, coverage gate passed. A session-level signal, never itself a label,
    #    and withheld for a kind whose auditor rubric is not qualified: the audit is
    #    the clean-negative path's only semantic check.
    if control_held and adversarial_held and accepted:
        kind = prepared.recipe.kind
        if kind not in CLEAN_NEGATIVE_QUALIFIED_KINDS:
            return SessionOutcome(Verdict.INCONCLUSIVE, clean_negative_withheld(kind))
        return SessionOutcome(Verdict.INCONCLUSIVE, "clean_negative", clean_negative=True)

    # 8. Anything else is non-decisive.
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
    at least ``negative_threshold`` independent clean negatives on distinct candidates
    and no exploitable session, and it is only ever scoped to the exact finding/
    payloads/revision/runtime that were exercised (sensitivity:unverified).
    """
    if not sessions:
        return Verdict.INCONCLUSIVE, "no sessions"
    if any(session.verdict is Verdict.EXPLOIT_DEMONSTRATED for session in sessions):
        return Verdict.EXPLOIT_DEMONSTRATED, "a session reproduced an exploitable differential"
    # A component-scoped demonstration is decisive and outranks clean negatives: one
    # session that reproduced the component differential is not refuted by another
    # session failing to reproduce it. Full application scope above wins over it.
    if any(session.verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED for session in sessions):
        return (
            Verdict.COMPONENT_EXPLOIT_DEMONSTRATED,
            "a session reproduced the differential at component scope only",
        )
    distinct = distinct_clean_negatives(sessions)
    if distinct >= negative_threshold:
        return (
            Verdict.EXPLOIT_NOT_DEMONSTRATED,
            "independent clean negatives scoped to finding/payloads/revision/runtime "
            "(sensitivity:unverified)",
        )
    if all(session.verdict is Verdict.UNABLE_TO_RUN for session in sessions):
        return Verdict.UNABLE_TO_RUN, "no session could run"
    if any(session.verdict is Verdict.ERROR for session in sessions):
        return Verdict.ERROR, "a session faulted without any decisive signal"
    if sum(session.clean_negative for session in sessions) > distinct:
        return (
            Verdict.INCONCLUSIVE,
            f"{distinct} of {negative_threshold} required clean negatives on distinct candidates; "
            "a repeated exploit payload is not independent",
        )
    return Verdict.INCONCLUSIVE, "no decisive signal across sessions"
