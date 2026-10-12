"""Contract/failure tests only: these doubles never qualify an external boundary."""
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

import grpc
import pytest
from openshell import SandboxRef, SandboxStatusRef, DeletionOutcome, DeletionResult
from openshell._proto import openshell_pb2

from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleError


class NotFound(grpc.RpcError):
    def code(self): return grpc.StatusCode.NOT_FOUND
    def details(self): return 'absent'


class Native:
    def __init__(self):
        self.calls=[];self.current=None;self.create_error=None;self.delete_error=None
        self.ready_phase=openshell_pb2.SANDBOX_PHASE_READY
        self.delete_id=None
    def create(self, **kwargs):
        self.calls.append(('create',kwargs))
        if self.create_error: raise self.create_error
        self.current=SandboxRef(str(uuid4()),kwargs['name'],kwargs['workspace'],SandboxStatusRef(1,1),kwargs['labels'])
        return self.current
    def get(self, name, **kwargs):
        self.calls.append(('get',kwargs))
        if self.current is None: raise NotFound()
        return self.current
    def wait_ready(self,name,**kwargs):
        self.calls.append(('wait_ready',kwargs))
        return replace(self.current,status=SandboxStatusRef(self.ready_phase,1))
    def delete(self,name,**kwargs):
        self.calls.append(('delete',kwargs))
        if self.delete_error: raise self.delete_error
        sid=self.delete_id or self.current.id;self.current=None
        return DeletionResult(DeletionOutcome.ACCEPTED,sid)
    def wait_deleted(self,name,**kwargs): self.calls.append(('wait_deleted',kwargs))


@pytest.fixture
def setup(tmp_path):
    tmp_path.chmod(0o700)
    native=Native()
    spec=openshell_pb2.SandboxSpec(template=openshell_pb2.SandboxTemplate(image='fixture@sha256:'+'a'*64))
    with OpenShellLifecycle(native,spec=spec,workspace='default',owner=uuid4(),receipts=tmp_path) as adapter:
        yield native,adapter,tmp_path


def test_lifecycle_receipts_and_native_defaults(setup):
    native,adapter,path=setup
    creation,ready,deletion=uuid4(),uuid4(),uuid4()
    handle=adapter.create(creation);adapter.wait_ready(handle,ready);adapter.delete(handle,deletion)
    receipts=[json.loads((path/f'{op}.result.json').read_text()) for op in (creation,ready,deletion)]
    assert all(r['outcome']=='completed' and r['delivery']=='acknowledged' for r in receipts)
    assert receipts[-1]['cleanup']=='confirmed' and receipts[-1]['handle']['id']==handle.id
    assert all('timeout_seconds' not in kw for method,kw in native.calls if method=='wait_ready')
    assert next(kw for method,kw in native.calls if method=='wait_deleted')['expected_sandbox_id']==handle.id
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in path.iterdir())
    intent=json.loads((path/f'{creation}.intent.json').read_text())
    assert intent['requested_name']==handle.name and intent['spec_sha256']


def test_completed_never_authorizes_readiness(setup):
    native,adapter,_=setup;handle=adapter.create(uuid4());native.ready_phase=openshell_pb2.SANDBOX_PHASE_COMPLETED
    with pytest.raises(LifecycleError) as e: adapter.wait_ready(handle,uuid4())
    assert e.value.receipt.phase=='SANDBOX_PHASE_COMPLETED' and e.value.receipt.outcome=='failed'
    assert e.value.receipt.handle==handle


@pytest.mark.parametrize('replacement', ['id','owner','workspace','creation'])
def test_observed_replacement_refuses_delete(setup,replacement):
    native,adapter,_=setup;handle=adapter.create(uuid4())
    if replacement=='id': native.current=replace(native.current,id=str(uuid4()))
    elif replacement=='workspace': native.current=replace(native.current,workspace='foreign')
    else:
        labels=dict(native.current.labels);labels['corsair.owner' if replacement=='owner' else 'corsair.operation']=str(uuid4())
        native.current=replace(native.current,labels=labels)
    with pytest.raises(LifecycleError) as e: adapter.delete(handle,uuid4())
    assert e.value.receipt.delivery=='not_dispatched' and e.value.receipt.cleanup=='unconfirmed'
    assert not any(method=='delete' for method,_ in native.calls)


