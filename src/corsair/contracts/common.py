"""Canonical common wire contracts; no vendor SDK types."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]
# A root run identity must leave room for the operation suffixes (".r<n>",
# ".fix<n>", and a ".s<n>" prefix for a later independent session) that are
# appended to form an EvidenceInput.operation_id, which shares the 80-character
# Identifier bound.
MAX_ROOT_IDENTIFIER_LENGTH = 60
MAX_DIAGNOSTIC_TEXT_CHARS = 4096
DIAGNOSTIC_TRUNCATION_MARKER = " … [diagnostic truncated]"
DiagnosticText = Annotated[str, Field(max_length=MAX_DIAGNOSTIC_TEXT_CHARS)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def validate_root_identity(value: str) -> str:
    """Validate a root run identity and reserve operation-suffix headroom.

    Used at every submission boundary (the Python API and the CLI) so an
    over-long identity is rejected before any work is spent, rather than failing
    later when an operation suffix overflows the Identifier bound.
    """
    from pydantic import TypeAdapter

    identity = TypeAdapter(Identifier).validate_python(value)
    if len(identity) > MAX_ROOT_IDENTIFIER_LENGTH:
        raise ValueError("run identity must leave space for operation suffixes")
    return identity


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


# Per-call telemetry lists keep at most this many entries each; beyond it only the
# episode totals grow and ``Usage.calls_truncated`` is set, which keeps a saved
# result inside its size cap however long an episode runs.
MAX_USAGE_CALL_ENTRIES = 64


class ModelCall(Contract):
    """One dispatched model request, as the provider reported it.

    ``index`` is the 1-based dispatch ordinal within the episode.  A count the
    provider did not report is ``None``, never 0.  ``cached_input_tokens`` is
    recorded only when the provider reports a positive count, because ADK's LiteLLM
    route reports an absent cache figure as 0.  ``output_tokens`` is the provider's
    candidate count exactly as reported: on OpenAI-compatible routes it already
    includes reasoning tokens, on ADK's native Gemini route it excludes them, and
    ``thought_tokens`` is never added to it.  ``seconds`` spans dispatch to the
    complete response.
    """

    index: int = Field(ge=1)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    seconds: float = Field(ge=0)


class ToolCall(Contract):
    """One native tool call admitted by the episode's tool budget.

    ``index`` is the 1-based admission ordinal.  ``result_bytes`` is the size of the
    tool's response as compact JSON and ``truncated`` is whether the tool itself
    reported a truncated result.  ``seconds`` spans admission to the response.
    """

    index: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    result_bytes: int = Field(ge=0)
    truncated: StrictBool
    seconds: float = Field(ge=0)


class Usage(Contract):
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    skills_loaded: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=2
    )
    skills_preloaded: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=2
    )
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    seconds: float = Field(default=0, ge=0)
    # Telemetry added after results were first saved; every field defaults so those
    # results still decode.  Totals sum the per-call reports and stay ``None`` when
    # no call reported a value (see ``ModelCall`` for the cached and thought rules).
    cached_input_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    model_calls: list[ModelCall] = Field(default_factory=list, max_length=MAX_USAGE_CALL_ENTRIES)
    tool_calls_detail: list[ToolCall] = Field(
        default_factory=list, max_length=MAX_USAGE_CALL_ENTRIES
    )
    calls_truncated: StrictBool = False

    @field_validator("skills_loaded", "skills_preloaded")
    @classmethod
    def unique_skill_names(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("loaded skill names must be unique")
        return value


class Feedback(Contract):
    gate: str = Field(max_length=128)
    reason: DiagnosticText
    operational: StrictBool = False
