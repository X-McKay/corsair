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

REQUEST = WitnessRequest('target.py', 'read', 'outside.txt')
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


def run_probe(tmp_path, test_body, command=COMMAND, target=TARGET, request=REQUEST):
    (tmp_path / 'target.py').write_text(target)
    (tmp_path / 'test_case.py').write_text('import os\nfrom pathlib import Path\nimport target\n\n' + test_body)
    argv = probe_argv(command, request, root=str(tmp_path), record_path='witness.json', nonce=NONCE)
    argv = (sys.executable,) + argv[1:]
    done = subprocess.run(argv, cwd=tmp_path, capture_output=True, timeout=60, env={'PYTHONPATH': '.'})
    record = (tmp_path / 'witness.json').read_bytes() if (tmp_path / 'witness.json').exists() else b''
    return done, record


def capture(record, request=REQUEST, **changes):
    values = dict(status='captured', request=request, nonce=NONCE, probe_sha256=PROBE_SHA256, record=record,
                  artifact=ArtifactRef(sha256(record).hexdigest(), len(record)), detail='', receipt=None)
    return WitnessCapture(**(values | changes))


def mapped(tmp_path, body):
    done, record = run_probe(tmp_path, body)
    assert record, done.stdout.decode() + done.stderr.decode()
    return witness_evidence(capture(record), REQUEST, SECURITY), json.loads(record)


def test_argv_replaces_exactly_one_module_invocation():
    argv = probe_argv(COMMAND, REQUEST, root='/w', record_path='/tmp/r.json', nonce=NONCE)
    assert argv[:4] == ('python3.12', '-c', BOOTSTRAP, PROBE_SOURCE) and argv[5:] == COMMAND[3:]
    assert json.loads(argv[4]) == {'effect_name': 'outside.txt', 'nonce': NONCE, 'record_path': '/tmp/r.json',
                                   'root': '/w', 'target_path': 'target.py', 'target_symbol': 'read', 'tool_id': 4}
    for command in (('python3.12', 'pytest'), COMMAND + ('-m', 'pytest')):
        with pytest.raises(ValueError, match='exactly one'):
            probe_argv(command, REQUEST, root='/w', record_path='r', nonce=NONCE)


@pytest.mark.parametrize('symbol', ['', 'a b', '1x', 'x.', 'a;b'])
def test_request_needs_a_plain_symbol_and_confined_path(symbol):
    with pytest.raises(ValueError):
        WitnessRequest('target.py', symbol, 'outside.txt')
    with pytest.raises(ValueError):
        WitnessRequest('../target.py', 'read', 'outside.txt')
    for name in ('', '..', 'a/b', 'x y'):
        with pytest.raises(ValueError):
            WitnessRequest('target.py', 'read', name)


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
    assert security['opens'][0]['path'].endswith('sub/../outside.txt') and security['opens'][0]['planned']
    assert record['intact']
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


def test_a_failed_planned_open_leaves_the_effect_unknown(tmp_path):
    request = WitnessRequest('target.py', 'read', 'missing.txt')
    done, record = run_probe(tmp_path, '''
def test_security(tmp_path):
    (tmp_path / "x").write_text("x")
    target.read(tmp_path, "x", error="swallow")
''', request=request)
    found = witness_evidence(capture(record, request), request, SECURITY)
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
    (dict(request=WitnessRequest('target.py', 'other', 'outside.txt')), 'does not belong'),
    (dict(request=WitnessRequest('target.py', 'read', 'other.txt')), 'does not belong'),
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
            + probe_argv(PREFIX, WitnessRequest('documents.py', 'read_document', 'outside.txt'), root='/tmp/workspace',
                         record_path='/tmp/corsair-witness.json', nonce=NONCE) + ('--tb=native',) + ids)
    assert sum(len(arg.encode()) + 1 for arg in argv) < 12288


def test_an_identical_function_elsewhere_is_never_the_target(tmp_path):
    """Equal code objects from another file compare equal; attribution must not follow equality."""
    (tmp_path / 'lookalike.py').write_text(TARGET)
    found, record = mapped(tmp_path, '''
import pytest
import lookalike
def test_security(tmp_path):
    (tmp_path / "x").write_text("x")
    with pytest.raises(ValueError):
        target.read(tmp_path, "x", error="reject")
    assert lookalike.read(tmp_path, "x") == "x"
''')
    security = record['tests'][SECURITY]
    assert (security['entered'], security['exits'], security['opens']) == (1, ['ValueError'], [])
    assert (found.witness.effect, found.witness.safe_behavior) == ('absent', 'ValueError')


def test_module_loading_inside_the_target_is_not_the_effect(tmp_path):
    target = TARGET + '''
def lazy(name):
    import lazy_dependency
    raise ValueError(name)
'''
    (tmp_path / 'lazy_dependency.py').write_text('VALUE = 1\n')
    request = WitnessRequest('target.py', 'lazy', 'outside.txt')
    done, record = run_probe(tmp_path, '''
import pytest
def test_security():
    with pytest.raises(ValueError):
        target.lazy("x")
''', target=target, request=request)
    found = witness_evidence(capture(record, request), request, SECURITY)
    assert json.loads(record)['tests'][SECURITY]['opens'] == []
    assert (found.witness.effect, found.witness.safe_behavior) == ('absent', 'ValueError')


