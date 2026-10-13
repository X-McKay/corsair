"""Shared native test runner orchestration: one fresh workspace, framework stages, release always runs.

Framework adapters (pytest, Maven Surefire) supply id validation and the discovery/execution stages;
this base owns workspace lifecycle, receipt completeness and never retries a command.
"""
from typing import Literal
from uuid import UUID

from corsair.ports.artifacts import ArtifactStore
from corsair.ports.execution import ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun, TestWorkspace, WitnessRequest


def error_text(error: BaseException) -> str:
    return f'{type(error).__name__}: {error}'[:2048]


def incomplete(receipt: ExecutionReceipt, operation: UUID, handle: SandboxHandle) -> str | None:
    if receipt.operation != str(operation) or receipt.handle != handle:
        return 'receipt identity does not match the requested execution'
    if (receipt.delivery != 'acknowledged' or receipt.completion != 'terminal_observed' or receipt.reason != 'terminal'
            or receipt.failure_layer is not None or receipt.storage_error is not None
            or receipt.worker_cleanup != 'confirmed' or type(receipt.native_exit) is not int):
        return (f'incomplete execution: delivery={receipt.delivery} completion={receipt.completion} '
                f'reason={receipt.reason} layer={receipt.failure_layer} cleanup={receipt.worker_cleanup}')
    return None


class NativeRunner:
    """Subclasses implement `_validate` (refuse before any workspace exists) and `_stages`."""

    def __init__(self, workspace: TestWorkspace, execution: SandboxExecution, store: ArtifactStore, config):
        self._workspace, self._execution, self._store, self._config = workspace, execution, store, config

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        raise NotImplementedError

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        raise NotImplementedError

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID,
            witness: WitnessRequest | None = None) -> NativeTestRun:
        if not isinstance(operation, UUID) or not isinstance(patch, ApprovedPatch):
            raise ValueError('Operator operation and approved patch required')
        ids = (control_test_id, security_test_id)
        self._validate(patch, ids, witness)
        if type(discovery_command) is not tuple or not discovery_command or any(type(t) is not str for t in discovery_command):
            raise ValueError('Discovery command must be string tokens')
        paths = {item.path for item in patch.files}
        base = dict(operation=str(operation), patch_sha256=patch.sha256)
        try:
            prepared = self._workspace.prepare(patch, operation)
        except Exception as error:
            # Preparation may have created a sandbox before failing: never infer absence.
            return NativeTestRun(**base, workspace=None, discovery=None, execution=None, cleanup='unconfirmed',
                                 failure_layer='workspace', detail=f'prepare: {error_text(error)}')
        cleanup: Literal['confirmed', 'unconfirmed'] = 'unconfirmed'
        released, captured = '', None
        try:
            if prepared.patch_sha256 != patch.sha256:
                discovery = execution = None
                layer, detail = 'workspace', 'prepared workspace does not hold this patch'
            else:
                discovery, execution, layer, detail, captured = self._stages(
                    prepared, ids, discovery_command, sorted(paths), operation, witness)
        finally:
            try:
                cleanup = 'confirmed' if self._workspace.release(prepared, operation) == 'confirmed' else 'unconfirmed'
            except Exception as error:
                released = f'; release: {error_text(error)}'
        return NativeTestRun(**base, workspace=prepared, discovery=discovery, execution=execution, cleanup=cleanup,
                             failure_layer=layer, detail=detail+released, witness=captured)

    def _execute(self, handle: SandboxHandle, argv: tuple[str, ...], operation: UUID) -> tuple[ExecutionReceipt | None, str | None]:
        try:
            receipt = self._execution.execute(handle, argv, operation)
        except Exception as error:
            # Never retried: delivery of the failed command may be unknown.
            return getattr(error, 'receipt', None), error_text(error)
        return receipt, incomplete(receipt, operation, handle)

    def _excerpt(self, receipt: ExecutionReceipt | None) -> str:
        if receipt is None:
            return ''
        limit = self._config.max_excerpt_chars
        return (f'exit={receipt.native_exit}\nstdout:\n{receipt.stdout[:limit*4].decode("utf-8", "replace")[:limit]}'
                f'\nstderr:\n{receipt.stderr[:limit*4].decode("utf-8", "replace")[:limit]}')
