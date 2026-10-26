"""Admitted source snapshots, not a generic forge or Git client API."""

from collections.abc import Iterable
from typing import Protocol

from corsair.contracts import ArtifactRef, Case, PreparedCase, RunManifest


class SourceAdmissionError(ValueError):
    """Source cannot be safely admitted or read under the operator policy."""


class SourceReader(Protocol):
    def read_text(self, snapshot: ArtifactRef, path: str, *, max_bytes: int) -> str: ...

    def iter_files(self, snapshot: ArtifactRef) -> Iterable[tuple[str, bytes]]: ...


class SourceSnapshotPort(SourceReader, Protocol):
    def prepare(self, case: Case, manifest: RunManifest) -> PreparedCase:
        """Admit sources and bind the target line; a certainly unbindable Python target
        raises ``policies.target_binding.TargetBindingBlocked`` before any model call."""
        ...
