"""Saved fixture stage contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def confined_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or not path.parts or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("expected a confined relative POSIX fixture path")
    if str(path) != value or any(ord(char) < 32 for char in value):
        raise ValueError("expected a canonical fixture path")
    return value


class SourceFile(Contract):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=16384)

    _path = field_validator("path")(confined_path)


class IssueAnalysisInput(Contract):
    fixture_id: str = Field(min_length=1, max_length=128)
    issue: str = Field(min_length=1, max_length=8192)
    scope: Literal["component", "application_path"]
    source_files: tuple[SourceFile, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def bounded_unique_source(self) -> "IssueAnalysisInput":
        if len({source.path for source in self.source_files}) != len(self.source_files):
            raise ValueError("duplicate fixture source path")
        if sum(len(source.content.encode("utf-8")) for source in self.source_files) > 65536:
            raise ValueError("fixture source exceeds 65536 bytes")
        return self

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class SourceExcerpt(Contract):
    path: str = Field(min_length=1, max_length=256)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=16384)

    _path = field_validator("path")(confined_path)

    @model_validator(mode="after")
    def ordered_range(self) -> "SourceExcerpt":
        if self.end_line < self.start_line:
            raise ValueError("inverted source line range")
        return self


Fact = Annotated[str, Field(min_length=1, max_length=2048)]


class Hypothesis(Contract):
    entry_point: Fact
    attacker_input: Fact
    attacker_capabilities: Fact
    preconditions: tuple[Fact, ...] = Field(min_length=1, max_length=16)
    sensitive_operation: Fact
    observable_effect: Fact


class IssueAnalysis(Contract):
    status: Literal["ready", "missing_information", "unsupported"]
    scope: Literal["component", "application_path"]
    hypothesis: Hypothesis | None
    citations: tuple[SourceExcerpt, ...] = Field(max_length=16)
    missing_facts: tuple[Fact, ...] = Field(max_length=16)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def status_matches_evidence(self) -> "IssueAnalysis":
        if self.status == "ready":
            if self.hypothesis is None or not self.citations or self.missing_facts:
                raise ValueError("ready requires a cited hypothesis and no missing required facts")
        elif self.hypothesis is not None or not self.missing_facts:
            raise ValueError("incomplete analysis requires missing facts and no ready hypothesis")
        return self
