"""Operator-owned sandbox preparation for the chain's environment stage (SPEC-0070): the port adapters implement and
the composition consumes, so an adapter never imports the composition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Protocol
from uuid import UUID

from corsair.ports.execution import SandboxExecution
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import PatchFile

if TYPE_CHECKING:
    from corsair.agents.environment.contracts import Toolchain


@dataclass(frozen=True)
class PreparedSandbox:
    """A sandbox of one prepared toolchain image, live until the preparation port releases it.

    ``read_source`` returns a file's bytes from the operator's capture of the revision placed in the sandbox
    (never from the sandbox), or None when the capture has no such file; ``source_paths`` lists every file of that
    capture (SPEC-0071: without it a smoke baseline is refused)."""
    execution: SandboxExecution
    handle: SandboxHandle
    scratch_location: str
    read_source: Callable[[str], bytes | None]
    source_paths: Callable[[], tuple[str, ...]] | None = None


class PreparationRefused(RuntimeError):
    """A preparation that ended before handing back a sandbox, with its failure layer and what it left behind:
    ``not_required`` when it refused before any sandbox existed (SPEC-0070)."""
    def __init__(self, layer: str, reason: str, cleanup: Literal["not_required", "confirmed", "unconfirmed"]):
        self.layer, self.reason, self.cleanup = layer, reason, cleanup
        super().__init__(f"{layer}: {reason}")


class Preparation(Protocol):
    """Operator-owned sandbox lifecycle for the environment stage; adapters are chosen outside the chain."""
    def prepare(self, toolchain: Toolchain, operation: UUID, *, overlay: tuple[PatchFile, ...] = ()) -> PreparedSandbox:
        """`overlay`: operator files (SPEC-0071 smoke tests) written beside the captured commit; an overlay path the
        capture already has is refused before any sandbox is created."""
        ...
    def release(self, sandbox: PreparedSandbox, operation: UUID) -> Literal["confirmed", "unconfirmed"]: ...
