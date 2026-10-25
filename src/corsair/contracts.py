"""The canonical wire contracts. Agents propose inputs; only trusted code creates evidence."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    field_validator,
    model_validator,
)

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def digest(value: BaseModel | dict | list | str | bytes) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if not isinstance(value, bytes):
        value = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    return hashlib.sha256(value).hexdigest()


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {".", "..", ""} for part in value.split("/"))
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("expected a normalized relative POSIX path")
    return value


class ArtifactRef(Contract):
    sha256: Digest
    size: int = Field(ge=0)
    media_type: str = "application/json"


class Source(Contract):
    """An admitted local source tree, snapshotted before any agent invocation."""

    path: str = Field(min_length=1)
    expected_digest: Digest | None = None


class Scope(StrEnum):
    COMPONENT = "component"
    APPLICATION = "application"


class Finding(Contract):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=12000)
    file: str
    line: int | None = Field(default=None, ge=1)
    claim_scope: Scope = Scope.COMPONENT

    _safe_file = field_validator("file")(safe_path)


class PythonRecipe(Contract):
    """Operator-owned secret-disclosure check at a Python callable's real API.

    The investigator controls ONLY the value of payload_parameter. Fixed keyword
    arguments, fixtures, expected benign value, and exception policy are not editable.
    The private fixture's actual random content never appears in an agent prompt.
    """

    kind: Literal["python.secret_disclosure/1"] = "python.secret_disclosure/1"
    module_file: str
    function: str
    payload_parameter: str
    fixed_kwargs: dict[str, JsonValue] = Field(default_factory=dict)
    public_files: dict[str, str] = Field(default_factory=lambda: {"hello.txt": "hello"})
    expected_control: JsonValue = "hello"
    allowed_exceptions: list[str] = Field(default_factory=lambda: ["builtins.ValueError"])

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def python_file(cls, value: str) -> str:
        if not value.endswith(".py"):
            raise ValueError("the initial recipe supports Python source files only")
        return value

    @field_validator("function", "payload_parameter")
    @classmethod
    def identifier(cls, value: str) -> str:
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("expected a public Python identifier")
        return value

    @field_validator("fixed_kwargs")
    @classmethod
    def keyword_arguments(cls, value: dict) -> dict:
        if len(value) > 16 or any(not key.isidentifier() for key in value):
            raise ValueError("invalid fixed keyword arguments")
        if len(json.dumps(value)) > 16000:
            raise ValueError("fixed arguments exceed the recipe limit")
        return value

    @field_validator("public_files")
    @classmethod
    def fixtures(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 16 or sum(len(text.encode()) for text in value.values()) > 65536:
            raise ValueError("public fixtures exceed the recipe limit")
        for name in value:
            safe_path(name)
        return value

    @field_validator("allowed_exceptions")
    @classmethod
    def exceptions(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z][\w]*(\.[A-Za-z][\w]*)+", item) for item in value):
            raise ValueError("exceptions must have fully qualified names")
        return value

    @model_validator(mode="after")
    def payload_not_fixed(self):
        if self.payload_parameter in self.fixed_kwargs:
            raise ValueError("payload_parameter may not override an operator-fixed argument")
        return self


class Case(Contract):
    schema_version: Literal["corsair.case/1"] = "corsair.case/1"
    case_id: Identifier
    finding: Finding
    source: Source
    recipe: PythonRecipe
    fixed_source: Source | None = None

    @model_validator(mode="after")
    def bind_recipe(self):
        if self.finding.file != self.recipe.module_file:
            raise ValueError("the recipe must bind to the original finding's file")
        return self


class Budget(Contract):
    max_rounds: int = Field(default=3, ge=1, le=16)
    max_llm_calls: int = Field(default=16, ge=2, le=128)
    episode_llm_calls: int = Field(default=4, ge=1, le=32)
    max_tool_calls: int = Field(default=24, ge=1, le=256)
    max_output_tokens: int = Field(default=4096, ge=256, le=16384)
    max_elapsed_seconds: int = Field(default=900, ge=30, le=3600)
    probe_timeout_seconds: int = Field(default=30, ge=1, le=300)
    tool_output_bytes: int = Field(default=32768, ge=1024, le=131072)


class InvestigationRequest(Contract):
    case: Case
    budget: Budget = Field(default_factory=Budget)


class RunManifest(Contract):
    schema_version: Literal["corsair.manifest/1"] = "corsair.manifest/1"
    package_version: str
    request_digest: Digest
    config_digest: Digest
    producer_prompt_digest: Digest
    auditor_prompt_digest: Digest
    image_id: str
    models: dict[str, str]
    capabilities: dict[str, dict] = Field(default_factory=dict)


class PreparedCase(Contract):
    case_id: Identifier
    finding: Finding
    recipe: PythonRecipe
    source: ArtifactRef
    fixed_source: ArtifactRef | None = None
    source_excerpt: str
    manifest: RunManifest


class PlanRevision(Contract):
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    objective: str = Field(min_length=1, max_length=1000)
    next_steps: list[str] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=2000)


class Submission(Contract):
    schema_version: Literal["corsair.submission/1"] = "corsair.submission/1"
    control_payload: JsonValue
    exploit_payload: JsonValue
    hypothesis: str = Field(min_length=1, max_length=4000)
    plan: PlanRevision

    @model_validator(mode="after")
    def bounded_payloads(self):
        if len(json.dumps([self.control_payload, self.exploit_payload]).encode()) > 32768:
            raise ValueError("payloads exceed the submission limit")
        return self


class Usage(Contract):
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    seconds: float = Field(default=0, ge=0)


class Feedback(Contract):
    gate: str
    reason: str
    operational: StrictBool = False


class ProducerInput(Contract):
    run_id: Identifier
    prepared: PreparedCase
    budget: Budget
    round_index: int = Field(ge=1)
    previous: Submission | None = None
    feedback: Feedback | None = None
    llm_call_limit: int = Field(ge=1)
    tool_call_limit: int = Field(ge=1)


class ProducerOutput(Contract):
    submission: Submission | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None


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


class AuditDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    INSUFFICIENT = "INSUFFICIENT_CONTEXT"


class AuditResult(Contract):
    decision: AuditDecision
    rule: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


class AuditInput(Contract):
    finding: Finding
    recipe: PythonRecipe
    source_excerpt: str
    submission: Submission
    max_output_tokens: int = Field(ge=256, le=16384)


class AuditOutput(Contract):
    review: AuditResult | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None


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


class BatchRequest(Contract):
    batch_id: Identifier
    requests: list[InvestigationRequest] = Field(min_length=1, max_length=64)
    repeats: int = Field(default=1, ge=1, le=8)
    concurrency: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def bounded_history_payload(self):
        if len(self.model_dump_json().encode()) > 1_000_000:
            raise ValueError("batch payload exceeds 1 MB; split the dataset into finite batches")
        if len(self.batch_id) > 60:
            raise ValueError("batch identity must leave space for child identifiers")
        return self


class BatchItem(Contract):
    case_id: Identifier
    run_id: Identifier
    artifact: ArtifactRef | None = None
    error: str | None = None
