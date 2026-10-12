"""Saved-source inventory and citation contracts shared by read-only stages; no SDK types."""

from pathlib import PurePosixPath
from typing import Annotated, TypeVar

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


def bounded_inventory(source_files: tuple[SourceFile, ...]) -> None:
    """SPEC-0014 inventory limits: unique paths and at most 65536 UTF-8 bytes in total."""
    if len({source.path for source in source_files}) != len(source_files):
        raise ValueError("duplicate fixture source path")
    if sum(len(source.content.encode("utf-8")) for source in source_files) > 65536:
        raise ValueError("fixture source exceeds 65536 bytes")


class SourceReference(Contract):
    path: str = Field(min_length=1, max_length=256)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    _path = field_validator("path")(confined_path)

    @model_validator(mode="after")
    def ordered_range(self) -> "SourceReference":
        if self.end_line < self.start_line:
            raise ValueError("inverted source line range")
        return self


class SourceExcerpt(SourceReference):
    quote: str = Field(min_length=1, max_length=16384)


class SourceLine(Contract):
    number: int = Field(ge=1)
    text: str = Field(max_length=16384)


class SourceRead(SourceReference):
    lines: tuple[SourceLine, ...] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def complete_numbered_range(self) -> "SourceRead":
        if (len(self.lines) != self.end_line - self.start_line + 1
                or any(line.number != self.start_line + offset for offset, line in enumerate(self.lines))):
            raise ValueError("source lines must cover the declared range in order")
        return self


Fact = Annotated[str, Field(min_length=1, max_length=2048)]


Citation = TypeVar("Citation", bound=SourceReference)
