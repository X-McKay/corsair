"""Actual local artifacts plus simulated receipts, never live application verdicts."""
from dataclasses import asdict, replace
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from corsair.adapters.local_artifacts import ArtifactStorageError, LocalArtifacts
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.reports.test_observations import consume_test_report


@pytest.fixture
def case(tmp_path):
    root = tmp_path / 'objects'; root.mkdir(mode=0o700)
    operation = uuid4()
    handle = SandboxHandle(str(uuid4()), 'fixture', 'default', str(uuid4()), str(uuid4()))
    with LocalArtifacts(root, max_bytes=8192) as store:
        source, tests = store.put(b'source fixture'), store.put(b'two frozen tests')
        payload = dict(schema_version='test-observations-v1', operation=str(operation),
                       source_sha256=source.sha256, tests_sha256=tests.sha256,
                       control=dict(test_id='test_control', outcome='passed'),
                       security=dict(test_id='test_security', outcome='passed'))
        data = json.dumps(payload).encode()
        receipt = ExecutionReceipt(str(operation), handle, '2026-10-12T00:00:00Z', 0.1,
                                   'acknowledged', 'terminal_observed', 'terminal',
                                   stdout=data, native_exit=0, worker_cleanup='confirmed')
        kwargs = dict(receipt=receipt, operation=operation, handle=handle, source=source, tests=tests)
        yield store, root, payload, kwargs


def consume(case, *, payload=None, data=None, exit_code=0, receipt_changes=None):
    store, _, original, kwargs = case
    if data is None:
        data = json.dumps(original if payload is None else payload).encode()
    receipt = replace(kwargs['receipt'], stdout=data, native_exit=exit_code, **(receipt_changes or {}))
    return consume_test_report(store, store.put(data), **(kwargs | dict(receipt=receipt)))


@pytest.mark.parametrize('control,security,exit_code', [
    ('passed','passed',0), ('passed','failed',1), ('failed','passed',1), ('skipped','passed',0),
])
def test_retains_two_claims_without_security_disposition(case, control, security, exit_code):
    payload = case[2]
    payload['control']['outcome'], payload['security']['outcome'] = control, security
    result = consume(case, payload=payload, exit_code=exit_code)
    assert result.claims.control.outcome == control and result.claims.security.outcome == security
    assert result.source == case[3]['source'] and result.tests == case[3]['tests']
    assert not hasattr(result, 'finding') and not hasattr(result, 'fix')


@pytest.mark.parametrize('mutation', ['fix','version','operation','source','tests','same_test','extra_test','exit'])
def test_rejects_untrusted_authority_and_inconsistent_claims(case, mutation):
    payload = case[2]
    if mutation == 'fix': payload['fix'] = 'verified'
    elif mutation == 'version': payload['schema_version'] = 'future'
    elif mutation == 'operation': payload['operation'] = str(uuid4())
    elif mutation == 'source': payload['source_sha256'] = 'f'*64
    elif mutation == 'tests': payload['tests_sha256'] = 'f'*64
    elif mutation == 'same_test': payload['security']['test_id'] = payload['control']['test_id']
    elif mutation == 'extra_test': payload['extra'] = payload['control']
    with pytest.raises(ValueError): consume(case, payload=payload, exit_code=1 if mutation == 'exit' else 0)


@pytest.mark.parametrize('data', [b'\xff', b'{', b'{}'*2049,
    b'{"schema_version":"wrong","schema_version":"test-observations-v1"}', b'['*2000+b']'*2000])
def test_rejects_ambiguous_malformed_or_excessive_report(case, data):
    with pytest.raises(ValueError): consume(case, data=data)


@pytest.mark.parametrize('change', [dict(delivery='unknown'), dict(completion='unknown'),
    dict(worker_cleanup='unconfirmed'), dict(storage_error='EACCES'), dict(reason='worker_loss'),
    dict(operation=str(uuid4())), dict(failure_layer='native_execution')])
def test_incomplete_or_wrong_execution_is_not_admitted(case, change):
    with pytest.raises(ValueError): consume(case, receipt_changes=change)


def test_bytes_must_match_execution_and_corrupt_object_is_refused(case):
    store, root, _, kwargs = case
    ref = store.put(kwargs['receipt'].stdout)
    with pytest.raises(ValueError, match='exact observed stdout'):
        consume_test_report(store, ref, **(kwargs | dict(receipt=replace(kwargs['receipt'], stdout=b'other'))))
    path = root / ref.sha256
    path.chmod(0o600); path.write_bytes(b'x'*ref.size); path.chmod(0o400)
    with pytest.raises(ArtifactStorageError): consume_test_report(store, ref, **kwargs)


def test_fresh_process_consumes_retained_artifact(case, tmp_path):
    store, root, _, kwargs = case
    ref = store.put(kwargs['receipt'].stdout)
    # Operator metadata is distinct from untrusted workload report bytes.
    record = dict(operation=str(kwargs['operation']), handle=asdict(kwargs['handle']),
                  source=asdict(kwargs['source']), tests=asdict(kwargs['tests']), report=asdict(ref),
                  stdout_base64=base64.b64encode(kwargs['receipt'].stdout).decode(),
                  root_identity=[root.stat().st_dev, root.stat().st_ino])
    metadata = tmp_path/'operator.json'; metadata.write_text(json.dumps(record))
    program = '''import base64,json,os,sys
from pathlib import Path
from uuid import UUID
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.reports.test_observations import consume_test_report
m=json.loads(Path(sys.argv[2]).read_text());root=Path(sys.argv[1])
with LocalArtifacts(root,max_bytes=4096) as store:
 i=os.fstat(store._fd);assert [i.st_dev,i.st_ino]==m['root_identity']
 ref=ArtifactRef(**m['report']);handle=SandboxHandle(**m['handle']);data=base64.b64decode(m['stdout_base64'],validate=True)
 receipt=ExecutionReceipt(m['operation'],handle,'fixture',0.1,'acknowledged','terminal_observed','terminal',stdout=data,native_exit=0,worker_cleanup='confirmed')
 result=consume_test_report(store,ref,receipt=receipt,operation=UUID(m['operation']),handle=handle,source=ArtifactRef(**m['source']),tests=ArtifactRef(**m['tests']))
 print(result.report.sha256)
'''
    process = subprocess.run([sys.executable, '-c', program, str(root), str(metadata)],
                             env=os.environ | {'PYTHONPATH':str(Path(__file__).resolve().parents[2]/'src')},
                             capture_output=True, text=True, timeout=15, check=True)
    assert process.stdout.strip() == ref.sha256
