"""Native completed execution -> immutable host output, with original cleanup.

Qualifies only bounded SDK stdout/stderr composition. No source upload,
workload-file download, agent/workflow or interrupted-operation admission.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.local_artifacts import ArtifactStorageError, LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleLimits
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.ports.execution import ExecutionError, ExecutionLimits
from tests.qualification.test_adapter_lifecycle import ObservedClient, AdapterHarness, adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, recovery_spec, PYTHON
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.gateway import gateway

# The fresh trusted host process independently opens the private root and uses
# the real storage adapter, rather than comparing bytes cached by this parent.
READER = '''import hashlib,json,os,sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.artifacts import ArtifactRef
root=Path(sys.argv[2]);expected=json.loads(sys.argv[3]);refs=json.loads(sys.argv[4])
with LocalArtifacts(root,max_bytes=4096) as store:
    info=os.fstat(store._fd)
    assert [info.st_dev,info.st_ino]==expected
    result=[]
    for value in refs:
        ref=ArtifactRef(**value);data=store.get(ref)
        result.append(dict(sha256=hashlib.sha256(data).hexdigest(),size=len(data)))
print(json.dumps(dict(root_identity=expected,references=result),sort_keys=True))
'''

SOURCES = ['src/corsair/ports/artifacts.py', 'src/corsair/ports/execution.py',
           'src/corsair/ports/sandbox.py', 'src/corsair/adapters/local_artifacts.py',
           'src/corsair/adapters/openshell.py', 'src/corsair/adapters/openshell_execution.py',
           'src/corsair/adapters/receipts.py', 'tests/qualification/test_adapter_lifecycle.py',
           'tests/qualification/test_recovery.py', 'tests/qualification/gateway.py',
           'tests/qualification/test_lifecycle.py', 'tests/qualification/test_policy.py',
           'tests/qualification/support.py', 'deploy/runtime-lock.yaml',
           'policies/openshell/identity.yaml', 'pyproject.toml', 'uv.lock']


@pytest.mark.execution_artifacts
def test_completed_native_output_is_immutable_after_sandbox_cleanup(kube, adapter_gateway):
    native = adapter_gateway
    summary = {'outcome': 'failed', 'native_internal_rpc_polls_retries': 'unknown',
               'application_retries': 0, 'scope': 'bounded completed SDK stdout/stderr only',
               'storage_publication': 'not_started', 'sandbox': {}}
    (kube.evidence/'execution-artifact-source-hashes.json').write_text(json.dumps(
        dict({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
             qualification_file={'path': str(__file__), 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}), indent=2))
    receipts = kube.evidence/'host-receipts'; receipts.mkdir(mode=0o700)
    objects = kube.evidence/'output-objects'; objects.mkdir(mode=0o700)
    corrupt = kube.evidence/'corruption-fixture'; corrupt.mkdir(mode=0o700)
    identity = objects.stat(); root_identity = [identity.st_dev, identity.st_ino]
    summary['root_identity'] = root_identity
    owner = uuid4(); limits = ExecutionLimits(4096, 2, 20, 512*1024*1024)
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
    expected = (bytes(range(256))*4, b'host-output-control\x00\xff\r\n')
    refs = []
    try:
        with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client:
            observed = ObservedClient(SdkReceipts(client, kube.evidence))
            with OpenShellLifecycle(observed, spec=recovery_spec(image_receipt('python')['image'], '512Mi'), workspace='default', owner=owner, receipts=receipts, limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as lifecycle, OpenShellExecution(connection, workspace='default', owner=owner, workdir='/tmp', limits=limits, receipts=receipts) as adapter, LocalArtifacts(objects, max_bytes=4096) as store:
                driver = AdapterHarness(lifecycle, observed); driver.creation = uuid4()
                with owned(kube, native, driver, summary['sandbox'], '512Mi', name='cs-'+driver.creation.hex[:16]):
                    operation = uuid4(); summary['execution_operation'] = str(operation)
                    result = adapter.execute(driver.handle, (PYTHON, '-c', "import os;os.write(1,bytes(range(256))*4);os.write(2,b'host-output-control\\x00\\xff\\r\\n')"), operation)
                    assert result.delivery == 'acknowledged' and result.completion == 'terminal_observed' and result.native_exit == 0
                    assert result.worker_cleanup == 'confirmed' and (result.stdout, result.stderr) == expected
                    assert len(result.stdout)+len(result.stderr) <= limits.output_bytes
                    saved = json.loads((receipts/f'{operation}.result.json').read_text())
                    assert saved['handle']['id'] == driver.handle.id and saved['completion'] == 'terminal_observed'
                    summary['native_execution'] = {'delivery': result.delivery, 'completion': result.completion, 'exit': result.native_exit, 'worker_cleanup': result.worker_cleanup, 'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr)}
                    summary['storage_publication'] = 'in_progress'
                    for data in (result.stdout, result.stderr):
                        ref = store.put(data, expected_sha256=hashlib.sha256(data).hexdigest()); refs.append(asdict(ref))
                        summary['output_references'] = list(refs)
                        original = (objects/ref.sha256).stat()
                        assert stat.S_IMODE(original.st_mode) == 0o400 and store.get(ref) == data
                        assert store.put(data) == ref and (objects/ref.sha256).stat().st_ino == original.st_ino
                    summary['storage_publication'] = 'admitted'
                    summary['execution_seconds'] = result.elapsed_seconds
                assert summary['sandbox']['cleanup_confirmed'] and summary['sandbox']['container_tasks_absent']
                summary['lifecycle_operations'] = driver.operations
                summary['sdk_method_calls'] = observed.sdk.counter
        # Real fresh host process verifies references after original sandbox/tasks
        # are absent; authoritative objects are intentionally retained as evidence.
        reader = kube.native([sys.executable, '-c', READER, str(ROOT/'src'), str(objects), json.dumps(root_identity), json.dumps(refs)], timeout=20)
        assert len(reader.stdout.encode()) < 4096
        fresh = json.loads(reader.stdout)
        assert fresh == {'root_identity': root_identity, 'references': refs}
        summary['fresh_reader'] = fresh
        # Corrupt only a separate owned fixture, preserving admitted output bytes.
        with LocalArtifacts(corrupt, max_bytes=4096) as poisoned:
            ref = poisoned.put(expected[0]); path = corrupt/ref.sha256
            original = path.stat(); path.chmod(0o600); path.write_bytes(b'X'+expected[0][1:]); path.chmod(0o400)
            try:
                with pytest.raises(ArtifactStorageError): poisoned.get(ref)
                with pytest.raises(ArtifactStorageError): poisoned.put(expected[0])
                summary['corrupt_output_refused_without_overwrite'] = path.read_bytes() != expected[0]
                assert summary['corrupt_output_refused_without_overwrite']
            finally:
                current = path.stat(follow_symlinks=False)
                assert (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino), 'Corruption fixture replaced; refusing cleanup'
                path.unlink()
                assert not path.exists()
                summary['corruption_fixture_cleanup'] = 'confirmed'
        summary['outcome'] = 'passed'
    except ExecutionError as error:
        result = error.receipt
        summary['native_execution'] = {'delivery': result.delivery, 'completion': result.completion, 'exit': result.native_exit, 'reason': result.reason, 'worker_cleanup': result.worker_cleanup, 'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr), 'receipt_storage_error': result.storage_error}
        raise
    except ArtifactStorageError as error:
        summary['artifact_failure'] = {'error_type': type(error).__name__, 'detail': str(error), 'reference': asdict(error.reference) if error.reference else None, 'publication': error.publication, 'temporary_cleanup': error.temporary_cleanup, 'temporary_name': error.temporary_name, 'temporary_identity': error.temporary_identity}
        raise
    finally:
        (kube.evidence/'execution-artifacts.json').write_text(json.dumps(summary, indent=2))
