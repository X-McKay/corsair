"""A case: one reported issue against an exact source tree, optionally with its fix tree.

Agents read the finding as data, never as instructions. Scoring truth (``oracle.json``) is loaded separately by
``load_oracle`` for evaluators only and can never enter a ``Case``: the request schema forbids unknown keys.

A revision is a local directory identified by ``tree_sha256``, a digest over the sorted (relative path, normalised
git mode, content sha256) of every file, so two runs agree on what they investigated regardless of umask.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

CONTRACT_VERSION = "corsair-lite/1"


def _safe_path(value: str) -> str:
    """A relative path inside the tree: no leading slash, no ``..`` segment, no NUL."""
    if not value or len(value) > 512 or value.startswith("/") or "\0" in value:
        raise ValueError("a relative path of at most 512 characters is required")
    if any(part in ("", "..") for part in value.split("/")):
        raise ValueError("path must not contain empty or '..' segments")
    return value


SafePath = Annotated[str, AfterValidator(_safe_path)]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Finding(Frozen):
    """What a reporter or scanner claims. Untrusted text."""

    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    file_path: SafePath | None = None
    start_line: int | None = Field(default=None, ge=1)
    symbol: str | None = Field(default=None, max_length=256)
    cwe: str | None = Field(default=None, pattern=r"^CWE-\d{1,5}$")


class Revision(Frozen):
    source: str = Field(min_length=1, max_length=1024, description="Host path of the tree")
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Case(Frozen):
    contract: Literal["corsair-lite/1"] = CONTRACT_VERSION
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}$", description="Opaque to agents")
    finding: Finding
    revision: Revision
    fixed_revision: Revision | None = None


def tree_sha256(root: Path) -> str:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"revision source is not a directory: {root}")
    entries: list[tuple[str, str, str]] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        here = Path(directory)
        for name in [d for d in dirnames if (here / d).is_symlink()] + filenames:
            path = here / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                mode, content = "120000", os.readlink(path).encode()
            elif stat.S_ISREG(info.st_mode):
                mode = "100755" if info.st_mode & 0o111 else "100644"
                content = path.read_bytes()
            else:
                continue
            entries.append((path.relative_to(root).as_posix(), mode, hashlib.sha256(content).hexdigest()))
    digest = hashlib.sha256()
    for relative, mode, content in sorted(entries):
        digest.update(f"{relative}\0{mode}\0{content}\n".encode())
    return digest.hexdigest()


def revision(source: Path, commit: str | None = None) -> Revision:
    source = Path(source).resolve()
    return Revision(source=str(source), commit=commit, tree_sha256=tree_sha256(source))


class GitSource(BaseModel):
    """A tree acquired from a git repository at an exact commit, without running the repository's hooks."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(pattern=r"^https://[^\s]+$")
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    subdir: str | None = Field(default=None, description="Investigate only this directory of the checkout")


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    finding: Finding
    source: str | GitSource = Field(description="A directory relative to this file, or a pinned git source")
    commit: str | None = None
    fixed_source: str | GitSource | None = None
    fixed_commit: str | None = None


SOURCES_ENV = "CORSAIR_SOURCES"


def sources_root() -> Path:
    return Path(os.environ.get(SOURCES_ENV) or Path.cwd() / ".runs" / "sources")


def acquire(source: GitSource, root: Path | None = None) -> Path:
    """Clone exactly one commit into a cache keyed by (url, commit), hooks disabled, and return the tree path.

    The cache directory is content-addressed; a complete checkout carries a ``.corsair-complete`` marker, so an
    interrupted clone is redone rather than trusted. ``.git`` stays beside the tree and is excluded from the digest.
    """
    import subprocess

    key = hashlib.sha256(f"{source.url}\n{source.commit}".encode()).hexdigest()[:24]
    target = (root or sources_root()) / key
    marker = target / ".corsair-complete"
    if not marker.is_file():
        if target.exists():
            import shutil
            shutil.rmtree(target)
        target.mkdir(parents=True)
        git = ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "-C", str(target)]
        subprocess.run([*git, "init", "-q"], check=True, stdin=subprocess.DEVNULL)
        subprocess.run([*git, "fetch", "-q", "--depth", "1", source.url, source.commit], check=True,
                       stdin=subprocess.DEVNULL, timeout=900)
        subprocess.run([*git, "-c", "advice.detachedHead=false", "checkout", "-q", source.commit], check=True,
                       stdin=subprocess.DEVNULL)
        marker.write_text(f"{source.url}\n{source.commit}\n")
    tree = target / source.subdir if source.subdir else target
    if not tree.is_dir() or not tree.resolve().is_relative_to(target.resolve()):
        raise ValueError(f"subdir {source.subdir!r} is not a directory inside the checkout")
    return tree


def from_request(path: Path) -> Case:
    """A Case from a request file (``input.json``): ``finding`` and ``source`` are required; ``fixed_source``,
    ``commit``, ``fixed_commit`` and ``case_id`` are optional; any other key (a label, an oracle) is refused.
    A source is a directory relative to the file, or ``{"url": ..., "commit": ..., "subdir": ...}`` acquired by
    ``acquire`` at that exact commit."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    request = _Request.model_validate_json(raw)
    base = path.parent

    def resolve(spec: str | GitSource, commit: str | None) -> Revision:
        if isinstance(spec, GitSource):
            return revision(acquire(spec), spec.commit)
        return revision(base / spec, commit)

    fixed = resolve(request.fixed_source, request.fixed_commit) if request.fixed_source else None
    return Case(case_id=request.case_id or f"issue:{hashlib.sha256(raw).hexdigest()[:16]}", finding=request.finding,
                revision=resolve(request.source, request.commit), fixed_revision=fixed)


def load_case(path: Path) -> Case:
    """``path`` is a request file or a case directory holding ``input.json``."""
    path = Path(path)
    return from_request(path / "input.json" if path.is_dir() else path)


def load_oracle(path: Path) -> dict | None:
    """Evaluator-only truth beside a case directory (``oracle.json``); None when absent. Never passed to agents."""
    path = Path(path)
    oracle = (path if path.is_dir() else path.parent) / "oracle.json"
    return json.loads(oracle.read_text()) if oracle.is_file() else None
