"""Real lifecycle adapter in the existing immutable-identity qualification harness."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleError, LifecycleLimits
from tests.qualification.support import ROOT
from tests.qualification.gateway import gateway
from tests.qualification.test_policy import require_network
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, recovery_spec
from tests.qualification.prepare_toolchains import image_receipt


class ObservedClient:
    """Keep actual native responses/receipts while the adapter calls the SDK."""
    def __init__(self, sdk):
        self.sdk=sdk;self.last={}
    def __getattr__(self, method):
        def call(*args, **kwargs):
            result=self.sdk.call(method,*args,**kwargs)
            self.last[method]=result
            return result
        return call


class AdapterHarness:
    """Route existing ownership helper lifecycle through the real adapter.

    Return original native responses, never synthesized deletion acknowledgements.
    Policy/exec checks and extra operator teardown observations stay native.
    """
    def __init__(self,adapter,observed):
        self.adapter=adapter;self.observed=observed;self.handle=None;self.operations=[];self.creation=None
    def call(self,method,*args,**kwargs):
        if method not in ('create','wait_ready','delete'):
            return getattr(self.observed,method)(*args,**kwargs)
        op=self.creation if method=='create' else uuid4();self.operations.append((method,str(op)))
        if method=='create':
            self.handle=self.adapter.create(op)
            return self.observed.last['create']
        assert args[0]==self.handle.name and kwargs['workspace']==self.handle.workspace
        if method=='wait_ready': self.adapter.wait_ready(self.handle,op)
        else: self.adapter.delete(self.handle,op)
        return self.observed.last[method]


@pytest.fixture
def adapter_gateway(kube,request):
    require_network(kube,request.config.getoption('--network-evidence'))
    return request.getfixturevalue('gateway')


@pytest.mark.adapter_lifecycle
def test_real_adapter_lifecycle_and_host_receipts(kube,adapter_gateway):
    native=adapter_gateway
    paths=['src/corsair/ports/sandbox.py','src/corsair/adapters/openshell.py','tests/unit/test_sandbox_lifecycle.py','tests/qualification/test_adapter_lifecycle.py','tests/qualification/test_recovery.py','tests/qualification/gateway.py','tests/qualification/test_lifecycle.py','tests/qualification/test_policy.py','tests/qualification/support.py','deploy/runtime-lock.yaml','policies/openshell/identity.yaml','pyproject.toml','uv.lock']
    (kube.evidence/'adapter-source-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},indent=2))
    summary={'outcome':'failed','sandboxes':[],'internal_rpc_polls_retries':'unknown',
             'delete_scope':'operator-exclusive workspace; no atomic expected-ID native delete'}
    receipts=kube.evidence/'host-receipts';receipts.mkdir(mode=0o700)
    tls=TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
    with SandboxClient(native['endpoint'],tls=tls,timeout=60) as client:
        observed=ObservedClient(SdkReceipts(client,kube.evidence))
        with OpenShellLifecycle(observed,spec=recovery_spec(image_receipt('python')['image'],'512Mi'),workspace='default',owner=uuid4(),receipts=receipts,limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as adapter:
            driver=AdapterHarness(adapter,observed)
            try:
                for index in range(3):
                    record={'index':index+1};summary['sandboxes'].append(record)
                    before=len(driver.operations)
                    driver.creation=uuid4()
                    name='cs-'+driver.creation.hex[:16]
                    with owned(kube,native,driver,record,'512Mi',name=name):
                        assert driver.handle.id==record['sandbox_id']
                        # A forged operator handle must not delete the real owned resource.
                        from dataclasses import replace
                        op=uuid4();counter=observed.sdk.counter
                        with pytest.raises(LifecycleError) as failure:
                            adapter.delete(replace(driver.handle,id=str(uuid4())),op)
                        assert failure.value.receipt.delivery=='not_dispatched'
                        assert failure.value.receipt.cleanup=='unconfirmed'
                        calls=[json.loads((kube.evidence/f'sdk-{n:04d}.json').read_text())['operation'] for n in range(counter+1,observed.sdk.counter+1)]
                        assert calls==['get'], 'Refused handle dispatched a mutation'
                        record['refused_identity_operation']=str(op)
                    record['operations']=driver.operations[before:]
                    results=[json.loads((receipts/f'{op}.result.json').read_text()) for _,op in record['operations']]
                    assert all(r['outcome']=='completed' and r['delivery']=='acknowledged' and r['handle']['id']==record['sandbox_id'] for r in results)
                    assert results[1]['phase']=='SANDBOX_PHASE_READY' and results[-1]['cleanup']=='confirmed'
                    record['timings_seconds']={r['action']:r['elapsed_seconds'] for r in results}
                    # Read authoritative files through a fresh host reader, without adapter memory.
                    for method,op in record['operations']:
                        assert json.loads((receipts/f'{op}.intent.json').read_text())['operation']==op
                        assert (receipts/f'{op}.result.json').stat().st_mode & 0o777==0o600
                assert all(r['cleanup_confirmed'] and r['container_tasks_absent'] and r['outcome']=='passed' for r in summary['sandboxes'])
                summary['outcome']='passed'
            finally:
                summary['sdk_method_calls']=observed.sdk.counter
                (kube.evidence/'adapter.json').write_text(json.dumps(summary,indent=2))
