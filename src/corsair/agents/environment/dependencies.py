"""Injected ports, operator-owned budget and the trusted per-run ledger for the environment agent.

Commands run only through the vendor-free execution port under the operator's
sandbox policy and limits; concrete adapters are chosen outside this package.
"""

from dataclasses import dataclass, field
from typing import Callable
from uuid import UUID, uuid4

from corsair.agents.issue_analysis.contracts import SourceExcerpt, confined_path
from corsair.ports.execution import SandboxExecution
from corsair.ports.sandbox import SandboxHandle

from .contracts import CommandRecord, EnvironmentInput


@dataclass(frozen=True)
class SetupBudget:
    """Operator-owned; nothing the model or repository says can change it."""
    max_commands: int = 12

    def __post_init__(self):
        if type(self.max_commands) is not int or not 1 <= self.max_commands <= 64:
            raise ValueError("setup command budget outside the admitted range")


@dataclass
class SetupLedger:
    """Trusted per-run record of every dispatched command and its retained output."""
    records: list[CommandRecord] = field(default_factory=list)
    outputs: dict[int, tuple[bytes, bytes]] = field(default_factory=dict)
    halted: str | None = None


@dataclass(frozen=True)
class EnvironmentDependencies:
    inputs: EnvironmentInput
    execution: SandboxExecution
    handle: SandboxHandle
    toolchain_id: str
    scratch_location: str
    budget: SetupBudget = SetupBudget()
    ledger: SetupLedger = field(default_factory=SetupLedger)
    new_operation: Callable[[], UUID] = uuid4

    def __post_init__(self):
        if self.toolchain_id not in {t.toolchain_id for t in self.inputs.toolchains}:
            raise ValueError("preparation sandbox toolchain is absent from the catalog")
        if not self.scratch_location.startswith("/"):
            raise ValueError("absolute operator scratch location required")

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        confined_path(path)
        source = next((s for s in self.inputs.source_files if s.path == path), None)
        if source is None:
            raise ValueError("source path is absent from the supplied inventory")
        lines = source.content.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines) or end_line - start_line + 1 > 80:
            raise ValueError("source line range is absent from the supplied inventory")
        return SourceExcerpt(path=path, start_line=start_line, end_line=end_line,
                             quote="\n".join(lines[start_line - 1:end_line]))
