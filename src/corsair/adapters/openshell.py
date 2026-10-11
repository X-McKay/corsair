"""Pinned native lifecycle in an operator-exclusive workspace. No retries.

Delete checks refuse observed replacements; the native name-based API has no
atomic expected-ID delete. Do not use against concurrent external mutation.
The client and fixed native spec are operator-provided; client must use the
qualified TLS configuration. This adapter does not manage transport or agents.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import UUID

import grpc
from google.protobuf.json_format import MessageToJson
from openshell import SandboxClient, DeletionOutcome
from openshell._proto import openshell_pb2

from corsair.ports.sandbox import SandboxHandle, LifecycleReceipt, LifecycleError


class OpenShellLifecycle:
    def __init__(self, client: SandboxClient, *, spec: openshell_pb2.SandboxSpec,
                 workspace: str, owner: UUID, receipts: Path):
        if not workspace or not isinstance(owner, UUID):
            raise ValueError('Explicit workspace and UUID owner required')
        if not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', spec.template.image):
            raise ValueError('Operator workload image must have an immutable digest')
        if not receipts.is_absolute():
            raise ValueError('Host receipt directory must be absolute')
        # Hold the actual protected directory inode, not a mutable pathname.
        fd = os.open(receipts, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(fd)
            raise ValueError('Host receipt directory must be owned by this user with mode0700')
        self._dir = fd
        self._client = client
        self._workspace = workspace
        self._owner = str(owner)
        self._spec = spec.SerializeToString(deterministic=True)
        self._spec_digest = hashlib.sha256(self._spec).hexdigest()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self._dir)

    def _write(self, operation, suffix, value):
        data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        fd = os.open(f'{operation}.{suffix}.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self._dir)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self._dir)

    def _begin(self, operation, action, handle=None):
        if not isinstance(operation, UUID):
            raise ValueError('Operation must be a UUID')
        receipt = LifecycleReceipt(str(operation), action, datetime.now(timezone.utc).isoformat(),
                                   0.0, 'not_dispatched', 'unknown',
                                   'unconfirmed' if action in ('create','delete') else 'not_required', handle)
        try:
            self._write(operation, 'intent', dict(asdict(receipt), workspace=self._workspace,
                        owner=self._owner, spec_sha256=self._spec_digest,
                        requested_name=('cs-' + operation.hex[:16]) if action=='create' else handle.name,
                        pending_delivery='unknown until an authoritative result is observed'))
        except Exception as error:
            raise LifecycleError(replace(receipt, outcome='failed', error_type=type(error).__name__,
                                         error_detail=str(error))) from error
        return receipt, time.monotonic()

    def _finish(self, receipt, started, error=None):
        receipt = replace(receipt, elapsed_seconds=time.monotonic()-started)
        if error is not None:
            code = error.code() if isinstance(error, grpc.RpcError) else None
            native_status = getattr(error, 'raw_status', None)
            receipt = replace(receipt, outcome='unknown' if receipt.delivery=='unknown' and receipt.action in ('create','delete') else 'failed', error_type=type(error).__name__,
                              error_detail=str(error), native_code=code.name if code else None,
                              native_status=MessageToJson(native_status) if native_status is not None else None)
        try:
            self._write(receipt.operation, 'result', asdict(receipt))
        except Exception as storage_error:
            # Known identity and dispatch state are retained even without a file.
            raise LifecycleError(replace(receipt, storage_error=f'{type(storage_error).__name__}: {storage_error}')) from storage_error
        if error is not None:
            raise LifecycleError(receipt) from error
        return receipt

    def _check(self, handle, native):
        if (handle.owner != self._owner or handle.workspace != self._workspace or
            (native.id,native.name,native.workspace) != (handle.id,handle.name,handle.workspace) or
            native.labels.get('corsair.owner') != handle.owner or
            native.labels.get('corsair.operation') != handle.creation_operation):
            raise ValueError('Original sandbox identity or ownership changed; operation refused')

    def create(self, operation: UUID) -> SandboxHandle:
        receipt, started = self._begin(operation, 'create')
        receipt = replace(receipt, delivery='unknown')
        try:
            name = 'cs-' + operation.hex[:16]
            native = self._client.create(workspace=self._workspace, name=name,
                        spec=openshell_pb2.SandboxSpec.FromString(self._spec),
                        labels={'corsair.owner':self._owner,'corsair.operation':str(operation)})
            handle = SandboxHandle(native.id, name, self._workspace, self._owner, str(operation))
            receipt = replace(receipt, handle=handle, delivery='acknowledged')
            if not native.id:
                raise ValueError('Native create returned no immutable ID; reconciliation required')
            self._check(handle, native)
            receipt = replace(receipt, outcome='completed')
        except Exception as error:
            self._finish(receipt, started, error)
        self._finish(receipt, started)
        return handle

    def wait_ready(self, handle: SandboxHandle, operation: UUID) -> None:
        receipt, started = self._begin(operation, 'wait_ready', handle)
        try:
            self._check(handle, self._client.get(handle.name, workspace=handle.workspace))
            receipt = replace(receipt, delivery='unknown')
            native = self._client.wait_ready(handle.name, workspace=handle.workspace)
            receipt = replace(receipt, delivery='acknowledged', phase=openshell_pb2.SandboxPhase.Name(native.phase))
            self._check(handle, native)
            if native.phase != openshell_pb2.SANDBOX_PHASE_READY:
                raise ValueError('Native wait returned a phase other than Ready')
            receipt = replace(receipt, outcome='completed')
        except Exception as error:
            self._finish(receipt, started, error)
        self._finish(receipt, started)

    def delete(self, handle: SandboxHandle, operation: UUID) -> None:
        receipt, started = self._begin(operation, 'delete', handle)
        try:
            self._check(handle, self._client.get(handle.name, workspace=handle.workspace))
            receipt = replace(receipt, delivery='unknown')
            native = self._client.delete(handle.name, workspace=handle.workspace)
            receipt = replace(receipt, delivery='acknowledged', native_delete_outcome=native.outcome.name)
            if native.sandbox_id != handle.id or native.outcome not in (DeletionOutcome.ACCEPTED,DeletionOutcome.COMPLETED):
                raise ValueError('Native deletion did not acknowledge the original ID')
            self._client.wait_deleted(handle.name, workspace=handle.workspace, expected_sandbox_id=handle.id)
            try:
                self._client.get(handle.name, workspace=handle.workspace)
            except grpc.RpcError as error:
                if error.code() != grpc.StatusCode.NOT_FOUND:
                    raise
            else:
                raise ValueError('Sandbox name still exists after deletion; cleanup unconfirmed')
            receipt = replace(receipt, outcome='completed', cleanup='confirmed')
        except Exception as error:
            self._finish(receipt, started, error)
        self._finish(receipt, started)
