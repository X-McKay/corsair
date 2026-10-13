"""Immutable byte identities and committed source; no vendor objects."""
from dataclasses import dataclass
import re
from typing import Protocol


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    size: int

    def __post_init__(self):
        if not isinstance(self.sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.sha256):
            raise ValueError('Full lowercase SHA256 required')
        if type(self.size) is not int or self.size < 0:
            raise ValueError('Nonnegative exact byte count required')


@dataclass(frozen=True)
class SourceFile:
    path: str
    mode: str
    git_blob: str
    artifact: ArtifactRef


@dataclass(frozen=True)
class SkippedEntry:
    """A symlink or submodule link the operator chose to leave out of a snapshot (SPEC-0037)."""
    path: str
    mode: str
    kind: str
    object: str


@dataclass(frozen=True)
class SourceSnapshot:
    commit: str
    tree: str
    files: tuple[SourceFile, ...]
    manifest: ArtifactRef
    skipped: tuple[SkippedEntry, ...] = ()


class ArtifactStore(Protocol):
    def put(self, data: bytes, *, expected_sha256: str | None = None) -> ArtifactRef: ...
    def get(self, reference: ArtifactRef) -> bytes: ...
