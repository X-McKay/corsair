"""Canonical bounded intake contracts; no SDK or execution authority."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import ArtifactRef, Contract, Digest, Identifier, Usage, safe_path
from .sources import Budget, Source

Language = Literal[
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "rust",
    "c",
    "cpp",
    "shell",
    "other",
    "multiple",
    "unknown",
]
ExecutionMode = Literal[
    "callable", "command", "http_service", "application", "static_configuration", "unknown"
]
Requirement = Literal[
    "dependency_install",
    "build",
    "service_start",
    "http_client",
    "external_service",
    "network_access",
    "native_toolchain",
    "browser",
    "privileged_execution",
    "other",
    "unknown",
]
ReasonCode = Literal[
    "OUTSIDE_SCOPE_POLICY",
    "INSUFFICIENT_ISSUE_INFORMATION",
    "MULTIPLE_ISSUES",
    "SOURCE_LOCATION_UNRESOLVED",
    "REQUIREMENTS_UNRESOLVED",
    "IMAGE_UNDETERMINED",
    "NO_COMPATIBLE_IMAGE",
    "LANGUAGE_UNSUPPORTED",
    "EXECUTION_MODE_UNSUPPORTED",
    "TARGET_DEPENDENCIES_UNSUPPORTED",
    "BUILD_UNSUPPORTED",
    "SERVICES_UNSUPPORTED",
    "NETWORK_NOT_PERMITTED",
    "PRIVILEGES_NOT_PERMITTED",
    "REQUIREMENT_UNSUPPORTED",
    "REQUIRED_INPUT_MISSING",
    "IMAGE_NOT_PERMITTED",
    "IMAGE_UNAVAILABLE",
    "IMAGE_INCOMPATIBLE",
]
ErrorCode = Literal[
    "INPUT_INVALID",
    "INPUT_LIMIT_EXCEEDED",
    "ISSUE_FETCH_FAILED",
    "SOURCE_DENIED",
    "INSPECTION_FAILED",
    "MODEL_FAILED",
    "OUTPUT_INVALID",
    "IMAGE_CHECK_FAILED",
]
Classification = Literal["in_scope_supported", "in_scope_not_supported", "out_of_scope"]


class Location(Contract):
    path: str = Field(min_length=1, max_length=240)
    symbol: str | None = Field(default=None, min_length=1, max_length=240)
    _path = field_validator("path")(safe_path)


class Issue(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1, max_length=12000)
    locations: list[Location] = Field(default_factory=list, max_length=16)


def validate_json_payload(value: JsonValue) -> JsonValue:
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 65536:
        raise ValueError("issue JSON exceeds 64 KiB")

    def walk(item: JsonValue, depth: int) -> None:
        if depth > 16:
            raise ValueError("issue JSON exceeds nesting limit")
        if isinstance(item, (dict, list)):
            if len(item) > 256:
                raise ValueError("issue JSON exceeds container entry limit")
            for child in item.values() if isinstance(item, dict) else item:
                walk(child, depth + 1)

    walk(value, 0)
    return value


def parse_issue_json(content: bytes) -> JsonValue:
    if len(content) > 65536:
        raise ValueError("issue JSON exceeds 64 KiB")

    def unique(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate issue JSON key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError("invalid JSON number")

    value = json.loads(content, object_pairs_hook=unique, parse_constant=reject_constant)
    return validate_json_payload(value)


class JsonIssueInput(Contract):
    kind: Literal["json"] = "json"
    payload: JsonValue
    _bounded = field_validator("payload")(validate_json_payload)


class IssueReference(Contract):
    kind: Literal["issue_reference"] = "issue_reference"
    owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    number: int = Field(gt=0, strict=True)


class IntakeRequest(Contract):
    schema_version: Literal["corsair.intake-request/2"] = "corsair.intake-request/2"
    input: Annotated[JsonIssueInput | IssueReference, Field(discriminator="kind")]
    source: Source
    budget: Budget = Field(default_factory=Budget)


class ImageCandidate(Contract):
    reference: str = Field(min_length=1, max_length=240, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$")
    language: Language
    execution_mode: ExecutionMode
    requirements: list[Requirement] = Field(default_factory=list, max_length=11)


class AvailableImage(ImageCandidate):
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ImageInventory(Contract):
    images: list[AvailableImage] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_references(self):
        if len({image.reference for image in self.images}) != len(self.images):
            raise ValueError("duplicate inventory reference")
        return self


class IntakeProposal(Contract):
    issue: Issue = Field(
        description=(
            "A nested JSON object with title, description and locations. "
            "Never a JSON-encoded string. Copy canonical_issue unchanged when supplied."
        )
    )
    scope: Literal["in_scope", "out_of_scope", "unknown"]
    surface: Literal[
        "function", "component", "configuration", "dependency", "application", "unknown"
    ]
    language: Language
    execution_mode: ExecutionMode
    requirements: list[Requirement] = Field(max_length=11)
    suggested_image: str | None = Field(default=None, max_length=240)
    reason_codes: list[ReasonCode] = Field(max_length=32)
    locations: list[Location] = Field(max_length=16)

    @field_validator("requirements", "reason_codes")
    @classmethod
    def unique_categories(cls, value: list):
        if len(value) != len(set(value)):
            raise ValueError("categories must be unique")
        return value


class IntakeDecision(Contract):
    status: Literal["completed", "needs_input", "error"]
    classification: Classification | None = None
    reason_codes: list[ReasonCode] = Field(default_factory=list, max_length=32)
    error_code: ErrorCode | None = None
    image_check: Literal["not_checked", "accepted", "blocked", "unavailable"] = "not_checked"
    image_id: str | None = None

    @model_validator(mode="after")
    def consistent_decision(self):
        if (self.status == "completed") != (self.classification is not None):
            raise ValueError("only completed intake has a classification")
        if (self.status == "error") != (self.error_code is not None):
            raise ValueError("error status requires an error code")
        if self.classification == "in_scope_supported" and (
            self.reason_codes or self.image_check != "accepted" or not self.image_id
        ):
            raise ValueError("supported intake requires accepted image and no blockers")
        return self


class PreparedIntake(Contract):
    run_id: Identifier
    request: IntakeRequest
    source: ArtifactRef
    input_artifact: ArtifactRef
    payload: JsonValue
    inventory: ImageInventory
    config_digest: Digest
    episode_seconds: int | None = Field(default=None, ge=1, le=3600)


class IntakeAgentOutput(Contract):
    source_preloaded: list[str] = Field(default_factory=list, max_length=4)
    inspection_reads: int = Field(default=0, ge=0)
    completion_errors: dict[str, int] = Field(default_factory=dict, max_length=32)
    tool_counts: dict[str, int] = Field(default_factory=dict, max_length=4)
    output_failure: (
        Literal[
            "LLM_BUDGET_EXHAUSTED",
            "TOOL_BUDGET_EXHAUSTED",
            "NO_STRUCTURED_OUTPUT",
            "SCHEMA_INVALID",
            "IMAGE_OUTSIDE_INVENTORY",
            "CANONICAL_ISSUE_MODIFIED",
            "SOURCE_NOT_INSPECTED",
        ]
        | None
    ) = None
    proposal: IntakeProposal | None = None
    usage: Usage = Field(default_factory=Usage)
    error_code: ErrorCode | None = None


class IntakeResult(Contract):
    schema_version: Literal["corsair.intake-result/2"] = "corsair.intake-result/2"
    run_id: Identifier
    decision: IntakeDecision
    proposal: IntakeProposal | None = None
    source: ArtifactRef | None = None
    input_artifact: ArtifactRef | None = None
    inventory: ImageInventory = Field(default_factory=ImageInventory)
    identities: dict[str, Digest] = Field(default_factory=dict, max_length=16)
    usage: Usage = Field(default_factory=Usage)
    inspection_reads: int = Field(default=0, ge=0)
    result_artifact: ArtifactRef | None = None


class IntakeStart(Contract):
    run_id: Identifier
    request: IntakeRequest
