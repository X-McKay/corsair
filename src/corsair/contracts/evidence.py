"""Canonical evidence wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, StrictBool

from .agents import Submission
from .common import ArtifactRef, Contract, DiagnosticText, Digest, Feedback, Identifier
from .sources import Budget, PreparedCase


class RoleOutcome(StrEnum):
    HELD = "PROPERTY_HELD"
    VIOLATION = "VIOLATION"
    INVALID = "INVALID"
    ERROR = "ERROR"


class RoleObservation(Contract):
    """One role's admitted execution facts, plus sandbox timing kept apart from them.

    The three ``*_seconds`` fields are efficiency telemetry rebuilt from the raw receipt.
    They never enter an outcome, coverage, audit or verdict decision, and ``None`` means
    unknown (every receipt saved before they existed), never zero.
    """

    outcome: RoleOutcome
    target_executed: StrictBool
    covered_lines: list[int] = Field(default_factory=list)
    reason: DiagnosticText = ""
    native_exit_code: int | None = None
    wall_seconds: float | None = Field(default=None, ge=0)
    """Driver-reported wall time around the native target step inside the container."""
    cpu_seconds: float | None = Field(default=None, ge=0)
    """Driver-reported cgroup v2 ``usage_usec`` of the whole container when the driver
    wrote its record. Untrusted target code shares the container, so this is efficiency
    telemetry only and never participates in a verdict."""
    host_seconds: float | None = Field(default=None, ge=0)
    """Trusted host-side seconds from container create to its wait returning."""


class EvidenceInput(Contract):
    run_id: Identifier
    operation_id: Identifier
    prepared: PreparedCase
    submission: Submission
    budget: Budget
    fixed: StrictBool = False


class Observation(Contract):
    operation_id: Identifier
    source_digest: Digest
    submission_digest: Digest
    control: RoleObservation | None = None
    adversarial: RoleObservation | None = None
    feedback: Feedback | None = None
    artifact: ArtifactRef | None = None
    cleanup_confirmed: StrictBool = False
