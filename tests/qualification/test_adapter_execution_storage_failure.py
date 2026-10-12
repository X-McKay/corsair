"""Actual SDK-worker loss and actual host result-storage refusal.

No workload replay, production hooks, cancellation API or reconciliation runner.
One exclusive parent observes its actual original multiprocessing Process object.
This is not atomic expected-start signalling or a general concurrency guarantee.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import multiprocessing
import stat
import threading
import time
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleLimits
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution, serialized
from corsair.ports.execution import ExecutionError, ExecutionLimits
from tests.qualification.test_adapter_lifecycle import AdapterHarness, ObservedClient, adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import PYTHON, owned, recovery_spec
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.gateway import gateway
from tests.qualification.receipt_observation import file_identity, reader_command


def process_identity(pid):
    """Read physical process identity; absence or replacement is never a signal target."""
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': fields[19], 'state': fields[0]}


def owned_worker(controller, before, memory_bytes):
    assert process_identity(controller['pid'])['start_ticks'] == controller['start_ticks']
    candidates = []
    for process in multiprocessing.active_children():
        if process in before:
            continue
        assert process.is_alive(), 'Original Process ended before deliberate worker loss'
        pid = process.pid
        identity = process_identity(pid)
        if identity['ppid'] != controller['pid'] or Path(f'/proc/{pid}').stat().st_uid != os.geteuid():
            continue
        limits = Path(f'/proc/{pid}/limits').read_text().splitlines()
        address_space = next(line.split() for line in limits if line.startswith('Max address space'))
        if address_space[3:5] != [str(memory_bytes), str(memory_bytes)]:
            continue
        affinity = sorted(os.sched_getaffinity(pid))
        if len(affinity) != 1:
            continue
        candidates.append((process, dict(identity, uid=os.geteuid(), address_space_bytes=memory_bytes,
                                        cpu_affinity=affinity, ownership='original multiprocessing Process object')))
    assert len(candidates) == 1, 'Actual newly spawned bounded SDK Process ownership is not unique'
    return candidates[0]


def directory_identity(fd):
    info = os.fstat(fd)
    assert stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
    return {'dev': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}


def check_directory(path, fd, identity):
    assert directory_identity(fd) == identity
    info = path.lstat()
    assert stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino, info.st_uid) == (
        identity['dev'], identity['inode'], identity['uid'])


def fixed_command(operation, mode):
    # Exclusive marker is observable only after complete write + fsync + rename.
    # It is evidence of actual command start, not acknowledgement of completion.
    token = operation.hex
    duration = '90' if mode == 'worker-loss' else '1.5'
    return (PYTHON, '-c', f'''import json,os,time
from pathlib import Path
token={token!r}
base=Path('/tmp')/('exec-fault-'+token)
temporary=Path(str(base)+'.pending')
marker=Path(str(base)+'.json')
assert not marker.exists()
fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
value={{'operation':token,'pid':os.getpid(),'start_ticks':fields[19]}}
with temporary.open('x') as f:
 f.write(json.dumps(value));f.flush();os.fsync(f.fileno())
os.rename(temporary,marker)
print(json.dumps(value),flush=True)
time.sleep({duration})
with Path(str(base)+'.finished').open('x') as f:f.write('finished\\n')
''')


def start_observation(sdk, handle, operation):
    token = operation.hex
    code = f'''import json
from pathlib import Path
token={token!r}
p=Path('/tmp')/('exec-fault-'+token+'.json')
if not p.exists():
 print(json.dumps({{'started':False}}))
else:
 r=json.loads(p.read_text());assert r['operation']==token
 fields=Path('/proc/'+str(r['pid'])+'/stat').read_text().rsplit(')',1)[1].split()
 assert fields[19]==r['start_ticks']
 r.update(started=True,state=fields[0],finished=Path(str(p)[:-5]+'.finished').exists())
 print(json.dumps(r))
'''
    result = sdk.call('exec', handle.name, [PYTHON, '-c', code], workspace=handle.workspace,
                      workdir='/tmp', no_login_shell=True, timeout_seconds=2)
    assert result.exit_code == 0 and result.stderr == ''
    return json.loads(result.stdout)


def observe_then_fault(sdk, handle, operation, mode, controller, before, limits,
                       receipts, directory_fd, identity, record, done):
    try:
        deadline = time.monotonic() + 5
        while not done.is_set():
            observation = start_observation(sdk, handle, operation)
            record.setdefault('start_observations', []).append(observation)
            if observation['started']:
                assert not observation['finished'] and observation['state'] == 'S'
                record['remote_start'] = observation
                break
            assert time.monotonic() < deadline, 'Actual remote start proof unavailable; do not replay'
            done.wait(.05)
        else:
            raise AssertionError('Execution ended before actual remote start proof; no fault delivered')
        assert not done.is_set(), 'Execution already ended; no deliberate fault delivered'
        if mode == 'worker-loss':
            process, worker = owned_worker(controller, before, limits.worker_memory_bytes)
            record['original_worker'] = worker
            current = process_identity(process.pid)
            assert (current['ppid'], current['start_ticks']) == (controller['pid'], worker['start_ticks'])
            assert process.is_alive() and not done.is_set()
            # Native Process.kill, also used by production supervision. No raw PID signal.
            process.kill()
            record['fault_delivered'] = 'original-owned-Process.kill'
            record['signal_attempts'] = 1
        else:
            check_directory(receipts, directory_fd, identity)
            assert stat.S_IMODE(os.fstat(directory_fd).st_mode) == 0o700
            os.fchmod(directory_fd, 0o500)
            record['fault_delivered'] = 'original-receipt-directory-mode0500'
    except BaseException as error:
        record['fault_error'] = f'{type(error).__name__}: {error}'


@pytest.mark.execution_receipts
def test_actual_worker_loss_storage_refusal_and_original_cleanup(kube, adapter_gateway):
    native = adapter_gateway
    sources = ['src/corsair/ports/sandbox.py', 'src/corsair/ports/execution.py',
               'src/corsair/adapters/openshell.py', 'src/corsair/adapters/openshell_execution.py',
               'src/corsair/adapters/receipts.py', 'tests/qualification/test_adapter_lifecycle.py',
               'tests/qualification/test_recovery.py', 'tests/qualification/gateway.py',
               'tests/qualification/test_lifecycle.py', 'tests/qualification/test_policy.py',
               'tests/qualification/support.py', 'deploy/runtime-lock.yaml',
               'policies/openshell/identity.yaml', 'pyproject.toml', 'uv.lock',
               'tests/qualification/receipt_observation.py']
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    hashes[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (kube.evidence / 'execution-fault-source-hashes.json').write_text(json.dumps(hashes, indent=2))
    summary = {'outcome': 'failed', 'sandboxes': [], 'native_internal_rpc_polls_retries': 'unknown',
               'application_execution_attempts': 0, 'application_retries': 0,
               'scope': 'operator-exclusive Linux/glibc profile; original native sandbox teardown'}
    owner = uuid4()
    limits = ExecutionLimits(4096, 2, 20, 512 * 1024 * 1024)
    summary['limits'] = asdict(limits)
    tls = TlsConfig(ca_path=native['mtls'] / 'ca.crt', cert_path=native['mtls'] / 'tls.crt',
                    key_path=native['mtls'] / 'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls'] / 'ca.crt',
                                     native['mtls'] / 'tls.crt', native['mtls'] / 'tls.key')
    lifecycle_receipts = kube.evidence / 'lifecycle-receipts'
    lifecycle_receipts.mkdir(mode=0o700)
    try:
        assert os.geteuid() != 0, 'Actual directory permission refusal requires an unprivileged fixture owner'
        with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client:
            observed = ObservedClient(SdkReceipts(client, kube.evidence))
            with OpenShellLifecycle(observed, spec=recovery_spec(image_receipt('python')['image'], '512Mi'),
                                   workspace='default', owner=owner, receipts=lifecycle_receipts, limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as lifecycle:
                driver = AdapterHarness(lifecycle, observed)
                for mode in ('worker-loss', 'result-storage-refusal'):
                    record = {'mode': mode}; summary['sandboxes'].append(record)
                    driver.creation = uuid4()
                    name = 'cs-' + driver.creation.hex[:16]
                    execution_receipts = kube.evidence / (mode + '-receipts')
                    execution_receipts.mkdir(mode=0o700)
                    fd = os.open(execution_receipts, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    identity = directory_identity(fd)
                    record['receipt_directory_identity'] = identity
                    try:
                        with owned(kube, native, driver, record, '512Mi', name=name):
                            handle = driver.handle
                            assert handle.id == record['sandbox_id']
                            operation = uuid4(); record['operation'] = str(operation)
                            controller = process_identity(os.getpid()); record['controller'] = controller
                            before = set(multiprocessing.active_children())
                            done = threading.Event()
                            observer_evidence = kube.evidence / (mode + '-observer-sdk')
                            observer_evidence.mkdir(mode=0o700)
                            with SandboxClient(native['endpoint'], tls=tls, timeout=2) as observer_client, \
                                 OpenShellExecution(connection, workspace='default', owner=owner,
                                    workdir='/tmp', limits=limits, receipts=execution_receipts) as adapter:
                                # Pinned exec_stream uses max(client timeout, execution timeout+10):
                                # these read-only observer calls therefore have a 12s native RPC bound.
                                observer_sdk = SdkReceipts(observer_client, observer_evidence)
                                actor = threading.Thread(target=observe_then_fault, args=(observer_sdk, handle,
                                    operation, mode, controller, before, limits, execution_receipts, fd,
                                    identity, record, done), name='qualification-fault-observer')
                                actor.start()
                                try:
                                    summary['application_execution_attempts'] += 1
                                    with pytest.raises(ExecutionError) as failure:
                                        adapter.execute(handle, fixed_command(operation, mode), operation)
                                    receipt = failure.value.receipt
                                    record['execution'] = serialized(receipt)
                                finally:
                                    done.set(); actor.join(timeout=15)
                                    record['observer_joined'] = not actor.is_alive()
                                    record['observer_sdk_calls'] = observer_sdk.counter
                                    assert not actor.is_alive(), 'Fault observer still owns native activity; cleanup unconfirmed'
                                    check_directory(execution_receipts, fd, identity)
                                    os.fchmod(fd, 0o700)
                                    record['receipt_directory_restored'] = stat.S_IMODE(os.fstat(fd).st_mode) == 0o700
                            assert not record.get('fault_error') and record.get('fault_delivered')
                            assert receipt.handle.id == handle.id and receipt.worker_cleanup == 'confirmed'
                            assert receipt.worker_limit_applied and receipt.native_calls == ('get', 'exec_stream')
                            assert (receipt.worker_glibc, receipt.worker_allocator_arenas) == ('2.39', 2)
                            start_bytes = json.dumps({k: record['remote_start'][k]
                                for k in ('operation', 'pid', 'start_ticks')}).encode() + b'\n'
                            assert receipt.stderr == b'' and len(receipt.stdout) <= limits.output_bytes
                            if mode == 'worker-loss':
                                assert (receipt.reason, receipt.delivery, receipt.completion) == ('worker_loss', 'unknown', 'unknown')
                                assert receipt.worker_pid == record['original_worker']['pid'] and receipt.worker_exit == -signal.SIGKILL
                                assert record['signal_attempts'] == 1
                                assert list(receipt.worker_cpu_affinity) == record['original_worker']['cpu_affinity']
                                assert not Path(f'/proc/{receipt.worker_pid}').exists(), 'Original worker is not reaped'
                                # Killing the worker can occur before any queued stdout reaches the parent.
                                assert start_bytes.startswith(receipt.stdout)
                                remote = start_observation(observed.sdk, handle, operation)
                                assert remote['started'] and not remote['finished'] and remote['state'] == 'S'
                                assert (remote['pid'], remote['start_ticks']) == (record['remote_start']['pid'], record['remote_start']['start_ticks'])
                                record['remote_after_worker_loss'] = remote
                                saved = json.loads((execution_receipts / f'{operation}.result.json').read_text())
                                assert saved == json.loads(json.dumps(serialized(receipt)))
                                result_identity = file_identity(execution_receipts / f'{operation}.result.json')
                            else:
                                assert isinstance(failure.value.__cause__, PermissionError) and failure.value.__cause__.errno == 13, 'Actual EACCES result write was not observed'
                                assert receipt.storage_error.startswith('PermissionError:')
                                assert (receipt.reason, receipt.delivery, receipt.completion, receipt.native_exit) == ('terminal', 'acknowledged', 'terminal_observed', 0)
                                assert receipt.worker_exit == 0
                                assert receipt.stdout == start_bytes
                                assert not (execution_receipts / f'{operation}.result.json').exists()
                                record['restart_inference'] = 'parent observed intent present and authoritative result absent; a later reader must retain unknown delivery'
                                result_identity = None
                            intent = execution_receipts / f'{operation}.intent.json'
                            assert json.loads(intent.read_text())['operation'] == str(operation)
                            assert stat.S_IMODE(intent.stat().st_mode) == 0o600
                            intent_identity = file_identity(intent)
                        assert record['cleanup_confirmed'] and record['container_tasks_absent']
                        # Only persisted host evidence is available to this new
                        # isolated process, after original sandbox teardown.
                        check_directory(execution_receipts, fd, identity)
                        command = reader_command(execution_receipts, operation, asdict(handle), identity,
                                                 intent_identity, result_identity)
                        record['reader_selection'] = json.loads(command[-1])
                        command_number = kube.counter + 1
                        fresh = kube.native(command, timeout=10)
                        assert fresh.stderr == ''
                        reader = record['fresh_reader'] = json.loads(fresh.stdout)
                        record['reader_command_receipt'] = f'command-{command_number:04d}.json'
                        assert reader['operation'] == str(operation) and reader['handle'] == asdict(handle)
                        assert reader['root_identity'] == identity and reader['delivery'] == reader['completion'] == 'unknown'
                        assert reader['replay_permitted'] is False and reader['pid'] != controller['pid']
                        assert not Path(f"/proc/{reader['pid']}").exists(), 'Fresh reader was not reaped'
                        assert reader['result_present'] == (mode == 'worker-loss')
                        assert reader['observation'] == ('persisted_worker_loss' if mode == 'worker-loss'
                                                         else 'intent_without_authoritative_result')
                        record['fresh_reader_reaped'] = True
                    finally:
                        check_directory(execution_receipts, fd, identity)
                        os.fchmod(fd, 0o700)
                        os.close(fd)
        assert all(r['outcome'] == 'passed' and r['cleanup_confirmed'] and r['container_tasks_absent']
                   for r in summary['sandboxes'])
        summary['outcome'] = 'passed'
    finally:
        (kube.evidence / 'execution-faults.json').write_text(json.dumps(summary, indent=2))
