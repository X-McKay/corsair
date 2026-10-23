"""The runtime matrix: operator-owned rows naming the image and framework a tree runs under.

``matrix.yaml`` is the only place trusted code learns which image runs which framework. Selection walks the rows
in file order and returns the first whose detection hints match the vulnerable tree. A language is a row and an
image, not code: the kernel dispatches on ``framework`` for the probe layout it supports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from corsair.domain.case import Case

SCHEMA = "corsair-lite/runtime-matrix/1"
DEFAULT_MATRIX = Path(__file__).with_name("runtime-matrix.yaml")


class Detect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1, max_length=256, description="Glob relative to the tree root")
    contains: str | None = Field(default=None, min_length=1, max_length=256)


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    language: str = Field(min_length=1, max_length=32, description="Reporting only")
    image: str = Field(min_length=1, max_length=512)
    image_source: str | None = Field(default=None, max_length=256)
    framework: str = Field(
        min_length=1, max_length=64, description="A registered adapter in corsair.adapters.frameworks"
    )
    detect: tuple[Detect, ...] = Field(min_length=1)
    evidence: Literal["pilot", "image-only", "live"]
    note: str = Field(default="", max_length=2_000)


class Matrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["corsair-lite/runtime-matrix/1"]
    rows: tuple[Row, ...] = Field(min_length=1)


def load(path: Path = DEFAULT_MATRIX) -> tuple[Row, ...]:
    matrix = Matrix.model_validate(yaml.safe_load(Path(path).read_text()))
    ids = [row.id for row in matrix.rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate matrix row ids in {path}")
    return matrix.rows


def _matches(root: Path, hint: Detect) -> bool:
    for candidate in sorted(root.glob(hint.file)):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        if hint.contains is None:
            return True
        try:
            if hint.contains in candidate.read_text(errors="replace"):
                return True
        except OSError:
            continue
    return False


def detects(row: Row, root: Path) -> bool:
    return any(_matches(root, hint) for hint in row.detect)


def select(case: Case, matrix: Path = DEFAULT_MATRIX) -> Row | None:
    """The first row whose hints match the vulnerable tree, or None (no runtime: the case is UNABLE_TO_RUN)."""
    root = Path(case.revision.source)
    if not root.is_dir():
        return None
    suffix = Path(case.finding.file_path or "").suffix.lower()
    languages = {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".pl": "perl",
        ".pm": "perl",
        ".rb": "ruby",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "cpp",
        ".hpp": "cpp",
        ".h": "cpp",
    }
    target_language = languages.get(suffix)
    rows = load(matrix)
    for row in rows:
        if target_language is not None and row.language != target_language:
            continue
        if detects(row, root):
            return row
    return None
