"""Vendor-free bounded execution boundary; limits are operator-owned."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from corsair.ports.sandbox import SandboxHandle


@dataclass(frozen=True)
class ExecutionLimits:
    output_bytes: int
    execution_seconds: int
    host_seconds: int
    worker_memory_bytes: int

    def __post_init__(self):
        values = (self.output_bytes, self.execution_seconds, self.host_seconds, self.worker_memory_bytes)
        if any(type(v) is not int for v in values):
            raise ValueError('Execution limits must be integer operator budgets')
        if not (1 <= self.output_bytes <= 1024*1024 and 1 <= self.execution_seconds <= 300
                and self.execution_seconds < self.host_seconds <= 360
                and 256*1024*1024 <= self.worker_memory_bytes <= 1024*1024*1024):
            raise ValueError('Execution limits outside the admitted local range')


@dataclass(frozen=True)
class ExecutionReceipt:
    operation: str
    handle: SandboxHandle
    started_at: str
    elapsed_seconds: float
    delivery: Literal['not_dispatched', 'unknown', 'acknowledged']
    completion: Literal['unknown', 'terminal_observed']
    reason: str
    failure_layer: str | None = None
    stdout: bytes = b''
    stderr: bytes = b''
    native_exit: int | None = None
    worker_pid: int | None = None
    worker_exit: int | None = None
    worker_limit_applied: bool | None = None
    worker_cpu_affinity: tuple[int, ...] | None = None
    worker_glibc: str | None = None
    worker_allocator_arenas: int | None = None
    worker_maxrss_kib: int | None = None
    native_calls: tuple[str, ...] = ()
    worker_cleanup: Literal['not_required', 'unconfirmed', 'confirmed'] = 'not_required'
    error_type: str | None = None
    error_detail: str | None = None
    native_code: str | None = None
    native_status: str | None = None
    storage_error: str | None = None


class ExecutionError(RuntimeError):
    def __init__(self, receipt: ExecutionReceipt):
        self.receipt = receipt
        super().__init__(f'exec {receipt.operation}: {receipt.storage_error or receipt.error_detail or receipt.reason}')


class SandboxExecution(Protocol):
    def execute(self, handle: SandboxHandle, command: tuple[str, ...], operation: UUID) -> ExecutionReceipt: ...
