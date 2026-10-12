"""One actual execution transport loss, no workload replay or cancellation API.

The exclusive pytest parent owns the exact original gateway-forward Popen object.
Physical identities are additional checks, not atomic expected-start signalling.
"""
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleLimits
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution, serialized
from corsair.ports.execution import ExecutionError, ExecutionLimits
from tests.qualification.gateway import gateway
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.test_adapter_execution_storage_failure import (
    fixed_command, owned_worker, process_identity, start_observation,
)
from tests.qualification.test_adapter_lifecycle import AdapterHarness, ObservedClient, adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import PYTHON, owned, recovery_spec


def forward_identity(process, expected_argv, controller):
    """Require the original live child and exact native invocation before signalling."""
    assert process.poll() is None, 'Original forward ended before deliberate transport loss'
    assert process.args == expected_argv
    assert process_identity(controller['pid'])['start_ticks'] == controller['start_ticks']
    value = process_identity(process.pid)
    assert value['ppid'] == controller['pid']
    assert Path(f'/proc/{process.pid}').stat().st_uid == os.geteuid()
    argv = Path(f'/proc/{process.pid}/cmdline').read_bytes().split(b'\0')[:-1]
    assert argv == [arg.encode() for arg in expected_argv]
    return dict(value, uid=os.geteuid(), argv=expected_argv,
                ownership='original fixture-owned subprocess.Popen object')


def terminate_forward(process, original, expected_argv, controller, record):
    current = forward_identity(process, expected_argv, controller)
    assert (current['pid'], current['start_ticks']) == (original['pid'], original['start_ticks'])
    record['signal_attempts'] = 1
    process.terminate()
    record['fault_delivered'] = 'original-owned-Popen.terminate'
    process.wait(timeout=10)
    record['original_forward_exit'] = process.returncode
    record['original_forward_reaped'] = process.poll() is not None
    assert process.returncode == -signal.SIGTERM and record['original_forward_reaped']
    assert not Path(f'/proc/{process.pid}').exists(), 'Original forward was not reaped'


def observe_then_interrupt(sdk, handle, operation, controller, before, limits,
                           forward, original, argv, record, done):
    try:
        deadline = time.monotonic() + 5
        while not done.is_set():
            value = start_observation(sdk, handle, operation)
            record.setdefault('start_observations', []).append(value)
            if value['started']:
                assert not value['finished'] and value['state'] == 'S'
                record['remote_start'] = value
                break
            assert time.monotonic() < deadline, 'Actual remote start unavailable; no replay'
            done.wait(.05)
        else:
            raise AssertionError('Execution ended before start proof; no transport fault delivered')
        assert not done.is_set(), 'Execution ended before deliberate transport loss'
        _, worker = owned_worker(controller, before, limits.worker_memory_bytes)
        record['original_worker'] = worker
        terminate_forward(forward, original, argv, controller, record)
    except BaseException as error:
        record['fault_error'] = f'{type(error).__name__}: {error}'


def restore_forward(kube, native, original, controller, record):
    """Reuse documented native forwarding; the gateway fixture owns every Popen."""
    if original.poll() is None:
        record['forward_recovery'] = 'not_needed_original_alive'
        return
    original.wait(timeout=10)
    port = native['endpoint'].rsplit(':', 1)[1]
    argv = kube.argv + ['port-forward', '-n', 'openshell', 'svc/openshell',
                       '--address=127.0.0.1', f'{port}:8080']
    log_path = kube.evidence/'transport-replacement-port-forward.log'
    log = log_path.open('x')
    try:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
    except BaseException:
        log.close()
        raise
    native['port_forwards'].append((process, log))
    record['replacement_forward_pid'] = process.pid
    deadline = time.monotonic() + 15
    while f'Forwarding from 127.0.0.1:{port}' not in log_path.read_text():
        assert process.poll() is None and time.monotonic() < deadline, 'Replacement forward unavailable'
        time.sleep(.2)
    record['replacement_forward'] = forward_identity(process, argv, controller)
    record['forward_recovery'] = 'native_forward_ready_same_endpoint'


