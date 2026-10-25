"""Canonical results wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .agents import AuditOutput, ProducerOutput
from .common import ArtifactRef, Contract, Identifier
from .evidence import Observation
from .sources import RunManifest, Scope


class RoundResult(Contract):
    index: int
    producer: ProducerOutput
    observation: Observation | None = None
    audit: AuditOutput | None = None


class Disposition(StrEnum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    CONDITIONAL = "CONDITIONAL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FixStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    DEMONSTRATION_BLOCKED = "DEMONSTRATION_BLOCKED"
    NOT_BLOCKED = "NOT_BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class InvestigationResult(Contract):
    schema_version: Literal["corsair.result/1"] = "corsair.result/1"
    run_id: Identifier
    case_id: Identifier
    disposition: Disposition
    execution_status: ExecutionStatus
    reason: str
    scope: Scope = Scope.COMPONENT
    manifest: RunManifest | None = None
    rounds: list[RoundResult] = Field(default_factory=list)
    usage_complete: bool = True
    fix_status: FixStatus = FixStatus.NOT_REQUESTED
    fix_observation: Observation | None = None
    result_artifact: ArtifactRef | None = None
