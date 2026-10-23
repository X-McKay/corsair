"""A tiny content-addressed artifact store: bytes in, ``ArtifactRef`` out.

Logs and probe output are large, so stages pass them by reference. The store is a directory keyed by sha256, so the
same bytes are stored once and a reference can be checked against its content at any time.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ENV_ROOT = "CORSAIR_ARTIFACTS"


class ArtifactRef(BaseModel):
    """Content-addressed bytes in the run's artifact store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    uri: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


def default_root() -> Path:
    return Path(os.environ.get(ENV_ROOT) or Path.cwd() / ".runs" / "artifacts")


class ArtifactStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else default_root()

    def _path(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256

    def put(self, data: bytes) -> ArtifactRef:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside the target and rename, so a reader never sees a partial file under a digest name.
            temporary = path.with_name(f".{digest}.{os.getpid()}.tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return ArtifactRef(uri=path.resolve().as_uri(), sha256=digest, size=len(data))

    def ref(self, sha256: str) -> ArtifactRef | None:
        """The reference for content already stored, or None when the store does not hold it."""
        path = self._path(sha256)
        if not path.is_file():
            return None
        return ArtifactRef(uri=path.resolve().as_uri(), sha256=sha256, size=path.stat().st_size)

    def get(self, ref: ArtifactRef) -> bytes:
        data = self._path(ref.sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError(f"artifact {ref.sha256} does not match its content")
        return data


def put(data: bytes, root: Path | str | None = None) -> ArtifactRef:
    return ArtifactStore(root).put(data)


def write_json(path: Path, value: object) -> None:
    """Publish a complete checkpoint atomically; a reader never observes partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
