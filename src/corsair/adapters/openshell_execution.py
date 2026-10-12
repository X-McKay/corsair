"""Supported native SDK execution in a bounded Linux host worker. No retries."""
import base64
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import multiprocessing
import os
from pathlib import Path
import resource
import time
from uuid import UUID

import grpc
from google.protobuf.json_format import MessageToJson
from openshell import SandboxClient, TlsConfig, ExecChunk, ExecResult
from openshell._proto import openshell_pb2

from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.execution import ExecutionLimits, ExecutionReceipt, ExecutionError
from corsair.ports.sandbox import SandboxHandle


@dataclass(frozen=True)
class OpenShellConnection:
    endpoint: str
    ca: Path
    cert: Path
    key: Path

    def __post_init__(self):
        if not self.endpoint or not all(p.is_absolute() and p.is_file() for p in (self.ca,self.cert,self.key)):
            raise ValueError('Explicit endpoint and complete host TLS files required')


def host_profile(memory_bytes):
    # GNU glibc 2.39 malloc.h: M_ARENA_MAX=-8. Call only before threads.
    # Bound per-core arena reservation without relaxing RLIMIT_AS.
    import ctypes
    if len(os.listdir('/proc/self/task')) != 1:
        raise RuntimeError('Host allocator admission requires a single-threaded worker')
    libc = ctypes.CDLL(None)
    libc.gnu_get_libc_version.restype = ctypes.c_char_p
    version = libc.gnu_get_libc_version().decode()
    if version != '2.39':
        raise RuntimeError('Unqualified host glibc version: ' + version)
    libc.mallopt.argtypes = [ctypes.c_int, ctypes.c_int]
    libc.mallopt.restype = ctypes.c_int
    if libc.mallopt(-8, 2) != 1:
        raise RuntimeError('Native host allocator refused the two-arena profile')
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    return {'memory_limit':resource.getrlimit(resource.RLIMIT_AS),
            'cpu_affinity':sorted(os.sched_getaffinity(0)), 'glibc':version, 'allocator_arenas':2}


