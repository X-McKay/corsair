"""Deterministic policy for evidence observations and assessment conclusions.

A passing adversarial probe is not a clearance. Legacy dispositions retain their
existing evidence meaning; versioned result records may additionally expose a
completed assessment conclusion when a trusted paired protocol is satisfied.
"""

from __future__ import annotations

from corsair.contracts import (
    AssessmentOutcome,
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


def _has_required_coverage(prepared: PreparedCase, role: RoleObservation) -> bool:
    """Require the configured finding line when the recipe declares one."""
    return prepared.finding.line is None or prepared.finding.line in role.covered_lines


def _assessment_role_valid(
    prepared: PreparedCase, role: RoleObservation, expected: RoleOutcome
) -> bool:
    return _native_role_valid(role, expected) and _has_required_coverage(prepared, role)


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


def assessment_outcome(
    prepared: PreparedCase, observation: Observation, audit: AuditOutput
) -> AssessmentOutcome | None:
    """Return a completed conclusion for one independently audited paired observation.

    This policy checks the result-level gate ledger. The evaluator additionally
    revalidates the immutable evidence receipt before counting either conclusion.
    ``None`` is an incomplete assessment, not a third security label.
    """
    if (
        observation.feedback is not None
        or observation.artifact is None
        or observation.source_digest != prepared.source.sha256
        or not observation.cleanup_confirmed
        or observation.control is None
        or observation.adversarial is None
        or audit.feedback is not None
        or audit.review is None
        or audit.review.decision is not AuditDecision.ACCEPT
    ):
        return None
    control = observation.control
    adversarial = observation.adversarial
    if _assessment_role_valid(prepared, control, RoleOutcome.HELD) and _assessment_role_valid(
        prepared, adversarial, RoleOutcome.VIOLATION
    ):
        return AssessmentOutcome.DEMONSTRATED
    if _assessment_role_valid(prepared, control, RoleOutcome.HELD) and _assessment_role_valid(
        prepared, adversarial, RoleOutcome.HELD
    ):
        return AssessmentOutcome.NOT_DEMONSTRATED
    return None


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
    """Return a conservative legacy disposition and execution status for one observation."""
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