def test_one_denial_propagating_through_frames_is_one_event(tmp_path):
    target = TARGET + '''
def inner(path):
    raise PermissionError(errno.EACCES, 'denied', str(path))

def outer(path):
    return inner(path)
'''
    request = WitnessRequest('target.py', 'outer', 'outside.txt')
    done, record = run_probe(tmp_path, '''
import pytest
def test_security(tmp_path):
    with pytest.raises(PermissionError):
        target.outer(tmp_path / "secret")
''', target=target, request=request)
    found = witness_evidence(capture(record, request), request, SECURITY)
    assert len(json.loads(record)['tests'][SECURITY]['os_errors']) == 1 and len(found.sandbox_events) == 1


def test_a_local_class_named_like_a_builtin_is_not_the_builtin(tmp_path):
    target = TARGET + '''
class ValueError(Exception):
    pass

def shadow(name):
    raise ValueError(name)
'''
    request = WitnessRequest('target.py', 'shadow', 'outside.txt')
    done, record = run_probe(tmp_path, '''
import pytest
def test_security():
    with pytest.raises(Exception):
        target.shadow("x")
''', target=target, request=request)
    found = witness_evidence(capture(record, request), request, SECURITY)
    assert found.witness.safe_behavior == 'target.ValueError'


def test_reading_another_file_is_not_the_planned_effect(tmp_path):
    """Review counterexample: a target that only reads its config must not support a reproduction."""
    found, record = mapped(tmp_path, '''
def test_security(tmp_path):
    (tmp_path / "config.txt").write_text("c")
    target.read(tmp_path, "config.txt")
    assert False, "faulty security assertion"
''')
    assert [o['planned'] for o in record['tests'][SECURITY]['opens']] == [False]
    assert (found.witness.path_reached, found.witness.effect) == (True, 'absent')


def test_a_planned_read_in_a_module_body_imported_by_the_target_counts(tmp_path):
    """Review counterexample: only the loader's own reads are excluded, not code a module runs on import."""
    target = TARGET + '''
def imports(root):
    import helper
    raise ValueError(helper.VALUE)
'''
    (tmp_path / 'helper.py').write_text('from pathlib import Path\nVALUE = Path("outside.txt").read_text()\n')
    (tmp_path / 'outside.txt').write_text('secret')
    request = WitnessRequest('target.py', 'imports', 'outside.txt')
    done, record = run_probe(tmp_path, '''
import pytest
def test_security(tmp_path):
    with pytest.raises(ValueError, match="secret"):
        target.imports(tmp_path)
''', target=target, request=request)
    found = witness_evidence(capture(record, request), request, SECURITY)
    assert [o['planned'] for o in json.loads(record)['tests'][SECURITY]['opens']] == [True]
    assert (found.witness.effect, found.witness.safe_behavior) == ('observed', 'ValueError')


def test_absence_is_the_planned_safe_behavior_however_the_target_exits(record):
    """SPEC-0040 `no_file_open`: a fix that returns normally, or rejects, without the planned open is safe."""
    data = json.loads(record)
    for exits in (['ValueError'], [None]):
        data['tests'][SECURITY] |= {'entered': 1, 'exits': exits}
        found = witness_evidence(capture(json.dumps(data).encode()), REQUEST, SECURITY, planned_safe_behavior='no_file_open')
        assert (found.witness.effect, found.witness.safe_behavior) == ('absent', 'no_file_open')
    unpaired = data | {'tests': {SECURITY: data['tests'][SECURITY] | {'entered': 1, 'exits': [], 'truncated': True}}}
    found = witness_evidence(capture(json.dumps(unpaired).encode()), REQUEST, SECURITY, planned_safe_behavior='no_file_open')
    assert found.witness is None or found.witness.safe_behavior is None


THREADED = '''import os, threading

def read(root, name):
    worker = threading.Thread(target=lambda: open(os.path.join(root, name)).read())
    worker.start()
    worker.join()
'''


def test_an_open_moved_to_another_thread_is_never_an_absence(tmp_path):
    """The planned file opened off the target's stack (a worker thread) makes the effect unknown, not absent."""
    done, record = run_probe(tmp_path, '''
def test_security(tmp_path):
    (tmp_path / "outside.txt").write_text("sentinel")
    assert (tmp_path / "outside.txt").read_text() == "sentinel"
    target.read(tmp_path, "outside.txt")
''', target=THREADED)
    assert record, done.stdout.decode() + done.stderr.decode()
    assert json.loads(record)['tests'][SECURITY]['offstack_planned'] >= 1
    found = witness_evidence(capture(record), REQUEST, SECURITY, planned_safe_behavior='no_file_open')
    assert (found.witness.path_reached, found.witness.effect, found.witness.safe_behavior) == (True, 'unknown', None)


