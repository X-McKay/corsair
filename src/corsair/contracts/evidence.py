"""Canonical evidence wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from .agents import Submission
from .common import ArtifactRef, Contract, DiagnosticText, Digest, Feedback, Identifier
from .sources import Budget, PreparedCase


class RoleOutcome(StrEnum):
    HELD = "PROPERTY_HELD"
    VIOLATION = "VIOLATION"
    INVALID = "INVALID"
    ERROR = "ERROR"


ErrorKind = Literal["target_exception", "harness", "sandbox"]
"""Trusted code's class of an ERROR role, read from receipt facts only:

- ``target_exception``: the cleanup-confirmed driver record reports ERROR with
  ``observation_kind`` ``execution_error`` (the target raised outside the recipe's
  allowed exceptions, or crashed).
- ``harness``: the driver record reports ERROR with any other ``observation_kind``.
- ``sandbox``: no driver record (the receipt's ``error``, e.g. ``SandboxExecutionError``),
  no receipt at all, or a role not run after an earlier sandbox fault.
"""


class RoleObservation(Contract):
    """One role's admitted execution facts, plus sandbox timing kept apart from them.

    An ERROR role keeps the coverage its receipt reported for the recipe module, and
    ``target_executed`` follows that coverage as for every other outcome; ``error_kind``
    classifies it. Neither enters a verdict: any ERROR role decides ERROR first.

    The three ``*_seconds`` fields are efficiency telemetry rebuilt from the raw receipt.
    They never enter an outcome, coverage, audit or verdict decision, and ``None`` means
    unknown (every receipt saved before they existed), never zero.
    """

    outcome: RoleOutcome
    target_executed: StrictBool
    covered_lines: list[int] = Field(default_factory=list)
    reason: DiagnosticText = ""
    native_exit_code: int | None = None
    error_kind: ErrorKind | None = None
    """Set for every ERROR role trusted code builds; ``None`` on every other outcome and
    on ERROR roles saved before it existed (which also kept no coverage)."""
    wall_seconds: float | None = Field(default=None, ge=0)
    """Driver-reported wall time around the native target step inside the container."""
    cpu_seconds: float | None = Field(default=None, ge=0)
    """Driver-reported cgroup v2 ``usage_usec`` of the whole container when the driver
    wrote its record. Untrusted target code shares the container, so this is efficiency
    telemetry only and never participates in a verdict."""
    host_seconds: float | None = Field(default=None, ge=0)
    """Trusted host-side seconds from container create to its wait returning."""

    @model_validator(mode="after")
    def error_kind_needs_error(self) -> Self:
        if self.error_kind is not None and self.outcome is not RoleOutcome.ERROR:
            raise ValueError("error_kind is only recorded for an ERROR outcome")
        return self


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
