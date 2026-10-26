"""Canonical sources wire contracts; no vendor SDK types."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import ArtifactRef, Contract, Digest, Identifier, safe_path


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
    # The admitted evidence policy, fixed when the case is prepared and replayed
    # from history: independent clean negatives required for
    # EXPLOIT_NOT_DEMONSTRATED, and the cap on independent producer sessions.
    negative_threshold: int = Field(default=2, ge=2, le=8)
    max_sessions: int = Field(default=2, ge=1, le=8)


class PreparedCase(Contract):
    case_id: Identifier
    finding: Finding
    recipe: PythonRecipe
    source: ArtifactRef
    fixed_source: ArtifactRef | None = None
    source_excerpt: str
    manifest: RunManifest
