"""Canonical common wire contracts; no vendor SDK types."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]
MAX_DIAGNOSTIC_TEXT_CHARS = 4096
DIAGNOSTIC_TRUNCATION_MARKER = " … [diagnostic truncated]"
DiagnosticText = Annotated[str, Field(max_length=MAX_DIAGNOSTIC_TEXT_CHARS)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def format_diagnostic(value: str) -> str:
    """Keep optional wire diagnostics concise without changing structured facts."""
    if len(value) <= MAX_DIAGNOSTIC_TEXT_CHARS:
        return value
    prefix_length = MAX_DIAGNOSTIC_TEXT_CHARS - len(DIAGNOSTIC_TRUNCATION_MARKER)
    return f"{value[:prefix_length]}{DIAGNOSTIC_TRUNCATION_MARKER}"


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


class Usage(Contract):
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    seconds: float = Field(default=0, ge=0)


class Feedback(Contract):
    gate: str = Field(max_length=128)
    reason: DiagnosticText
    operational: StrictBool = False
