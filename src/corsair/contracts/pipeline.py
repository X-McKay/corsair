"""Canonical intake-gated investigation contracts; no SDK dependencies."""

from typing import Literal

from pydantic import Field, model_validator

from .common import ArtifactRef, Contract, Digest, Identifier, Usage
from .execution import ExecutionOutcome
from .intake import IntakeRequest, IntakeResult
from .sources import Source

StopReason = Literal[
    "OUT_OF_SCOPE",
    "UNSUPPORTED",
    "NEEDS_INPUT",
    "INTAKE_ERROR",
    "HANDOFF_INVALID",
    "BUDGET_EXHAUSTED",
    "INTAKE_UNCERTAIN",
    "EXECUTION_UNCERTAIN",
    "CANCELLED",
    "DEADLINE_EXHAUSTED",
]


class IssueInvestigationRequest(Contract):
    schema_version: Literal["corsair.issue-investigation-request/4"] = (
        "corsair.issue-investigation-request/4"
    )
    case_id: Identifier
    intake: IntakeRequest
    fixed_source: Source | None = None

    @model_validator(mode="after")
    def bounded_request(self):
        if len(self.model_dump_json().encode()) > 131072:
            raise ValueError("issue investigation request exceeds envelope limit")
        return self


class IssueInvestigationResult(Contract):
    schema_version: Literal["corsair.issue-investigation-result/4"] = (
        "corsair.issue-investigation-result/4"
    )
    run_id: Identifier
    case_id: Identifier
    request_digest: Digest
    status: Literal["stopped", "investigation_finished", "incomplete"] = "incomplete"
    stop_reason: StopReason | None = "INTAKE_UNCERTAIN"
    intake: IntakeResult | None = None
    execution_run_id: Identifier | None = None
    execution_result: ArtifactRef | None = None
    execution_outcome: ExecutionOutcome | None = None
    execution_error: str | None = Field(default=None, max_length=128)
    security_assessment: Literal["UNRESOLVED"] = "UNRESOLVED"
    usage: Usage = Field(default_factory=Usage)
    usage_complete: bool = False
    result_artifact: ArtifactRef | None = None

    @model_validator(mode="after")
    def consistent_result(self):
        if self.status == "investigation_finished":
            if (
                self.stop_reason is not None
                or self.execution_result is None
                or self.execution_run_id is None
                or self.execution_outcome is None
                or self.intake is None
                or self.intake.decision.classification != "in_scope_supported"
            ):
                raise ValueError(
                    "finished investigation requires supported intake and recorded child"
                )
        elif self.stop_reason is None:
            raise ValueError("stopped or incomplete investigation requires a categorical reason")
        if self.status == "stopped" and self.execution_run_id is not None:
            raise ValueError("stopped intake must not schedule investigation")
        return self
