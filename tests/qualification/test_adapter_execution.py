"""Actual native execution adapter, with immutable lifecycle/resource cleanup."""
from dataclasses import replace
import hashlib
import json
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleLimits
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.ports.execution import ExecutionLimits, ExecutionError
from tests.qualification.test_adapter_lifecycle import ObservedClient, AdapterHarness, adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, recovery_spec, PYTHON
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.gateway import gateway

SOURCES=['src/corsair/ports/sandbox.py','src/corsair/ports/execution.py','src/corsair/adapters/openshell.py','src/corsair/adapters/openshell_execution.py','src/corsair/adapters/receipts.py','tests/unit/test_sandbox_execution.py','tests/unit/test_sandbox_lifecycle.py','tests/qualification/test_adapter_execution.py','tests/qualification/test_adapter_lifecycle.py','tests/qualification/test_recovery.py','tests/qualification/gateway.py','tests/qualification/test_lifecycle.py','tests/qualification/test_policy.py','tests/qualification/support.py','deploy/runtime-lock.yaml','policies/openshell/identity.yaml','pyproject.toml','uv.lock']


@pytest.mark.adapter_execution
def test_real_execution_limits_receipts_and_cleanup(kube,adapter_gateway):
    native=adapter_gateway
    (kube.evidence/'execution-source-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},indent=2))
    summary={'outcome':'failed','sandboxes':[], 'native_internal_rpc_polls_retries':'unknown'}
    receipts=kube.evidence/'host-receipts';receipts.mkdir(mode=0o700)
    owner=uuid4();limits=ExecutionLimits(4096,2,20,512*1024*1024)
    tls=TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
    connection=OpenShellConnection(native['endpoint'],native['mtls']/'ca.crt',native['mtls']/'tls.crt',native['mtls']/'tls.key')
    with SandboxClient(native['endpoint'],tls=tls,timeout=60) as client:
        observed=ObservedClient(SdkReceipts(client,kube.evidence))
        with OpenShellLifecycle(observed,spec=recovery_spec(image_receipt('python')['image'],'512Mi'),workspace='default',owner=owner,receipts=receipts,limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as lifecycle, OpenShellExecution(connection,workspace='default',owner=owner,workdir='/tmp',limits=limits,receipts=receipts) as adapter:
            driver=AdapterHarness(lifecycle,observed)
            try:
                for index in range(3):
                    record={'index':index+1,'execution_operations':[]};summary['sandboxes'].append(record)
                    driver.creation=uuid4();name='cs-'+driver.creation.hex[:16]
                    before=len(driver.operations)
                    with owned(kube,native,driver,record,'512Mi',name=name):
                        for mode,code in [
                            ('success',"import os;os.write(1,b'\\xffbinary\\n');os.write(2,b'control-stderr\\n')"),
                            ('nonzero',"import sys;print('deliberate-command-failure');sys.exit(7)"),
                            ('timeout',"import time;print('started',flush=True);time.sleep(90)"),
                            ('overflow',"import os\nwhile True:os.write(1,b'X'*65536)"),
                            ('refusal',"print('MUST-NOT-EXECUTE')")]:
                            op=uuid4();record['execution_operations'].append((mode,str(op)))
                            handle=replace(driver.handle,id=str(uuid4())) if mode=='refusal' else driver.handle
                            if mode in ('success','nonzero'):
                                r=adapter.execute(handle,(PYTHON,'-c',code),op)
                                assert r.delivery=='acknowledged' and r.completion=='terminal_observed'
                                assert r.native_exit==(0 if mode=='success' else 7)
                                if mode=='success':assert (r.stdout,r.stderr)==(b'\xffbinary\n',b'control-stderr\n')
                            else:
                                with pytest.raises(ExecutionError) as e:adapter.execute(handle,(PYTHON,'-c',code),op)
                                r=e.value.receipt
                                assert r.completion=='unknown'
                                if mode=='timeout':assert r.native_exit==124 and r.reason=='native_special_status' and r.stdout==b'started\n'
                                elif mode=='overflow':assert r.reason=='output_limit' and r.delivery=='unknown' and len(r.stdout)==4096 and r.stderr==b''
                                else:assert r.delivery=='not_dispatched' and r.native_calls==('get',) and r.stdout==r.stderr==b''
                            assert r.worker_cleanup=='confirmed' and r.worker_exit==0
                            assert len(r.stdout)+len(r.stderr)<=limits.output_bytes
                            if mode!='refusal':
                                assert r.worker_limit_applied and len(r.worker_cpu_affinity)==1 and r.worker_maxrss_kib is not None
                                assert (r.worker_glibc,r.worker_allocator_arenas)==('2.39',2)
                                assert r.native_calls==('get','exec_stream')
                            saved=json.loads((receipts/f'{op}.result.json').read_text())
                            assert saved['handle']['id']==handle.id and saved['reason']==r.reason
                            assert saved['stdout_bytes']+saved['stderr_bytes']<=4096
                            assert (receipts/f'{op}.intent.json').stat().st_mode & 0o777==0o600
                    record['lifecycle_operations']=driver.operations[before:]
                    assert record['cleanup_confirmed'] and record['container_tasks_absent']
                summary['outcome']='passed'
            finally:
                summary['lifecycle_native_method_calls']=observed.sdk.counter
                (kube.evidence/'execution.json').write_text(json.dumps(summary,indent=2))
