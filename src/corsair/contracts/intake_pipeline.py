"""Intake-gated entrypoint over main's unchanged evidence and verdict pipeline."""

from typing import Literal

from pydantic import Field, model_validator

from .common import ArtifactRef, Contract, Identifier, Usage
from .intake_agent import IntakeRequest, IntakeResult
from .results import Disposition, ExecutionStatus
from .sources import Case

StopReason = Literal[
    "OUT_OF_SCOPE",
    "UNSUPPORTED",
    "NEEDS_INPUT",
    "INTAKE_ERROR",
    "TARGET_BINDING_REQUIRED",
    "HANDOFF_INVALID",
    "BUDGET_EXHAUSTED",
    "INTAKE_UNCERTAIN",
    "INVESTIGATION_UNCERTAIN",
    "CANCELLED",
    "DEADLINE_EXHAUSTED",
]


class IntakeInvestigationRequest(Contract):
    schema_version: Literal["corsair.intake-investigation-request/1"] = (
        "corsair.intake-investigation-request/1"
    )
    case_id: Identifier
    intake: IntakeRequest
    binding: Case | None = None

    @model_validator(mode="after")
    def bounded(self):
        if len(self.model_dump_json().encode()) > 131072:
            raise ValueError("intake investigation request exceeds envelope limit")
        if self.binding is not None and (
            self.binding.case_id != self.case_id or self.binding.source != self.intake.source
        ):
            raise ValueError("trusted binding must match case identity and intake source")
        return self


class IntakeInvestigationResult(Contract):
    schema_version: Literal["corsair.intake-investigation-result/1"] = (
        "corsair.intake-investigation-result/1"
    )
    run_id: Identifier
    case_id: Identifier
    status: Literal["stopped", "investigation_finished", "incomplete"] = "incomplete"
    stop_reason: StopReason | None = "INTAKE_UNCERTAIN"
    intake: IntakeResult | None = None
    investigation_run_id: Identifier | None = None
    investigation_result: ArtifactRef | None = None
    investigation_disposition: Disposition | None = None
    investigation_execution_status: ExecutionStatus | None = None
    usage: Usage = Field(default_factory=Usage)
    usage_complete: bool = False
    result_artifact: ArtifactRef | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "investigation_finished":
            if (
                self.stop_reason is not None
                or self.investigation_result is None
                or self.investigation_run_id is None
                or self.intake is None
                or self.intake.decision.classification != "in_scope_supported"
            ):
                raise ValueError("finished parent requires supported intake and recorded child")
        elif self.stop_reason is None:
            raise ValueError("stopped/incomplete parent requires categorical reason")
        if self.status == "stopped" and self.investigation_run_id is not None:
            raise ValueError("stopped intake must not schedule investigation")
        return self
