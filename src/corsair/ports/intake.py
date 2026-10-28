"""Narrow inspection reader; no SDK, shell or source-admission capability."""

from typing import Protocol


class InspectionReader(Protocol):
    def read(self, operation: str, relative: str = "") -> dict: ...
