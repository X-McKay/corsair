"""Versioned Corsair data. No orchestrator, provider, or sandbox SDK objects."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def confined_path(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or str(path) != value or "\\" in value
            or any(p in ("", ".", "..", ".git") for p in path.parts)
            or any(ord(c) < 32 or ord(c) == 127 for c in value) or len(value.encode()) > 1024):
        raise ValueError("A canonical, confined repository-relative path is required")
    return value


class ArtifactRef(Contract):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0, le=268435456)


class SourceFile(Contract):
    path: str
    artifact: ArtifactRef
    mode: Literal["100644", "100755"] = "100644"
    _path = field_validator("path")(confined_path)


class SourceSnapshot(Contract):
    schema_version: Literal["source-v2"] = "source-v2"
    repository: str
    commit: str | None = None
    tree: str | None = None
    files: tuple[SourceFile, ...]
    manifest: ArtifactRef
    skipped: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_paths(self):
        paths = [f.path for f in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate source paths")
        return self


class SourceRequest(Contract):
    path: str
    commit: str | None = None
    candidate_path: str | None = None
    candidate_commit: str | None = None
    max_files: int = Field(default=10000, ge=1, le=65536)
    max_bytes: int = Field(default=32 * 1024 * 1024, ge=1, le=256 * 1024 * 1024)
    max_file_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=16 * 1024 * 1024)

    @field_validator("commit", "candidate_commit")
    @classmethod
    def exact_commit(cls, value):
        if value is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
            raise ValueError("Use an exact Git commit, not a branch or tag")
        return value

    @model_validator(mode="after")
    def candidate_identity(self):
        if self.candidate_commit and not self.commit:
            raise ValueError("A candidate commit requires an exact baseline commit")
        return self


class Budget(Contract):
    request_limit: int = Field(default=24, ge=1, le=256)
    tool_calls_limit: int = Field(default=48, ge=1, le=512)
    input_tokens_limit: int = Field(default=100000, ge=1, le=2000000)
    output_tokens_limit: int = Field(default=20000, ge=1, le=200000)
    stage_timeout_seconds: int = Field(default=240, ge=5, le=1800)
    episode_timeout_seconds: int = Field(default=1800, ge=30, le=14400)
    command_timeout_seconds: int = Field(default=120, ge=1, le=900)
    max_output_bytes: int = Field(default=1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    max_plan_revisions: int = Field(default=1, ge=0, le=5)


class ModelProfile(Contract):
    model: str
    provider: Literal["openai", "openai-compatible", "ollama", "bedrock"] = "openai-compatible"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def no_embedded_credentials(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment):
                raise ValueError("A credential-free HTTP(S) model endpoint is required")
        return value

    @model_validator(mode="after")
    def explicit_ollama_endpoint(self):
        if self.provider == "ollama" and self.base_url is None:
            raise ValueError("An explicit Ollama base_url is required")
        return self


class SandboxProfile(Contract):
    name: str = "openshell-local"
    image: str
    policy_path: str
    toolchain: dict[str, str] = Field(default_factory=dict, max_length=32)
    workspace: str = "default"
    workspace_root: str = "/workspace"
    gateway: str | None = Field(default=None, min_length=1, max_length=128,
                                pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    cli_path: str | None = None
    qualification_path: str | None = None
    readiness_timeout_seconds: int = Field(default=120, ge=5, le=600)
    memory_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=128 * 1024 * 1024, le=32 * 1024 * 1024 * 1024)

    @field_validator("image")
    @classmethod
    def pinned_image(cls, value):
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", value):
            raise ValueError("An OCI image pinned by sha256 digest is required")
        return value

    @field_validator("toolchain")
    @classmethod
    def bounded_toolchain(cls, values):
        if any(not re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}", key) or len(value) > 512 for key, value in values.items()):
            raise ValueError("Toolchain metadata requires bounded tool names and descriptions")
        return values

    @field_validator("workspace_root")
    @classmethod
    def isolated_root(cls, value):
        if not value.startswith("/") or value in ("/", "/home", "/root", "/tmp") or ".." in value.split("/"):
            raise ValueError("Use an explicit isolated sandbox workspace root")
        return value


class OperatorConfig(Contract):
    schema_version: Literal["operator-v2"] = "operator-v2"
    storage_root: str
    default_model: ModelProfile
    role_models: dict[str, ModelProfile] = Field(default_factory=dict)
    sandbox: SandboxProfile
    budget: Budget = Field(default_factory=Budget)
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    temporal_tls: bool = False
    temporal_api_key_env: str | None = None
    task_queue: str = Field(default="corsair-v2", min_length=1, max_length=128)
    capture_content: bool = False
    otlp_endpoint: str | None = None

    @field_validator("role_models")
    @classmethod
    def known_roles(cls, value):
        if set(value) - {"analysis", "investigator", "control_author", "exploit_author", "validity", "repair"}:
            raise ValueError("Unknown agent role")
        return value

    def model_for(self, role: str) -> ModelProfile:
        return self.role_models.get(role, self.default_model)

    @model_validator(mode="after")
    def authenticated_temporal_requires_tls(self):
        if self.temporal_api_key_env and not self.temporal_tls:
            raise ValueError("Temporal API-key authentication requires TLS")
        return self


class RunSpec(Contract):
    schema_version: Literal["run-v2"] = "run-v2"
    request_id: str = Field(min_length=1, max_length=128)
    source: SourceRequest
    concern: str = Field(min_length=1, max_length=32768)
    language: str = "unknown"
    framework: str = "unknown"
    cwe: tuple[str, ...] = ()
    generate_repair: bool = False
    allowed_repair_paths: tuple[str, ...] = ()

    @field_validator("allowed_repair_paths")
    @classmethod
    def repair_paths(cls, values):
        return tuple(confined_path(v) for v in values)

    @model_validator(mode="after")
    def repair_authority(self):
        if self.generate_repair and not self.allowed_repair_paths:
            raise ValueError("Generated repairs require explicit permitted source paths")
        if self.generate_repair and (self.source.candidate_path or self.source.candidate_commit):
            raise ValueError("Choose a supplied candidate or a generated repair, not both")
        return self


class Citation(Contract):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    _path = field_validator("path")(confined_path)

    @model_validator(mode="after")
    def ordered_lines(self):
        if self.end_line < self.start_line:
            raise ValueError("Citation line range is reversed")
        return self


class ReportSelector(Contract):
    name: str = Field(min_length=1, max_length=256)
    classname: str = Field(default="", max_length=512)


class ProbeSpec(Contract):
    role: Literal["control", "security"]
    path: str
    test_id: str = Field(min_length=1, max_length=512)
    selector: ReportSelector
    objective: str = Field(min_length=1, max_length=4096)
    input_description: str = Field(min_length=1, max_length=4096)
    expected_safe_behavior: str = Field(min_length=1, max_length=4096)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=16)
    _path = field_validator("path")(confined_path)


class TestRecipe(Contract):
    report_format: Literal["junit", "jest", "tap", "minitest-json"]
    discovery_format: Literal["lines", "pytest", "junit-xml", "jest-json", "ctest-json"] = "lines"
    setup_commands: tuple[tuple[str, ...], ...] = ()
    discovery_command: tuple[str, ...]
    execution_command: tuple[str, ...]
    report_path: str
    regression_commands: tuple[tuple[str, ...], ...] = ()
    _report_path = field_validator("report_path")(confined_path)

    @model_validator(mode="after")
    def bounded_argv(self):
        commands = (*self.setup_commands, self.discovery_command, self.execution_command, *self.regression_commands)
        if len(commands) > 24:
            raise ValueError("Command count exceeds plan limit")
        for command in commands:
            if not command or len(command) > 128 or any(not t or "\0" in t or len(t) > 8192 for t in command):
                raise ValueError("Commands require bounded nonempty argv tokens")
        return self


class InvestigationPlan(Contract):
    status: Literal["planned", "unsupported", "inconclusive"]
    summary: str = Field(min_length=1, max_length=4096)
    target_citations: tuple[Citation, ...] = ()
    control: ProbeSpec | None = None
    security: ProbeSpec | None = None
    recipe: TestRecipe | None = None
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def complete_pair(self):
        if self.status == "planned":
            if not self.control or not self.security or not self.recipe or not self.target_citations:
                raise ValueError("A planned investigation needs source citations and both native probes")
            if self.control.role != "control" or self.security.role != "security":
                raise ValueError("Control and security roles are reversed")
            if self.control.path == self.security.path or self.control.test_id == self.security.test_id:
                raise ValueError("Independent probes require distinct assigned files and test identities")
        return self


class ProbeDraft(Contract):
    status: Literal["drafted", "blocked"]
    path: str
    content: str = Field(max_length=65536)
    rationale: str = Field(max_length=4096)
    _path = field_validator("path")(confined_path)

    @model_validator(mode="after")
    def actual_draft(self):
        if self.status == "drafted" and not self.content.strip():
            raise ValueError("An admitted draft needs actual test source")
        return self


class ProbeValidity(Contract):
    source_binding: bool
    reaches_condition: bool
    relevant_assertion: bool
    doubles_preserve_production_logic: bool
    citations: tuple[Citation, ...] = ()
    rationale: str = Field(min_length=1, max_length=4096)

    @property
    def valid(self) -> bool:
        return (self.source_binding and self.reaches_condition and self.relevant_assertion
                and self.doubles_preserve_production_logic and bool(self.citations))


class ValidityReview(Contract):
    control: ProbeValidity
    security: ProbeValidity
    recipe_valid: bool = False
    recipe_rationale: str = Field(default="", max_length=4096)
    limitations: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.control.valid and self.security.valid and self.recipe_valid and bool(self.recipe_rationale.strip())


class RepairDraft(Contract):
    status: Literal["proposed", "blocked"]
    files: dict[str, str]
    rationale: str = Field(min_length=1, max_length=4096)

    @field_validator("files")
    @classmethod
    def confined_files(cls, value):
        if len(value) > 16 or sum(len(c.encode()) for c in value.values()) > 256 * 1024:
            raise ValueError("Repair is outside the file/byte envelope")
        for path in value:
            confined_path(path)
        return value


class WorkspaceLease(Contract):
    name: str
    sandbox_id: str
    run_id: str
    generation: int = Field(ge=1)
    image: str
    policy_sha256: str


class CommandResult(Contract):
    operation_id: str
    sandbox_id: str
    status: Literal["completed", "unknown", "not_dispatched", "timeout", "output_limit", "policy_denied"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_ref: ArtifactRef | None = None
    stderr_ref: ArtifactRef | None = None
    duration_seconds: float = Field(ge=0)
    detail: str = ""


class ProbeObservation(Contract):
    test_id: str
    outcome: Literal["passed", "failed", "error", "skipped"]
    failure_type: str | None = None
    detail: str = ""


class RevisionExecution(Contract):
    revision: Literal["baseline", "candidate"]
    source_manifest: ArtifactRef
    pair_sha256: str
    image: str
    policy_sha256: str
    sandbox_id: str
    discovery_ok: bool
    observations: tuple[ProbeObservation, ...] = ()
    execution_status: Literal["completed", "unknown", "blocked", "invalid_report"]
    commands: tuple[CommandResult, ...] = ()
    report_ref: ArtifactRef | None = None
    cleanup: Literal["confirmed", "pending", "unknown"]
    regression_passed: bool | None = None
    detail: str = ""


class StageMetrics(Contract):
    role: str
    model: str
    latency_seconds: float = Field(ge=0)
    requests: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    field_availability: dict[str, Literal["reported", "reported_zero", "not_reported", "not_applicable", "unknown"]] = Field(default_factory=dict)
    usage_details: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "failed", "budget_exhausted", "cancelled"]
    error: str | None = None
    trajectory: tuple[dict[str, Any], ...] = ()


class AgentResult(Contract):
    role: str
    output: dict[str, Any] | None
    metrics: StageMetrics
    output_ref: ArtifactRef | None = None


class Verdict(Contract):
    status: Literal["confirmed_finding", "verified_repair", "unknown_absence", "inconclusive", "unsupported", "unqualified", "cancelled", "failed_platform"]
    reason: str
    rule_id: str
    summary: str
    scope: str = "Source-reviewed native unit-probe evidence; no production reachability claim."
    limitations: tuple[str, ...] = ()


class RunResult(Contract):
    schema_version: Literal["result-v2"] = "result-v2"
    run_id: str
    spec_sha256: str
    config_sha256: str
    source: SourceSnapshot | None = None
    candidate: SourceSnapshot | None = None
    plan_ref: ArtifactRef | None = None
    pair_ref: ArtifactRef | None = None
    validity_ref: ArtifactRef | None = None
    stages: tuple[AgentResult, ...] = ()
    revisions: tuple[RevisionExecution, ...] = ()
    verdict: Verdict
    qualification: Literal["qualified", "unqualified"]
    cleanup: Literal["confirmed", "pending", "unknown", "not_acquired"]
    duration_seconds: float = Field(ge=0)
    evidence_ref: ArtifactRef | None = None
    report_ref: ArtifactRef | None = None


class AnalysisInput(Contract):
    """Public benchmark source context only. Expected labels belong to Case metadata."""
    concern: str = Field(default="Assess the supplied source for a security flaw.", max_length=32768)
    files: dict[str, str]
    language: str = "unknown"
    framework: str = "unknown"
    cwe: tuple[str, ...] = ()

    @field_validator("files")
    @classmethod
    def bounded_source(cls, values):
        if not values or len(values) > 128 or sum(len(v.encode()) for v in values.values()) > 256 * 1024:
            raise ValueError("Use a nonempty bounded source slice")
        for path in values:
            confined_path(path)
        return values


class SourceAssessment(Contract):
    """A model prediction, never an executed or conclusive disposition."""
    prediction: Literal["vulnerable", "safe_in_scope", "unknown"]
    rationale: str = Field(min_length=1, max_length=4096)
    citations: tuple[Citation, ...] = ()
    limitations: tuple[str, ...] = ()


class AnalysisResult(Contract):
    schema_version: Literal["analysis-result-v2"] = "analysis-result-v2"
    assessment: SourceAssessment | None
    metrics: StageMetrics
    output_ref: ArtifactRef | None = None
    mode: Literal["source_only"] = "source_only"