def after_loss_code(operation):
    # Absence of the original process is an observation, not a cancellation proof.
    token = operation.hex
    return f'''import json
from pathlib import Path
p=Path('/tmp')/('exec-fault-'+{token!r}+'.json')
r=json.loads(p.read_text());assert r['operation']=={token!r}
proc=Path('/proc')/str(r['pid'])/'stat'
try:
 fields=proc.read_text().rsplit(')',1)[1].split()
 r.update(process_present=True,observed_start_ticks=fields[19],state=fields[0])
except FileNotFoundError:
 r.update(process_present=False,observed_start_ticks=None,state=None)
r['finished']=Path(str(p)[:-5]+'.finished').exists()
print(json.dumps(r))
'''


def after_loss_observation(sdk, handle, operation):
    result = sdk.call('exec', handle.name, [PYTHON, '-c', after_loss_code(operation)], workspace=handle.workspace,
                      workdir='/tmp', no_login_shell=True, timeout_seconds=2)
    assert result.exit_code == 0 and result.stderr == ''
    return json.loads(result.stdout)


@pytest.mark.execution_transport
def test_actual_transport_loss_unknown_execution_and_original_cleanup(kube, adapter_gateway):
    native = adapter_gateway
    sources = ['tests/qualification/test_execution_transport.py',
               'tests/qualification/test_adapter_execution_storage_failure.py',
               'src/corsair/ports/execution.py', 'src/corsair/ports/sandbox.py',
               'src/corsair/adapters/openshell.py', 'src/corsair/adapters/openshell_execution.py',
               'src/corsair/adapters/receipts.py', 'tests/qualification/test_adapter_lifecycle.py',
               'tests/qualification/test_recovery.py', 'tests/qualification/test_lifecycle.py',
               'tests/qualification/test_policy.py', 'tests/qualification/gateway.py',
               'tests/qualification/support.py', 'deploy/runtime-lock.yaml',
               'policies/openshell/identity.yaml', 'Makefile', 'pyproject.toml', 'uv.lock']
    (kube.evidence/'execution-transport-source-hashes.json').write_text(json.dumps(
        {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}, indent=2))
    record = {'outcome':'failed', 'application_execution_attempts':0, 'application_retries':0,
              'native_internal_rpc_polls_retries':'unknown', 'remote_cancellation':'unproven'}
    owner = uuid4()
    limits = ExecutionLimits(4096, 2, 20, 512*1024*1024)
    record['limits'] = asdict(limits)
    controller = process_identity(os.getpid()); record['controller'] = controller
    assert len(native['port_forwards']) == 1, 'Transport case requires one original owned forward'
    forward = native['port_forwards'][0][0]
    port = native['endpoint'].rsplit(':',1)[1]
    argv = kube.argv+['port-forward','-n','openshell','svc/openshell','--address=127.0.0.1',f'{port}:8080']
    original = record['original_forward'] = forward_identity(forward, argv, controller)
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'],native['mtls']/'ca.crt',native['mtls']/'tls.crt',native['mtls']/'tls.key')
    lifecycle_receipts = kube.evidence/'transport-lifecycle-receipts'; lifecycle_receipts.mkdir(mode=0o700)
    execution_receipts = kube.evidence/'transport-execution-receipts'; execution_receipts.mkdir(mode=0o700)
    observer_evidence = kube.evidence/'transport-observer-sdk'; observer_evidence.mkdir(mode=0o700)
    try:
        with ExitStack() as clients:
            client = clients.enter_context(SandboxClient(native['endpoint'],tls=tls,timeout=60))
            observed = ObservedClient(SdkReceipts(client,kube.evidence))
            with OpenShellLifecycle(observed,spec=recovery_spec(image_receipt('python')['image'],'512Mi'),
                    workspace='default',owner=owner,receipts=lifecycle_receipts,limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as lifecycle:
                driver = AdapterHarness(lifecycle,observed); driver.creation=uuid4()
                sandbox = record['sandbox'] = {}
                with owned(kube,native,driver,sandbox,'512Mi',name='cs-'+driver.creation.hex[:16]):
                    handle = driver.handle
                    operation = uuid4(); record['operation'] = str(operation)
                    before = set(multiprocessing.active_children()); done=threading.Event()
                    with SandboxClient(native['endpoint'],tls=tls,timeout=2) as observer_client, \
                         OpenShellExecution(connection,workspace='default',owner=owner,workdir='/tmp',
                                            limits=limits,receipts=execution_receipts) as adapter:
                        observer_sdk = SdkReceipts(observer_client,observer_evidence)
                        actor = threading.Thread(target=observe_then_interrupt,args=(observer_sdk,handle,
                            operation,controller,before,limits,forward,original,argv,record,done),
                            name='qualification-transport-observer')
                        actor.start()
                        try:
                            record['application_execution_attempts'] += 1
                            with pytest.raises(ExecutionError) as failure:
                                adapter.execute(handle,fixed_command(operation,'worker-loss'),operation)
                            receipt = failure.value.receipt; record['execution']=serialized(receipt)
                        finally:
                            done.set(); actor.join(timeout=15)
                            record['observer_joined'] = not actor.is_alive()
                            record['observer_sdk_calls'] = observer_sdk.counter
                            assert not actor.is_alive(), 'Observer activity still owned; cleanup unconfirmed'
                            if forward.poll() is not None:
                                captured = record.get('execution'); worker = record.get('original_worker')
                                assert captured and worker and captured['worker_cleanup']=='confirmed', 'Worker cleanup unknown; do not reconnect'
                                assert captured['worker_pid']==worker['pid'] and not Path(f"/proc/{worker['pid']}").exists(), 'Original worker reap unconfirmed; do not reconnect'
                                record['worker_reap_before_reconnect'] = True
                                observer_client.close(); client.close()
                                restore_forward(kube,native,forward,controller,record)
                                observed.sdk.client = clients.enter_context(SandboxClient(native['endpoint'],tls=tls,timeout=60))
                                record['native_client_reopened'] = True
                            else:
                                record['forward_recovery'] = 'not_needed_original_alive'
                                record['native_client_reopened'] = False
                    assert not record.get('fault_error') and record.get('fault_delivered')
                    assert receipt.handle.id==handle.id and receipt.worker_cleanup=='confirmed'
                    assert receipt.worker_pid==record['original_worker']['pid'] and not Path(f'/proc/{receipt.worker_pid}').exists()
                    assert receipt.worker_limit_applied and receipt.native_calls==('get','exec_stream')
                    assert (receipt.worker_glibc,receipt.worker_allocator_arenas)==('2.39',2)
                    assert receipt.reason=='native_error' and receipt.failure_layer=='native_execution', 'Different actual failure retained; no transport pass'
                    assert receipt.delivery==receipt.completion=='unknown' and receipt.native_exit is None
                    assert receipt.error_type and receipt.error_detail and receipt.storage_error is None
                    # gRPC Core maps data transmitted before TCP connection loss to
                    # client UNAVAILABLE: https://grpc.github.io/grpc/core/md_doc_statuscodes.html
                    # Preserve any differing live result as failure; never widen to pass.
                    assert receipt.native_code=='UNAVAILABLE', 'Expected connection-loss status absent; actual failure retained'
                    assert receipt.worker_exit==0 and record['signal_attempts']==1
                    start_bytes = json.dumps({k:record['remote_start'][k] for k in ('operation','pid','start_ticks')}).encode()+b'\n'
                    assert receipt.stderr==b'' and start_bytes.startswith(receipt.stdout)
                    intent=json.loads((execution_receipts/f'{operation}.intent.json').read_text())
                    saved=json.loads((execution_receipts/f'{operation}.result.json').read_text())
                    assert intent['operation']==str(operation) and saved==json.loads(json.dumps(serialized(receipt)))
                    assert observed.sdk.call('get',handle.name,workspace=handle.workspace).id==handle.id
                    remote = record['remote_after_transport_loss'] = after_loss_observation(observed.sdk,handle,operation)
                    assert all(remote[k]==record['remote_start'][k] for k in ('operation','pid','start_ticks'))
                    if remote['process_present']:
                        assert remote['observed_start_ticks']==remote['start_ticks'], 'Original remote PID replaced'
                    assert not remote['finished'], 'Fixture unexpectedly finished before teardown'
                assert sandbox['cleanup_confirmed'] and sandbox['container_tasks_absent'] and sandbox['outcome']=='passed'
            record['helper_sdk_calls']=observed.sdk.counter
        record['outcome']='passed'
    except BaseException as error:
        record.update(error_type=type(error).__name__,error_detail=str(error))
        raise
    finally:
        (kube.evidence/'execution-transport.json').write_text(json.dumps(record,indent=2))
