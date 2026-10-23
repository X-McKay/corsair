"""Pure case types and deterministic local-tree identity."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

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


class GitSource(BaseModel):
    """An exact Git commit, acquired only through the source-control port."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["git", "github", "azure_devops"] = "git"
    url: str = Field(min_length=1, max_length=2048)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    subdir: str | None = Field(default=None, description="Investigate only this directory of the checkout")

    @field_validator("url")
    @classmethod
    def https_repository_url(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("repository URL must not contain whitespace")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ValueError("repository URL has an invalid port") from error
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise ValueError("repository URL must be HTTPS without credentials, query, or fragment")
        return value


def tree_manifest(root: Path, *, directories: bool = False) -> list[tuple[str, str, str]]:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"revision source is not a directory: {root}")
    entries: list[tuple[str, str, str]] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        here = Path(directory)
        for name in [d for d in dirnames if directories or (here / d).is_symlink()] + filenames:
            path = here / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                mode, content = "120000", os.readlink(path).encode()
            elif stat.S_ISREG(info.st_mode):
                mode = "100755" if info.st_mode & 0o111 else "100644"
                content = path.read_bytes()
            elif directories and stat.S_ISDIR(info.st_mode):
                mode, content = "040000", b""
            else:
                continue
            entries.append((path.relative_to(root).as_posix(), mode, hashlib.sha256(content).hexdigest()))
    return sorted(entries)


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, mode, content in tree_manifest(root):
        digest.update(f"{relative}\0{mode}\0{content}\n".encode())
    return digest.hexdigest()


def revision(source: Path, commit: str | None = None) -> Revision:
    source = Path(source).resolve()
    return Revision(source=str(source), commit=commit, tree_sha256=tree_sha256(source))
