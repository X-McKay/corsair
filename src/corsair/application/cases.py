"""Case-request parsing and evaluator-only oracle loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from corsair.domain.case import Case, Finding, GitSource, Revision, revision
from corsair.ports.scm import SourceControl


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    finding: Finding
    source: str | GitSource = Field(description="A directory relative to this file, or a pinned git source")
    commit: str | None = None
    fixed_source: str | GitSource | None = None
    fixed_commit: str | None = None


def from_request(path: Path, *, scm: SourceControl | None = None) -> Case:
    """Load ``input.json`` without allowing evaluator-only oracle data into a ``Case``."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    request = _Request.model_validate_json(raw)
    base = path.parent

    def resolve(spec: str | GitSource, commit: str | None) -> Revision:
        if isinstance(spec, GitSource):
            if scm is None:
                raise ValueError("a SourceControl dependency is required for a GitSource")
            return revision(scm.acquire(spec), spec.commit)
        return revision(base / spec, commit)

    fixed = resolve(request.fixed_source, request.fixed_commit) if request.fixed_source else None
    return Case(
        case_id=request.case_id or f"issue:{hashlib.sha256(raw).hexdigest()[:16]}",
        finding=request.finding,
        revision=resolve(request.source, request.commit),
        fixed_revision=fixed,
    )


def load_case(path: Path, *, scm: SourceControl | None = None) -> Case:
    """Load a request file or a case directory holding ``input.json``."""
    path = Path(path)
    return from_request(path / "input.json" if path.is_dir() else path, scm=scm)


def load_oracle(path: Path) -> dict | None:
    """Load evaluator-only truth beside a case directory; it never enters a ``Case``."""
    path = Path(path)
    oracle = (path if path.is_dir() else path.parent) / "oracle.json"
    return json.loads(oracle.read_text()) if oracle.is_file() else None
