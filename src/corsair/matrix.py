"""The Select stage: one runtime matrix row per (image, framework), chosen by manifest lookup (redesign section 6).

The matrix (``deploy/v2/runtime-matrix.yaml``) is operator-owned data and the only place trusted code learns how
to run one test for a framework. Selection walks the rows in file order and returns the first whose detection
hints match the revision tree: a manifest file name (a glob relative to the tree root) and, optionally, a
substring that file must contain. Nothing here branches on a language; ``language`` is carried for reports only.

A row's ``evidence`` is ``canary-only`` until its two canaries (``tools/v2_canary.py``) classify as ``passed``
and ``assertion_failed`` on its image; only then is it ``image-only``. Selection skips ``canary-only`` rows by
default, because an unchecked exit-code map or run template could turn a broken run into a decisive outcome.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .contracts import Case, ExitClass, Runtime

SCHEMA = "corsair-v2/runtime-matrix/1"
DEFAULT_MATRIX = Path(__file__).resolve().parents[2] / "deploy/v2/runtime-matrix.yaml"


class Detect(BaseModel):
    """A row matches a tree when any one of its hints matches: a file glob, and optionally text that file holds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1, max_length=256, description="Glob relative to the tree root, e.g. t/*.t")
    contains: str | None = Field(default=None, min_length=1, max_length=256)


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,127}$")
    language: str = Field(min_length=1, max_length=32, description="Reporting only; never read by a code path")
    image: str = Field(min_length=1, max_length=512)
    base_image: str | None = Field(default=None, max_length=512, description="Digest-pinned upstream base")
    image_source: str | None = Field(default=None, max_length=256)
    framework: str = Field(min_length=1, max_length=64)
    skill: str = Field(min_length=1, max_length=64)
    detect: tuple[Detect, ...] = Field(min_length=1)
    run_template: tuple[str, ...] = Field(min_length=1)
    exit_codes: dict[int, ExitClass] = Field(min_length=1)
    test_dir: str = Field(default="", max_length=256)
    evidence: Literal["canary-only", "image-only", "live"]
    build_network_hosts: tuple[str, ...] = ()
    canary_setup: tuple[str, ...] = Field(default=(), description="argv run before each canary, offline; canary only")
    syntax_check: tuple[str, ...] | None = Field(
        default=None, min_length=1, description="argv template checking a probe file without running application "
                                                "code (D3 feedback); omitted where the check could run code")
    note: str = Field(default="", max_length=2_000)

    def runtime(self) -> Runtime:
        return Runtime(row_id=self.id, image=self.image, framework=self.framework, skill=self.skill,
                       run_template=self.run_template, exit_codes=self.exit_codes, test_dir=self.test_dir,
                       evidence=self.evidence, syntax_check=self.syntax_check)


class Matrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["corsair-v2/runtime-matrix/1"]
    rows: tuple[Row, ...] = Field(min_length=1)


def load(path: Path = DEFAULT_MATRIX) -> tuple[Row, ...]:
    """Every row, in file order, validated; duplicate ids are refused."""
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
    """Whether any of the row's hints matches the tree at ``root``."""
    return any(_matches(root, hint) for hint in row.detect)


def select(case: Case, matrix: Path = DEFAULT_MATRIX, *, include_unchecked: bool = False) -> Runtime | None:
    """The first admitted row whose hints match the vulnerable revision's tree, or None (rule R0, ``no_runtime``).

    ``include_unchecked`` also considers ``canary-only`` rows; only the canary tool and tests should set it.
    """
    root = Path(case.revision.source)
    if not root.is_dir():
        return None
    for row in load(matrix):
        if row.evidence == "canary-only" and not include_unchecked:
            continue
        if detects(row, root):
            return row.runtime()
    return None


def fill(template: tuple[str, ...], *, test_file: str, test_name: str) -> tuple[str, ...]:
    """The run template with its placeholders filled, as Execute fills it.

    ``{file}`` is the test file, ``{name}`` the test name, ``{class}`` the file's stem and ``{module}`` the file's
    path without its extension, dotted. Only these four are known; any other brace field raises KeyError.
    """
    path = Path(test_file)
    values = {"file": test_file, "name": test_name, "class": path.stem,
              "module": ".".join(path.with_suffix("").parts)}
    return tuple(part.format_map(values) for part in template)
