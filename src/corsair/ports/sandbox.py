"""Vendor-free lifecycle boundary; operator code holds this port."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class SandboxHandle:
    id: str
    name: str
    workspace: str
    owner: str
    creation_operation: str


@dataclass(frozen=True)
class LifecycleReceipt:
    operation: str
    action: Literal['create', 'wait_ready', 'delete']
    started_at: str
    elapsed_seconds: float
    delivery: Literal['not_dispatched', 'unknown', 'acknowledged']
    outcome: Literal['unknown', 'failed', 'completed']
    cleanup: Literal['not_required', 'unconfirmed', 'confirmed']
    handle: SandboxHandle | None = None
    phase: str | None = None
    native_delete_outcome: str | None = None
    error_type: str | None = None
    error_detail: str | None = None
    native_code: str | None = None
    native_status: str | None = None
    storage_error: str | None = None


class LifecycleError(RuntimeError):
    """Receipt and chained native cause survive failure, including journal loss."""
    def __init__(self, receipt: LifecycleReceipt):
        self.receipt = receipt
        super().__init__(f'{receipt.action} {receipt.operation}: {receipt.storage_error or receipt.error_detail or receipt.outcome}')


class SandboxLifecycle(Protocol):
    def create(self, operation: UUID) -> SandboxHandle: ...
    def wait_ready(self, handle: SandboxHandle, operation: UUID) -> None: ...
    def delete(self, handle: SandboxHandle, operation: UUID) -> None: ...
