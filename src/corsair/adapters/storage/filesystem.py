"""One local immutable store; successful operation manifests are the reconciliation record."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from corsair.contracts import ArtifactRef, digest


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.blobs = self.root / "blobs"
        self.operations = self.root / "operations"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.operations.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _publish(path: Path, content: bytes) -> bool:
        """Atomic create, never replace a committed record, even under concurrent writers."""
        fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
        temporary = Path(name)
        created = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
                created = True
            except FileExistsError:
                if path.read_bytes() != content:
                    raise ValueError("immutable artifact/operation identity conflict") from None
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return created
        finally:
            temporary.unlink(missing_ok=True)

    def put(self, content: bytes, media_type: str = "application/octet-stream") -> ArtifactRef:
        ref = ArtifactRef(sha256=digest(content), size=len(content), media_type=media_type)
        self._publish(self.blobs / ref.sha256, content)
        return ref

    def get(self, ref: ArtifactRef) -> bytes:
        content = (self.blobs / ref.sha256).read_bytes()
        if len(content) != ref.size or digest(content) != ref.sha256:
            raise ValueError("artifact digest/size mismatch")
        return content

    def put_json(self, value: BaseModel | dict | list) -> ArtifactRef:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        return self.put(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
            "application/json",
        )

    def get_json(self, ref: ArtifactRef):
        return json.loads(self.get(ref))

    def commit(self, operation_id: str, ref: ArtifactRef) -> None:
        # Operation names are hashed: callers cannot escape the operations directory.
        self.get(ref)
        self._publish(self.operations / digest(operation_id), ref.model_dump_json().encode())

    def claim(self, operation_id: str, ref: ArtifactRef) -> bool:
        """Create an immutable execution intent; only the first writer may proceed."""
        self.get(ref)
        return self._publish(self.operations / digest(operation_id), ref.model_dump_json().encode())

    def reconcile(self, operation_id: str) -> ArtifactRef | None:
        path = self.operations / digest(operation_id)
        if not path.exists():
            return None
        ref = ArtifactRef.model_validate_json(path.read_bytes())
        self.get(ref)
        return ref
