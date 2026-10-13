"""SPEC-0033 witness probe and record mapping, with the real probe in real pytest subprocesses."""
from dataclasses import replace
from hashlib import sha256
import json
import subprocess
import sys

import pytest

from corsair.core.disposition import SandboxEvent
from corsair.nodes.witness import BOOTSTRAP, PROBE_SHA256, PROBE_SOURCE, probe_argv, witness_evidence
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.test_runner import WitnessCapture, WitnessRequest

REQUEST = WitnessRequest('target.py', 'read')
COMMAND = ('python3.12', '-m', 'pytest', '-p', 'no:cacheprovider', '-q')
NONCE = 'nonce-1'
SECURITY = 'test_case.py::test_security'
TARGET = '''import errno, os
from pathlib import Path

def helper(path):
    return Path(path).read_text()

def read(root, name, error=None):
    if error == 'denied':
        raise PermissionError(errno.EACCES, 'denied')
    if error == 'reject':
        raise ValueError('outside')
    if error == 'swallow':
        try:
            open(os.path.join(root, 'missing.txt'))
        except FileNotFoundError:
            return None
    return helper(os.path.join(root, name))
'''


def run_probe(tmp_path, test_body, command=COMMAND, target=TARGET):
    (tmp_path / 'target.py').write_text(target)
    (tmp_path / 'test_case.py').write_text('import os\nfrom pathlib import Path\nimport target\n\n' + test_body)
    argv = probe_argv(command, REQUEST, root=str(tmp_path), record_path='witness.json', nonce=NONCE)
    argv = (sys.executable,) + argv[1:]
    done = subprocess.run(argv, cwd=tmp_path, capture_output=True, timeout=60, env={'PYTHONPATH': '.'})
    record = (tmp_path / 'witness.json').read_bytes() if (tmp_path / 'witness.json').exists() else b''
    return done, record


def capture(record, **changes):
    values = dict(status='captured', request=REQUEST, nonce=NONCE, probe_sha256=PROBE_SHA256, record=record,
                  artifact=ArtifactRef(sha256(record).hexdigest(), len(record)), detail='', receipt=None)
    return WitnessCapture(**(values | changes))


def mapped(tmp_path, body):
    done, record = run_probe(tmp_path, body)
    assert record, done.stdout.decode() + done.stderr.decode()
    return witness_evidence(capture(record), REQUEST, SECURITY), json.loads(record)


def test_argv_replaces_exactly_one_module_invocation():
    argv = probe_argv(COMMAND, REQUEST, root='/w', record_path='/tmp/r.json', nonce=NONCE)
    assert argv[:4] == ('python3.12', '-c', BOOTSTRAP, PROBE_SOURCE) and argv[5:] == COMMAND[3:]
    assert json.loads(argv[4]) == {'nonce': NONCE, 'record_path': '/tmp/r.json', 'root': '/w', 'target_path': 'target.py',
                                   'target_symbol': 'read', 'tool_id': 4}
    for command in (('python3.12', 'pytest'), COMMAND + ('-m', 'pytest')):
        with pytest.raises(ValueError, match='exactly one'):
            probe_argv(command, REQUEST, root='/w', record_path='r', nonce=NONCE)


@pytest.mark.parametrize('symbol', ['', 'a b', '1x', 'x.', 'a;b'])
def test_request_needs_a_plain_symbol_and_confined_path(symbol):
    with pytest.raises(ValueError):
        WitnessRequest('target.py', symbol)
    with pytest.raises(ValueError):
        WitnessRequest('../target.py', 'read')


def test_opens_inside_the_target_count_and_the_tests_own_reads_do_not(tmp_path):
    found, record = mapped(tmp_path, '''
def test_control(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    assert target.read(tmp_path, "a.txt") == "a"

def test_security(tmp_path):
    (tmp_path / "outside.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    assert (tmp_path / "outside.txt").read_text() == "x"   # the test's own read is not the effect
    target.read(tmp_path / "sub", "../outside.txt")
    assert False, "reached"
''')
    security = record['tests'][SECURITY]
    assert (security['entered'], security['exits'], len(security['opens'])) == (1, [None], 1)
    assert security['opens'][0].endswith('sub/../outside.txt') and record['intact']
    assert (found.witness.path_reached, found.witness.effect, found.witness.safe_behavior) == (True, 'observed', None)
    assert found.sandbox_events == () and found.reason == 'admitted'


def test_a_rejection_is_the_safe_behavior_without_any_open(tmp_path):
    found, _ = mapped(tmp_path, '''
import pytest
def test_security(tmp_path):
    with pytest.raises(ValueError):
        target.read(tmp_path, "../outside.txt", error="reject")
''')
    assert (found.witness.path_reached, found.witness.effect, found.witness.safe_behavior) == (True, 'absent', 'ValueError')


def test_a_target_never_called_has_no_path_reached(tmp_path):
    found, _ = mapped(tmp_path, 'def test_security():\n    assert True\n')
    assert (found.witness.path_reached, found.witness.effect, found.witness.safe_behavior) == (False, 'absent', None)


