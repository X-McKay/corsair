"""Bounded observations of the pinned native default, never an SLO."""
import hashlib
import inspect
import json
import pytest
from openshell import SandboxClient, TlsConfig
from tests.qualification.support import ROOT
from tests.qualification.test_recovery import owned
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_policy import require_network
from tests.qualification.gateway import gateway

@pytest.fixture
def readiness_gateway(kube, request):
    require_network(kube, request.config.getoption('--network-evidence'))
    return request.getfixturevalue('gateway')

@pytest.mark.readiness
def test_native_default_readiness_sample(kube, readiness_gateway):
    native = readiness_gateway
    paths = ['tests/qualification/test_readiness.py','tests/qualification/test_recovery.py','tests/qualification/gateway.py','tests/qualification/test_lifecycle.py','tests/qualification/test_policy.py','tests/qualification/support.py','deploy/runtime-lock.yaml','policies/openshell/identity.yaml','pyproject.toml','uv.lock']
    (kube.evidence/'readiness-source-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},indent=2))
    default = inspect.signature(SandboxClient.wait_ready).parameters['timeout_seconds'].default
    assert default == 300.0
    summary = {'outcome':'failed','default_seconds':default,'sandboxes':[], 'internal_rpc_polls_retries':'unknown'}
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
    with SandboxClient(native['endpoint'],tls=tls,timeout=60) as connection:
        sdk = SdkReceipts(connection,kube.evidence)
        try:
            for index in range(3):
                record = {'index':index+1};summary['sandboxes'].append(record)
                before = sdk.counter
                with owned(kube,native,sdk,record,'512Mi'):
                    for number, key in [(before+1,'create_seconds'),(before+2,'wait_ready_seconds')]:
                        receipt = json.loads((kube.evidence/f'sdk-{number:04d}.json').read_text())
                        assert receipt['completion']=='acknowledged'
                        record[key] = receipt['elapsed_seconds']
                    assert 'timeout_seconds' not in json.loads((kube.evidence/f'sdk-{before+2:04d}.json').read_text())['kwargs']
            assert all(r['outcome']=='passed' and r['cleanup_confirmed'] and r['container_tasks_absent'] for r in summary['sandboxes'])
            summary['outcome']='passed'
        finally:
            summary['sdk_method_calls']=sdk.counter
            (kube.evidence/'readiness.json').write_text(json.dumps(summary,indent=2))
