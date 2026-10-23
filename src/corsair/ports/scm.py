"""Source-control acquisition boundary for case loading."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from corsair.domain.case import GitSource


class SourceControl(Protocol):
    """Acquire an immutable Git source into a local tree."""

    def acquire(self, source: GitSource, root: Path | None = None) -> Path: ...