def native_worker(pipe, connection, handle, command, workdir, limits):
    dispatched = False
    layer = 'host_admission'
    try:
        profile = host_profile(limits.worker_memory_bytes)
        with SandboxClient(connection.endpoint, tls=TlsConfig(ca_path=connection.ca, cert_path=connection.cert,
                          key_path=connection.key), timeout=limits.execution_seconds+10) as client:
            layer = 'native_identity'
            pipe.send(('native_call', 'get'))
            native = client.get(handle.name, workspace=handle.workspace)
            if ((native.id,native.name,native.workspace) != (handle.id,handle.name,handle.workspace)
                    or native.labels.get('corsair.owner') != handle.owner
                    or native.labels.get('corsair.operation') != handle.creation_operation
                    or native.phase != openshell_pb2.SANDBOX_PHASE_READY):
                raise ValueError('Original sandbox ownership/identity or Ready changed; execution refused')
            pipe.send(('dispatch', profile))
            dispatched = True
            layer = 'native_execution'
            pipe.send(('native_call', 'exec_stream'))
            remaining = limits.output_bytes
            for item in client.exec_stream(handle.name, command, workspace=handle.workspace,
                        workdir=workdir, no_login_shell=True, timeout_seconds=limits.execution_seconds):
                if isinstance(item, ExecChunk):
                    kept = item.data[:remaining]
                    pipe.send((item.stream, kept))
                    remaining -= len(kept)
                    if len(item.data) > len(kept):
                        pipe.send(('output_limit', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
                        # Closing the supported native client stops consumption;
                        # it does not establish remote process cancellation.
                        return
                elif isinstance(item, ExecResult):
                    pipe.send(('terminal', {'exit':item.exit_code, 'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
                    return
                else:
                    raise TypeError('Unsupported native execution event')
            raise RuntimeError('Native stream returned no terminal result')
    except Exception as error:
        code = error.code() if isinstance(error, grpc.RpcError) else None
        status = getattr(error, 'raw_status', None)
        pipe.send(('error', {'delivery': 'unknown' if dispatched else 'not_dispatched',
                   'error_type':type(error).__name__, 'error_detail':str(error),
                   'native_code':code.name if code else None,
                   'native_status':MessageToJson(status) if status is not None else None, 'failure_layer':layer}))
    finally:
        pipe.close()


def serialized(receipt):
    value = asdict(receipt)
    for key in ('stdout','stderr'):
        data = value.pop(key)
        value[key+'_base64'] = base64.b64encode(data).decode()
        value[key+'_bytes'] = len(data)
        value[key+'_sha256'] = hashlib.sha256(data).hexdigest()
    return value


class OpenShellExecution:
    def __init__(self, connection: OpenShellConnection, *, workspace: str, owner: UUID,
                 workdir: str, limits: ExecutionLimits, receipts: Path):
        if not workspace or not isinstance(owner,UUID) or not workdir.startswith('/') or '\x00' in workdir:
            raise ValueError('Explicit operator workspace/owner and absolute workdir required')
        self._connection = connection
        self._workspace, self._owner, self._workdir = workspace, str(owner), workdir
        self._limits = limits
        self._journal = ReceiptDirectory(receipts)

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def execute(self, handle: SandboxHandle, command: tuple[str, ...], operation: UUID) -> ExecutionReceipt:
        if (not isinstance(operation,UUID) or type(command) is not tuple or not command
                or any(type(arg) is not str or '\x00' in arg for arg in command)
                or not command[0] or sum(len(arg.encode())+1 for arg in command)>16384):
            raise ValueError('UUID operation and bounded argv tuple required')
        receipt = ExecutionReceipt(str(operation), handle, datetime.now(timezone.utc).isoformat(),
                                   0.0, 'not_dispatched', 'unknown', 'pending')
        started = time.monotonic()
        process, parent, child = None, None, None
        stdout, stderr = bytearray(), bytearray()
        cause = None
        try:
            self._journal.write(operation, 'intent', dict(serialized(receipt),
                limits=asdict(self._limits), workdir=self._workdir,
                command_sha256=hashlib.sha256(b'\x00'.join(a.encode() for a in command)).hexdigest(),
                pending_delivery='unknown until an authoritative result is observed'))
        except Exception as error:
            raise ExecutionError(replace(receipt, reason='intent_storage', failure_layer='receipt_storage', storage_error=str(error))) from error
        try:
            if handle.owner != self._owner or handle.workspace != self._workspace:
                raise ValueError('Handle does not belong to operator workspace/owner')
            context = multiprocessing.get_context('spawn')
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=native_worker,
                args=(child,self._connection,handle,command,self._workdir,self._limits))
            # A failing start can have created a child: do not claim non-delivery.
            receipt = replace(receipt, delivery='unknown', worker_cleanup='unconfirmed')
            process.start()
            child.close()
            receipt = replace(receipt, worker_pid=process.pid, worker_cleanup='unconfirmed', delivery='unknown')
            deadline = started + self._limits.host_seconds
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0 or not parent.poll(remaining):
                    receipt = replace(receipt, reason='host_timeout', failure_layer='host_supervision')
                    break
                kind, value = parent.recv()
                if kind in ('stdout','stderr'):
                    if len(stdout)+len(stderr)+len(value)>self._limits.output_bytes:
                        raise ValueError('Worker violated output contract')
                    (stdout if kind=='stdout' else stderr).extend(value)
                elif kind=='native_call':
                    if value not in ('get','exec_stream') or len(receipt.native_calls)>=2:
                        raise ValueError('Worker native-call contract violated')
                    receipt = replace(receipt, native_calls=receipt.native_calls+(value,))
                elif kind=='dispatch':
                    if tuple(value['memory_limit']) != (self._limits.worker_memory_bytes,)*2:
                        raise ValueError('Worker memory limit was not applied')
                    if len(value['cpu_affinity']) != 1:
                        raise ValueError('Worker single-CPU affinity was not applied')
                    if (value['glibc'],value['allocator_arenas']) != ('2.39',2):
                        raise ValueError('Worker native allocator profile was not applied')
                    receipt = replace(receipt, worker_limit_applied=True, worker_cpu_affinity=tuple(value['cpu_affinity']),
                                      worker_glibc=value['glibc'], worker_allocator_arenas=value['allocator_arenas'])
                elif kind=='terminal':
                    value, rss = value['exit'], value['maxrss_kib']
                    receipt = replace(receipt, delivery='acknowledged', native_exit=value, worker_maxrss_kib=rss,
                        completion='unknown' if value in (74,124) else 'terminal_observed',
                        reason='native_special_status' if value in (74,124) else 'terminal',
                        failure_layer='native_execution' if value in (74,124) else None)
                    break
                elif kind=='error':
                    receipt = replace(receipt, reason='native_error', **value)
                    break
                elif kind=='output_limit':
                    receipt = replace(receipt, reason='output_limit', failure_layer='output_budget', worker_maxrss_kib=value)
                    break
                else:
                    raise ValueError('Worker returned an unsupported event')
        except Exception as error:
            cause = error
            receipt = replace(receipt, reason='worker_loss' if isinstance(error,EOFError) else 'host_error',
                              error_type=type(error).__name__, error_detail=str(error), failure_layer='host_supervision')
        finally:
            if process is not None and process.pid is not None:
                try:
                    process.join(timeout=1)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=1)
                    receipt = replace(receipt, worker_exit=process.exitcode,
                        worker_cleanup='confirmed' if not process.is_alive() else 'unconfirmed')
                finally:
                    if not process.is_alive(): process.close()
            if parent is not None: parent.close()
            if child is not None: child.close()
        receipt = replace(receipt, stdout=bytes(stdout), stderr=bytes(stderr), elapsed_seconds=time.monotonic()-started)
        try:
            self._journal.write(operation, 'result', serialized(receipt))
        except Exception as error:
            raise ExecutionError(replace(receipt, storage_error=f'{type(error).__name__}: {error}')) from error
        if receipt.reason != 'terminal' or receipt.worker_cleanup != 'confirmed':
            raise ExecutionError(receipt) from cause
        return receipt