@pytest.mark.parametrize('action',['create','delete'])
def test_failed_mutation_is_unknown_and_never_retried(setup,action):
    native,adapter,_=setup;failure=TimeoutError('delivery unknown')
    if action=='create': native.create_error=failure;call=lambda:adapter.create(uuid4())
    else:
        handle=adapter.create(uuid4());native.delete_error=failure;call=lambda:adapter.delete(handle,uuid4())
    with pytest.raises(LifecycleError) as e: call()
    assert e.value.receipt.delivery=='unknown' and e.value.receipt.outcome=='unknown'
    assert e.value.__cause__ is failure
    assert sum(method==action for method,_ in native.calls)==1


def test_receipt_failure_before_dispatch_and_operation_reuse(setup,monkeypatch):
    native,adapter,path=setup;op=uuid4();adapter.create(op)
    with pytest.raises(LifecycleError) as e: adapter.create(op)
    assert e.value.receipt.delivery=='not_dispatched' and e.value.receipt.error_type=='FileExistsError'
    assert sum(method=='create' for method,_ in native.calls)==1
    def broken(*args): raise OSError('disk full')
    monkeypatch.setattr(adapter,'_write',broken)
    with pytest.raises(LifecycleError) as e: adapter.create(uuid4())
    assert e.value.receipt.delivery=='not_dispatched'
    assert sum(method=='create' for method,_ in native.calls)==1


@pytest.mark.parametrize('native_failure',[False,True])
def test_result_persistence_loss_retains_identity_or_native_failure(setup,monkeypatch,native_failure):
    native,adapter,_=setup;original=adapter._write
    def write(op,suffix,value):
        if suffix=='result': raise OSError('disk full after dispatch')
        return original(op,suffix,value)
    monkeypatch.setattr(adapter,'_write',write)
    if native_failure: native.create_error=TimeoutError('native delivery unknown')
    with pytest.raises(LifecycleError) as e: adapter.create(uuid4())
    receipt=e.value.receipt
    assert receipt.storage_error and sum(method=='create' for method,_ in native.calls)==1
    if native_failure: assert receipt.error_type=='TimeoutError' and receipt.delivery=='unknown'
    else: assert receipt.handle.id==native.current.id and receipt.delivery=='acknowledged'


def test_native_delete_identity_mismatch_is_unconfirmed(setup):
    native,adapter,_=setup;handle=adapter.create(uuid4());native.delete_id=str(uuid4())
    with pytest.raises(LifecycleError) as e: adapter.delete(handle,uuid4())
    assert e.value.receipt.delivery=='acknowledged' and e.value.receipt.cleanup=='unconfirmed'
    assert not any(method=='wait_deleted' for method,_ in native.calls)


def test_wait_deleted_replacement_is_not_confirmed(setup,monkeypatch):
    native,adapter,_=setup;handle=adapter.create(uuid4());replacement=replace(native.current,id=str(uuid4()))
    def wait(name,**kwargs): native.current=replacement
    monkeypatch.setattr(native,'wait_deleted',wait)
    with pytest.raises(LifecycleError) as e: adapter.delete(handle,uuid4())
    assert e.value.receipt.cleanup=='unconfirmed' and e.value.receipt.outcome=='failed'


def test_protected_host_directory_and_immutable_spec(setup, tmp_path):
    native,adapter,path=setup
    adapter.create(uuid4())
    spec=openshell_pb2.SandboxSpec(template=openshell_pb2.SandboxTemplate(image='mutable:tag'))
    with pytest.raises(ValueError): OpenShellLifecycle(native,spec=spec,workspace='default',owner=uuid4(),receipts=path)
    spec.template.image='fixed@sha256:'+'a'*64
    path.chmod(0o755)
    with pytest.raises(ValueError): OpenShellLifecycle(native,spec=spec,workspace='default',owner=uuid4(),receipts=path)


def test_operator_spec_is_snapshotted(tmp_path):
    tmp_path.chmod(0o700);native=Native()
    spec=openshell_pb2.SandboxSpec(template=openshell_pb2.SandboxTemplate(image='fixed@sha256:'+'b'*64))
    with OpenShellLifecycle(native,spec=spec,workspace='default',owner=uuid4(),receipts=tmp_path) as adapter:
        spec.template.image='operator-mutated:tag'
        adapter.create(uuid4())
        assert native.calls[0][1]['spec'].template.image=='fixed@sha256:'+'b'*64
