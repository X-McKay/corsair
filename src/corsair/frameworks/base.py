"""The adapter contract. Adapters import the kernel's types; the kernel imports adapters lazily by name."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..kernel import GateVerdict, Hypothesis, Outcome

PROBE_DIR = "/work/.corsair"
RESULT_DIR = "/tmp/corsair"
WORKDIR = "/work"


@dataclass(frozen=True)
class ProbeResult:
    """What one payload's run showed, read from the collected result files only."""

    outcome: "Outcome"
    exception_type: str | None
    message: str | None
    junit_tests: int
    covered_target: bool | None
    covered_lines: tuple[int, ...]


class Framework(Protocol):
    name: str
    language: str
    probe_file: str
    """The file name, inside ``PROBE_DIR``, the submitted probe source is written to."""

    def guard(self, probe: str) -> "GateVerdict":
        """Structural check of the probe source: the required symbols, one payload parameter, no mocking imports.
        Returns a passed or failed ``ast_guard`` verdict; never runs the code."""
        ...

    def driver_files(self) -> dict[str, bytes]:
        """Kernel-owned files written beside the probe (relative to ``PROBE_DIR``): the driver that runs
        ``run_target`` for one payload as one native test id and records the classification."""
        ...

    def command(self, role: str, target_file: str) -> list[str]:
        """The argv that runs exactly one payload under coverage, from ``WORKDIR``, writing the native report, the
        coverage report and the driver record under ``RESULT_DIR``."""
        ...

    def environment(self, role: str) -> Mapping[str, str]:
        ...

    def result_paths(self) -> list[str]:
        """Files to copy out after the run, under ``RESULT_DIR``."""
        ...

    def read(self, files: Mapping[str, bytes | None], hypothesis: "Hypothesis") -> ProbeResult:
        """Classify the run from the collected files. A missing driver record or an empty native report is
        ``not_run``; a driver record that disagrees with the native report is ``errored``."""
        ...