def test_the_test_bodys_own_reads_of_the_sentinel_are_not_counted_off_stack(tmp_path):
    found, data = mapped(tmp_path, '''
import pytest
def test_security(tmp_path):
    (tmp_path / "outside.txt").write_text("sentinel")
    assert (tmp_path / "outside.txt").read_text() == "sentinel"
    with pytest.raises(ValueError):
        target.read(tmp_path, "../outside.txt", error="reject")
''')
    assert data['tests'][SECURITY]['offstack_planned'] == 0
    assert (found.witness.effect, found.witness.safe_behavior) == ('absent', 'ValueError')
def test_the_test_bodys_own_read_after_the_call_is_its_own_not_off_stack(tmp_path):
    """Live run 2: the security test re-read the outside file after the call; that read is the test's, not the target's."""
    found, data = mapped(tmp_path, '''
def test_security(tmp_path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "outside.txt").write_text("outside")
    target.read(tmp_path / "allowed", "../outside.txt")
    assert (tmp_path / "outside.txt").read_text() == "outside"
    with open(tmp_path / "outside.txt") as stream:
        assert stream.read() == "outside"
''')
    test = data['tests'][SECURITY]
    assert (test['offstack_planned'], test['body_planned']) == (0, 2)
    assert [o['planned'] for o in test['opens']] == [True]
    assert (found.witness.path_reached, found.witness.effect) == (True, 'observed')


def test_a_read_through_a_helper_or_the_event_loop_stays_off_stack(tmp_path):
    """Only the test function itself, through standard file-I/O frames, is the test body; anything between stays off-stack."""
    done, record = run_probe(tmp_path, '''
import asyncio, functools
def check(path):
    return path.read_text()

def test_security(tmp_path):
    (tmp_path / "outside.txt").write_text("outside")
    try:
        target.read(tmp_path, "x", error="reject")
    except ValueError:
        pass
    check(tmp_path / "outside.txt")
    async def later():
        asyncio.get_running_loop().call_soon(functools.partial((tmp_path / "outside.txt").read_text))
        await asyncio.sleep(0)
    asyncio.run(later())
''')
    assert record, done.stdout.decode() + done.stderr.decode()
    test = json.loads(record)['tests'][SECURITY]
    assert (test['offstack_planned'], test['body_planned']) == (2, 0)
    found = witness_evidence(capture(record), REQUEST, SECURITY, planned_safe_behavior='no_file_open')
    assert found.witness.effect == 'unknown'


def test_a_runtime_without_monitoring_runs_the_tests_and_records_itself_unsupported(tmp_path):
    # CPython before 3.12 has no sys.monitoring: the run must proceed and the record must be refused by name.
    (tmp_path / 'target.py').write_text(TARGET)
    (tmp_path / 'test_case.py').write_text('import target\n\ndef test_security(tmp_path):\n    assert False\n')
    argv = list(probe_argv(COMMAND, REQUEST, root=str(tmp_path), record_path='witness.json', nonce=NONCE))
    argv[0], argv[2] = sys.executable, 'import sys; del sys.monitoring\n' + BOOTSTRAP
    done = subprocess.run(argv, cwd=tmp_path, capture_output=True, timeout=60, env={'PYTHONPATH': '.'})
    record = json.loads((tmp_path / 'witness.json').read_bytes())
    assert done.returncode == 1 and b'1 failed' in done.stdout
    assert (record['tool_registered'], record['intact']) == (False, False)
    assert record['unsupported'].endswith('has no sys.monitoring (3.12+)')
    assert record['tests'][SECURITY]['complete'] is True
    found = witness_evidence(capture((tmp_path / 'witness.json').read_bytes()), REQUEST, SECURITY)
    assert (found.witness, found.sandbox_events) == (None, None) and 'unsupported on this runtime' in found.reason


DEFERRED = '''import asyncio, os

async def read(root, name):
    asyncio.get_running_loop().call_soon(lambda: open(os.path.join(root, name)).read())
    await asyncio.sleep(0)
'''


def test_a_same_thread_open_deferred_by_the_target_is_never_an_absence(tmp_path):
    """Codex on #44: an event-loop callback the target schedules runs on the test thread off the target's stack."""
    done, record = run_probe(tmp_path, '''
import asyncio
def test_security(tmp_path):
    (tmp_path / "outside.txt").write_text("sentinel")
    assert (tmp_path / "outside.txt").read_text() == "sentinel"
    asyncio.run(target.read(tmp_path, "outside.txt"))
''', target=DEFERRED)
    assert record, done.stdout.decode() + done.stderr.decode()
    assert json.loads(record)['tests'][SECURITY]['offstack_planned'] >= 1
    found = witness_evidence(capture(record), REQUEST, SECURITY, planned_safe_behavior='no_file_open')
    assert found.witness.effect == 'unknown' and found.witness.safe_behavior != 'no_file_open'
