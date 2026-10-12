"""Real host supervision contracts; no external boundary qualification."""
from dataclasses import replace
import json
import multiprocessing
import os
import resource
import time
from uuid import uuid4

import pytest

from corsair.adapters import openshell_execution as module
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.ports.execution import ExecutionLimits, ExecutionError
from corsair.ports.sandbox import SandboxHandle


def fixture_worker(pipe, connection, handle, command, workdir, limits):
    mode=command[0]
    if mode=='lost': os._exit(3)
    if mode=='hang': time.sleep(10);return
    if mode=='error':
        pipe.send(('error',dict(delivery='unknown',error_type='NativeFailure',error_detail='original native cause',native_code='UNAVAILABLE',native_status='native status',failure_layer='native_execution')));return
    pipe.send(('dispatch', {'memory_limit':(limits.worker_memory_bytes,)*2,'cpu_affinity':[0],'glibc':'2.39','allocator_arenas':2}))
    pipe.send(('stdout',b'\xffabc'))
    pipe.send(('stderr',b'err'))
    if mode=='overflow':pipe.send(('output_limit',123))
    else:pipe.send(('terminal',{'exit':124 if mode=='timeout' else 7,'maxrss_kib':123}))
    pipe.close()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    for name in ('ca','cert','key'): (tmp_path/name).touch()
    owner=uuid4()
    connection=OpenShellConnection('explicit.fixture:1',*(tmp_path/n for n in ('ca','cert','key')))
    limits=ExecutionLimits(7,1,2,512*1024*1024)
    handle=SandboxHandle(str(uuid4()),'owned','default',str(owner),str(uuid4()))
    fork=multiprocessing.get_context('fork')
    monkeypatch.setattr(module.multiprocessing,'get_context',lambda _:fork)
    monkeypatch.setattr(module,'native_worker',fixture_worker)
    with OpenShellExecution(connection,workspace='default',owner=owner,workdir='/tmp',limits=limits,receipts=tmp_path) as adapter:
        yield adapter,handle,tmp_path


def test_binary_nonzero_and_host_receipt_survive_fresh_reader(setup):
    adapter,handle,path=setup;op=uuid4()
    r=adapter.execute(handle,('nonzero',),op)
    assert (r.stdout,r.stderr,r.native_exit,r.delivery,r.completion)==(b'\xffabc',b'err',7,'acknowledged','terminal_observed')
    assert r.worker_cleanup=='confirmed' and r.worker_exit==0
    result=json.loads((path/f'{op}.result.json').read_text())
    assert result['stdout_base64']=='/2FiYw==' and result['stdout_bytes']+result['stderr_bytes']==7
    assert (path/f'{op}.result.json').stat().st_mode & 0o777==0o600
    with pytest.raises(ExecutionError) as e: adapter.execute(handle,('nonzero',),op)
    assert e.value.receipt.delivery=='not_dispatched' and e.value.receipt.reason=='intent_storage'


@pytest.mark.parametrize('mode,reason,delivery',[('overflow','output_limit','unknown'),('lost','worker_loss','unknown'),('hang','host_timeout','unknown'),('timeout','native_special_status','acknowledged'),('error','native_error','unknown')])
def test_uncertainty_is_preserved_and_worker_reaped(setup,mode,reason,delivery):
    adapter,handle,_=setup
    with pytest.raises(ExecutionError) as e:adapter.execute(handle,(mode,),uuid4())
    r=e.value.receipt
    assert (r.reason,r.delivery,r.completion,r.worker_cleanup)==(reason,delivery,'unknown','confirmed')
    assert len(r.stdout)+len(r.stderr)<=7
    if mode=='error': assert r.native_code=='UNAVAILABLE' and r.native_status=='native status'
    if mode=='hang':assert r.worker_exit<0


def test_handle_refusal_precedes_spawn(setup):
    adapter,handle,_=setup
    with pytest.raises(ExecutionError) as e:adapter.execute(replace(handle,owner=str(uuid4())),('nonzero',),uuid4())
    assert e.value.receipt.delivery=='not_dispatched' and e.value.receipt.worker_pid is None


def test_storage_failure_preserves_terminal_and_output(setup,monkeypatch):
    adapter,handle,_=setup;original=adapter._journal.write
    def write(op,suffix,value):
        if suffix=='result':raise OSError('disk full after terminal')
        original(op,suffix,value)
    monkeypatch.setattr(adapter._journal,'write',write)
    with pytest.raises(ExecutionError) as e:adapter.execute(handle,('nonzero',),uuid4())
    r=e.value.receipt
    assert r.storage_error and r.native_exit==7 and r.stdout==b'\xffabc' and r.worker_cleanup=='confirmed'


@pytest.mark.parametrize('command',[[],(),('x\x00',),('x'*16385,)])
def test_invalid_command_never_dispatches(setup,command):
    adapter,handle,_=setup
    with pytest.raises(ValueError):adapter.execute(handle,command,uuid4())


def allocation_worker(pipe):
    profile=module.host_profile(512*1024*1024)
    assert profile['glibc']=='2.39' and profile['allocator_arenas']==2 and len(profile['cpu_affinity'])==1
    try:bytearray(1024*1024*1024)
    except MemoryError:pipe.send('bounded')
    else:pipe.send('UNBOUNDED')
    pipe.close()


def test_linux_hard_address_space_limit_rejects_excess_allocation():
    context=multiprocessing.get_context('spawn');parent,child=context.Pipe(False)
    process=context.Process(target=allocation_worker,args=(child,));process.start();child.close()
    try:
        assert parent.poll(5) and parent.recv()=='bounded'
        process.join(5);assert process.exitcode==0
    finally:
        if process.is_alive():process.kill();process.join(5)
        parent.close();process.close()


def test_start_failure_is_conservatively_unknown(setup,monkeypatch):
    adapter,handle,_=setup
    def fail(self): raise OSError('start delivery uncertain')
    monkeypatch.setattr(multiprocessing.process.BaseProcess,'start',fail)
    with pytest.raises(ExecutionError) as e:adapter.execute(handle,('nonzero',),uuid4())
    assert e.value.receipt.delivery=='unknown' and e.value.receipt.worker_cleanup=='unconfirmed'
