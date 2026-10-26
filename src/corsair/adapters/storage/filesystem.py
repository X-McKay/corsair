"""One local immutable store; successful operation manifests are the reconciliation record."""

import json
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel

from corsair.contracts import ArtifactRef, digest

_OPERATION_KEY = re.compile(r"[0-9a-f]{64}")


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

    @staticmethod
    def operation_key(operation_id: str) -> str:
        """Operation names are hashed: callers cannot escape the operations directory."""
        return digest(operation_id)

    def commit(self, operation_id: str, ref: ArtifactRef) -> None:
        self.get(ref)
        self._publish(
            self.operations / self.operation_key(operation_id), ref.model_dump_json().encode()
        )

    def claim(self, operation_id: str, ref: ArtifactRef) -> bool:
        """Create an immutable execution intent; only the first writer may proceed."""
        self.get(ref)
        return self._publish(
            self.operations / self.operation_key(operation_id), ref.model_dump_json().encode()
        )

    def operation_records(self) -> Iterator[tuple[str, float, ArtifactRef | None]]:
        """Read-only enumeration of committed records as (key, recorded time, reference).

        Names are stored hashed, so a record yields its key rather than its name; callers
        bind a referenced document to a name with :meth:`operation_key`. Records are
        newest first by filesystem time, which is operational metadata, never evidence.
        An unparseable record yields ``None`` rather than ending the enumeration.
        """
        records: list[tuple[float, str, Path]] = []
        for path in self.operations.iterdir():
            if _OPERATION_KEY.fullmatch(path.name) and path.is_file():
                records.append((path.stat().st_mtime, path.name, path))
        records.sort(key=lambda record: (-record[0], record[1]))
        for recorded, key, path in records:
            try:
                ref: ArtifactRef | None = ArtifactRef.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                ref = None
            yield key, recorded, ref

    def reconcile(self, operation_id: str) -> ArtifactRef | None:
        path = self.operations / self.operation_key(operation_id)
        if not path.exists():
            return None
        ref = ArtifactRef.model_validate_json(path.read_bytes())
        self.get(ref)
        return ref
