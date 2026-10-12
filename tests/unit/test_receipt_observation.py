"""Actual fresh stdlib processes read protected receipt fixtures only."""
from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from corsair.adapters.openshell_execution import serialized
from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from tests.qualification.receipt_observation import file_identity, reader_command


def fixture(tmp_path, persisted):
    root = tmp_path / 'receipts'; root.mkdir(mode=0o700)
    operation = uuid4()
    handle = SandboxHandle(str(uuid4()), 'cs-fixture', 'default', str(uuid4()), str(uuid4()))
    receipt = ExecutionReceipt(str(operation), handle, 'fixture', 0, 'not_dispatched', 'unknown', 'pending')
    with closing(ReceiptDirectory(root)) as journal:
        journal.write(operation, 'intent', dict(serialized(receipt),
                      pending_delivery='unknown until an authoritative result is observed'))
        if persisted:
            journal.write(operation, 'result', serialized(replace(receipt, reason='worker_loss', delivery='unknown',
                          failure_layer='host_supervision', worker_exit=-9, worker_cleanup='confirmed')))
    info = root.stat()
    identity = dict(dev=info.st_dev, inode=info.st_ino, uid=info.st_uid)
    intent = root / f'{operation}.intent.json'
    result = root / f'{operation}.result.json'
    command = reader_command(root, operation, asdict(handle), identity, file_identity(intent),
                             file_identity(result) if persisted else None)
    return root, intent, result, command


@pytest.mark.parametrize('persisted', [False, True])
def test_fresh_process_observes_only_persisted_unknown_state(tmp_path, persisted):
    root, intent, result, command = fixture(tmp_path, persisted)
    selection = json.loads(command[-1])
    assert set(selection) == {'operation', 'handle', 'root_identity', 'intent_identity', 'result_identity'}
    native = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert native.returncode == 0 and native.stderr == ''
    observation = json.loads(native.stdout)
    assert observation['delivery'] == observation['completion'] == 'unknown'
    assert observation['replay_permitted'] is False
    assert observation['result_present'] == persisted
    assert observation['intent_sha256'] == hashlib.sha256(intent.read_bytes()).hexdigest()
    assert observation['result_sha256'] == (hashlib.sha256(result.read_bytes()).hexdigest() if persisted else None)
    assert observation['pid'] != os.getpid() and not Path(f"/proc/{observation['pid']}").exists()


@pytest.mark.parametrize('mutation', ['root-replacement', 'intent-symlink', 'intent-fifo',
                                    'intent-hardlink', 'operation-mismatch', 'unexpected-result'])
def test_fresh_process_refuses_replaced_or_unbound_evidence(tmp_path, mutation):
    root, intent, result, command = fixture(tmp_path, False)
    if mutation == 'root-replacement':
        root.rename(tmp_path / 'original'); root.mkdir(mode=0o700)
    elif mutation in ('intent-symlink', 'intent-fifo'):
        intent.rename(root / 'original')
        if mutation == 'intent-symlink': intent.symlink_to(root / 'original')
        else: os.mkfifo(intent, mode=0o600)
    elif mutation == 'intent-hardlink':
        os.link(intent, root / 'additional-link')
    elif mutation == 'operation-mismatch':
        value = json.loads(intent.read_text()); value['operation'] = str(uuid4())
        intent.write_text(json.dumps(value))
        selection = json.loads(command[-1]); selection['intent_identity'] = file_identity(intent)
        command[-1] = json.dumps(selection)
    else:
        result.write_text('{}'); result.chmod(0o600)
    native = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert native.returncode != 0 and native.stdout == ''