def test_a_permission_error_on_the_witness_path_is_a_sandbox_event(tmp_path):
    found, record = mapped(tmp_path, '''
import pytest
def test_security(tmp_path):
    with pytest.raises(PermissionError):
        target.read(tmp_path, "x", error="denied")
''')
    assert record['tests'][SECURITY]['os_errors'] == [{'errno': 13, 'type': 'PermissionError'}]
    assert found.sandbox_events == (SandboxEvent(kind='policy_denial', phase='test', touches_witness_path=None),)
    assert found.witness.safe_behavior == 'PermissionError'


def test_a_failed_open_leaves_the_effect_unknown(tmp_path):
    found, _ = mapped(tmp_path, '''
def test_security(tmp_path):
    (tmp_path / "x").write_text("x")
    target.read(tmp_path, "x", error="swallow")
''')
    assert found.witness.effect == 'unknown' and found.sandbox_events == ()


def test_changed_monitoring_marks_the_record_not_intact(tmp_path):
    done, record = run_probe(tmp_path, '''
import sys
def test_security(tmp_path):
    sys.monitoring.set_events(4, 0)
''')
    assert json.loads(record)['intact'] is False
    found = witness_evidence(capture(record), REQUEST, SECURITY)
    assert (found.witness, found.sandbox_events) == (None, None) and 'monitoring changed' in found.reason


def test_a_record_written_by_the_test_fails_the_run_instead_of_being_replaced(tmp_path):
    done, record = run_probe(tmp_path, '''
def test_security():
    Path("witness.json").write_text("{}")
''')
    assert done.returncode == 3 and record == b'{}'


def test_a_tool_id_already_in_use_is_never_intact(tmp_path):
    (tmp_path / 'target.py').write_text(TARGET)
    (tmp_path / 'test_case.py').write_text('def test_security():\n    pass\n')
    # Occupying the probe's id before the session leaves it unregistered, and its record is never admitted.
    argv = list(probe_argv(COMMAND, REQUEST, root=str(tmp_path), record_path='witness.json', nonce=NONCE))
    argv[0], argv[2] = sys.executable, 'import sys; sys.monitoring.use_tool_id(4, "other")\n' + BOOTSTRAP
    done = subprocess.run(argv, cwd=tmp_path, capture_output=True, timeout=60, env={'PYTHONPATH': '.'})
    record = (tmp_path / 'witness.json').read_bytes()
    assert done.returncode == 0 and json.loads(record)['tool_registered'] is False
    assert 'not registered' in witness_evidence(capture(record), REQUEST, SECURITY).reason


@pytest.fixture
def record(tmp_path):
    return run_probe(tmp_path, '''
import pytest
def test_security(tmp_path):
    with pytest.raises(ValueError):
        target.read(tmp_path, "x", error="reject")
''')[1]


@pytest.mark.parametrize('change, reason', [
    (dict(status='unavailable', detail='read: exit 1'), 'witness unavailable: read: exit 1'),
    (dict(nonce='other'), 'does not belong'),
    (dict(probe_sha256='0' * 64), 'another target or probe'),
    (dict(request=WitnessRequest('target.py', 'other')), 'does not belong'),
    (dict(artifact=ArtifactRef('0' * 64, 1)), 'differ from the stored artifact'),
    (dict(record=b'{"schema": 1}'), 'differ from the stored artifact'),
])
def test_records_from_another_run_probe_or_target_are_refused(record, change, reason):
    captured = capture(record)
    captured = replace(captured, **change)
    found = witness_evidence(captured, change.get('request', REQUEST), SECURITY)
    assert (found.witness, found.sandbox_events) == (None, None) and reason in found.reason


def test_a_malformed_record_or_unobserved_security_call_is_refused(record):
    for bad in (b'{"schema": 1}', b'not json'):
        assert 'record invalid' in witness_evidence(capture(bad), REQUEST, SECURITY).reason
    assert 'not observed to completion' in witness_evidence(capture(record), REQUEST, 'test_case.py::test_x').reason
    data = json.loads(record)
    data['tests'][SECURITY]['complete'] = False
    assert 'not observed' in witness_evidence(capture(json.dumps(data).encode()), REQUEST, SECURITY).reason
    data['tests'][SECURITY] |= {'complete': True, 'entered': 2}
    assert 'do not pair' in witness_evidence(capture(json.dumps(data).encode()), REQUEST, SECURITY).reason
    assert witness_evidence(None, REQUEST, SECURITY).witness is None


def test_inconsistent_exits_leave_safe_behavior_unset(record):
    data = json.loads(record)
    data['tests'][SECURITY] |= {'entered': 2, 'exits': ['ValueError', None]}
    assert witness_evidence(capture(json.dumps(data).encode()), REQUEST, SECURITY).witness.safe_behavior is None


def test_the_probe_argv_stays_well_inside_the_execution_adapter_bound():
    """The OpenShell execution adapter refuses argv over 16384 bytes; keep the probe far below it."""
    from corsair.adapters.pytest_runner import WRAPPER
    from evals.fixture_e2e.reviewed import PREFIX
    ids = ('test_documents.py::test_benign_control', 'test_documents.py::test_security_rejects_outside_read')
    argv = (('/bin/sh', '-c', WRAPPER, 'corsair-pytest', '/tmp/corsair-junit.xml')
            + probe_argv(PREFIX, WitnessRequest('documents.py', 'read_document'), root='/tmp/workspace',
                         record_path='/tmp/corsair-witness.json', nonce=NONCE) + ('--tb=native',) + ids)
    assert sum(len(arg.encode()) + 1 for arg in argv) < 12288
