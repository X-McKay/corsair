"""Canonical recipe-free execution contracts; generated plans are untrusted data."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .common import ArtifactRef, Contract, Digest, Identifier, Usage, safe_path
from .intake import AvailableImage, Issue, Location
from .sources import Budget, Source

ExecutionOutcome = Literal["SUCCEEDED", "FAILED", "ERROR", "INCOMPLETE"]


class ExecutionRequest(Contract):
    schema_version: Literal["corsair.execution-request/3"] = "corsair.execution-request/3"
    case_id: Identifier
    issue: Issue
    source: Source
    image: AvailableImage
    fixed_source: Source | None = None
    intake_result: ArtifactRef | None = None
    budget: Budget = Field(default_factory=Budget)

    @model_validator(mode="after")
    def sufficient_issue(self):
        if len(self.model_dump_json().encode()) > 131072:
            raise ValueError("execution request exceeds serialized envelope limit")
        if not self.issue.title and not self.issue.description:
            raise ValueError("an investigation requires issue context")
        return self


class TestFile(Contract):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=32768)
    _path = field_validator("path")(safe_path)

    @field_validator("content")
    @classmethod
    def byte_bound(cls, value: str) -> str:
        if len(value.encode()) > 32768:
            raise ValueError("test file exceeds 32 KiB")
        return value


class Command(Contract):
    argv: list[Annotated[str, Field(min_length=1, max_length=32768)]] = Field(
        min_length=1, max_length=64
    )
    cwd: str = Field(default=".", max_length=240)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    expected: Literal["zero", "nonzero"] = "zero"

    @field_validator("argv")
    @classmethod
    def safe_argv(cls, value: list[str]) -> list[str]:
        if any("\x00" in part for part in value):
            raise ValueError("NUL in argv")
        if sum(len(part.encode()) for part in value) > 32768:
            raise ValueError("argv exceeds 32 KiB")
        return value

    @field_validator("cwd")
    @classmethod
    def work_directory(cls, value: str) -> str:
        return value if value == "." else safe_path(value)


class TestPlan(Contract):
    hypothesis: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=1, le=16)
    parent_revision: int | None = Field(default=None, ge=1, le=15)
    files: list[TestFile] = Field(default_factory=list, max_length=16)
    commands: list[Command] = Field(min_length=1, max_length=8)
    locations: list[Location] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def aggregate_bounds(self):
        paths = [file.path for file in self.files]
        if len(set(paths)) != len(paths) or any(
            a.startswith(b + "/") for a in paths for b in paths if a != b
        ):
            raise ValueError("duplicate or conflicting test file paths")
        if sum(len(file.content.encode()) for file in self.files) > 131072:
            raise ValueError("test files exceed 128 KiB")
        if sum(len(arg.encode()) for cmd in self.commands for arg in cmd.argv) > 32768:
            raise ValueError("combined argv exceeds 32 KiB")
        if self.parent_revision != (None if self.revision == 1 else self.revision - 1):
            raise ValueError("plan parent must be the preceding revision")
        return self


class PlanAudit(Contract):
    decision: Literal["accepted", "rejected", "insufficient"]
    reasons: list[
        Literal[
            "UNRELATED_TEST",
            "TARGET_CHANGED",
            "ASSERTION_UNSUPPORTED",
            "SOURCE_UNGROUNDED",
            "INSUFFICIENT_CONTEXT",
            "PRIVATE_EVIDENCE_ACCESS",
        ]
    ] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def consistent(self):
        if (self.decision == "accepted") != (not self.reasons):
            raise ValueError("accepted audit has no veto reasons; other decisions need reasons")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("duplicate audit reasons")
        return self


class CommandReceipt(Contract):
    command_digest: Digest
    exec_id: str = Field(min_length=1, max_length=128)
    state: Literal["completed", "timeout", "output_limit", "error"]
    exit_code: int | None = None
    stdout: ArtifactRef
    stderr: ArtifactRef
    truncated: bool = False

    @model_validator(mode="after")
    def completion_status(self):
        if (self.state == "completed") != (self.exit_code is not None):
            raise ValueError("only completed commands have a native exit status")
        return self


class ProcessObservation(Contract):
    operation_id: Identifier
    source_digest: Digest
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_digest: Digest
    container_id: str | None = Field(default=None, max_length=128)
    receipts: list[CommandReceipt] = Field(default_factory=list, max_length=8)
    cleanup_confirmed: bool = False
    outcome: ExecutionOutcome = "INCOMPLETE"
    error: (
        Literal[
            "SETUP_FAILED",
            "IMAGE_CHANGED",
            "EXECUTION_FAILED",
            "TIMEOUT",
            "OUTPUT_LIMIT",
            "CLEANUP_UNCERTAIN",
            "OPERATION_UNCERTAIN",
        ]
        | None
    ) = None
    artifact: ArtifactRef | None = None


class ExecutionRound(Contract):
    plan_artifact: ArtifactRef | None = None
    plan: TestPlan | None = None
    audit: PlanAudit | None = None
    observation: ProcessObservation | None = None
    fixed_observation: ProcessObservation | None = None
    error: str | None = Field(default=None, max_length=128)


class ExecutionResult(Contract):
    schema_version: Literal["corsair.execution-result/3"] = "corsair.execution-result/3"
    run_id: Identifier
    case_id: Identifier
    outcome: ExecutionOutcome = "INCOMPLETE"
    security_assessment: Literal["UNRESOLVED"] = "UNRESOLVED"
    prepared_artifact: ArtifactRef | None = None
    rounds: list[ExecutionRound] = Field(default_factory=list, max_length=16)
    identities: dict[str, Digest] = Field(default_factory=dict, max_length=16)
    usage: Usage = Field(default_factory=Usage)
    error: str | None = Field(default=None, max_length=128)
    result_artifact: ArtifactRef | None = None

    @model_validator(mode="after")
    def serialized_envelope(self):
        if len(self.model_dump_json().encode()) > 1_000_000:
            raise ValueError("execution result exceeds serialized envelope limit")
        return self


class PreparedExecution(Contract):
    run_id: Identifier
    request: ExecutionRequest
    source: ArtifactRef
    fixed_source: ArtifactRef | None = None
    config_digest: Digest
    request_digest: Digest
    resources_digest: Digest
    artifact: ArtifactRef | None = None


class ExecutionRoundInput(Contract):
    prepared: PreparedExecution
    revision: int = Field(ge=1, le=16)
    previous: ExecutionRound | None = None
    llm_limit: int = Field(ge=1, le=32)
    tool_limit: int = Field(ge=0, le=256)
    seconds: int = Field(ge=1, le=3600)


class ExecutionEpisode(Contract):
    plan_artifact: ArtifactRef | None = None
    completion_errors: dict[str, int] = Field(default_factory=dict, max_length=32)
    plan: TestPlan | None = None
    audit: PlanAudit | None = None
    usage: Usage = Field(default_factory=Usage)
    source_paths: list[str] = Field(default_factory=list, max_length=1000)
    error: (
        Literal["MODEL_FAILED", "OUTPUT_INVALID", "SOURCE_UNGROUNDED", "BUDGET_EXHAUSTED"] | None
    ) = None


class AuditEpisodeInput(Contract):
    round: ExecutionRoundInput
    plan: TestPlan


class ExecutePlanInput(Contract):
    prepared: PreparedExecution
    plan: TestPlan
    audit: PlanAudit
    timeout_seconds: int = Field(ge=1, le=3600)
    fixed: bool = False


class ExecutionStart(Contract):
    run_id: Identifier
    request: ExecutionRequest
