"""Content-addressed evidence storage consumed by trusted application code."""

from typing import Protocol, runtime_checkable

from corsair.domain.artifacts import ArtifactRef


@runtime_checkable
class Artifacts(Protocol):
    def put(self, data: bytes) -> ArtifactRef: ...
    def ref(self, sha256: str) -> ArtifactRef | None: ...
    def get(self, ref: ArtifactRef) -> bytes: ...
