"""Canonical evidence wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, StrictBool

from .agents import Submission
from .common import ArtifactRef, Contract, Digest, Feedback, Identifier
from .sources import Budget, PreparedCase


class RoleOutcome(StrEnum):
    HELD = "PROPERTY_HELD"
    VIOLATION = "VIOLATION"
    INVALID = "INVALID"
    ERROR = "ERROR"


class RoleObservation(Contract):
    outcome: RoleOutcome
    target_executed: StrictBool
    covered_lines: list[int] = Field(default_factory=list)
    reason: str
    native_exit_code: int | None = None


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
