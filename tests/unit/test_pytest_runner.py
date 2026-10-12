"""Runner orchestration over fake ports plus one real pytest run of reviewed SPEC-0018 bytes."""
from dataclasses import replace
import json
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import WRAPPER, PytestRunner, PytestRunnerConfig
from corsair.ports.execution import ExecutionError, ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PreparedWorkspace
from evals.fixture_e2e.reviewed import DISCOVER, FIXTURE, PREFIX, ReviewedLocalExecution, ReviewedWorkspace

IDS = ('tests/test_a.py::test_control', 'tests/test_a.py::test_security')
PATCH = ApprovedPatch((PatchFile('tests/test_a.py', b'def test_control(): pass\n'),), ('tests/test_a.py',))
COLLECTED = ('\n'.join(IDS) + '\n\n2 tests collected in 0.01s\n').encode()


def junit(control='', security=''):
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
            f'<testcase classname="tests.test_a" name="test_control">{control}</testcase>'
            f'<testcase classname="tests.test_a" name="test_security">{security}</testcase>'
            '</testsuite></testsuites>').encode()


FAILED = junit(security='<failure message="AssertionError: x">Traceback (most recent call last):\n'
               '  File "/work/tests/test_a.py", line 9, in test_security\n    assert False, "x"\nAssertionError: x</failure>')


class Workspace:
    def __init__(self, store, root, *, prepare_error=None, release='confirmed', digest=None):
        self.store, self.root, self.prepare_error, self.release_result, self.digest = store, root, prepare_error, release, digest
        self.calls = []

    def prepare(self, patch, operation):
        self.calls.append(('prepare', operation))
        if self.prepare_error: raise self.prepare_error
        handle = SandboxHandle(str(uuid4()), 'tests', 'default', 'owner', str(operation))
        return PreparedWorkspace(handle, self.store.put(b'source'), self.store.put(b'tests'), self.digest or patch.sha256)

    def release(self, workspace, operation):
        self.calls.append(('release', operation))
        if isinstance(self.release_result, Exception): raise self.release_result
        return self.release_result


def receipt(handle, operation, stdout=b'', native_exit=0, **changes):
    return replace(ExecutionReceipt(str(operation), handle, '2026-10-12T00:00:00Z', 0.1, 'acknowledged',
                                    'terminal_observed', 'terminal', stdout=stdout, native_exit=native_exit,
                                    worker_cleanup='confirmed'), **changes)


class Scripted:
    """Each step is (stdout, exit, receipt changes) or an exception factory taking the planned receipt."""
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def execute(self, handle, command, operation):
        self.calls.append((command, operation))
        step = self.steps.pop(0)
        if callable(step): raise step(receipt(handle, operation))
        stdout, native_exit, changes = (step + ({},))[:3]
        return replace(receipt(handle, operation, stdout, native_exit), **changes)


@pytest.fixture
def store(tmp_path):
    root = tmp_path / 'objects'; root.mkdir(mode=0o700)
    with LocalArtifacts(root, max_bytes=1024*1024) as artifacts:
        yield artifacts


def run(store, *steps, workspace=None, ids=IDS, patch=PATCH, root='/work'):
    workspace = workspace or Workspace(store, root)
    execution = Scripted(*steps)
    runner = PytestRunner(workspace, execution, store, PytestRunnerConfig(PREFIX, '.corsair-junit.xml', root))
    operation = uuid4()
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=DISCOVER,
                        operation=operation)
    return result, execution, workspace, operation


def test_discovers_then_executes_once_and_admits_claims_from_junit(store):
    result, execution, workspace, operation = run(store, (COLLECTED, 0), (FAILED, 1))
    assert (result.failure_layer, result.cleanup, result.detail) == (None, 'confirmed', '')
    assert result.discovery.status == 'discovered' and set(result.discovery.test_ids) == set(IDS)
    (discover, first), (argv, second) = execution.calls
    assert discover == DISCOVER + ('tests/test_a.py',)
    assert (first, second) == (uuid5(operation, 'discovery'), uuid5(operation, 'execution'))
    # Ids and paths are positional arguments to a fixed script; nothing agent-derived is in the script text.
    assert argv[:5] == ('sh', '-c', WRAPPER, 'corsair-pytest', '.corsair-junit.xml')
    assert argv[5:] == PREFIX + ('--tb=native',) + IDS and not any(i in WRAPPER for i in IDS)
    run_ = result.execution
    assert run_.status == 'completed' and store.get(run_.junit) == FAILED
    assert [c.outcome for c in run_.cases] == ['passed', 'failed']
    failure = run_.cases[1].failure
    assert (failure.type, failure.path, failure.function, failure.line) == ('AssertionError', 'tests/test_a.py', 'test_security', 9)
    claims = run_.claims
    assert (claims.report, claims.native_exit, claims.operation) == (run_.junit, 1, str(second))
    assert (claims.claims.control.outcome, claims.claims.security.outcome) == ('passed', 'failed')
    assert claims.claims.source_sha256 == result.workspace.source.sha256 and claims.handle == result.workspace.handle
    assert workspace.calls == [('prepare', operation), ('release', operation)]


@pytest.mark.parametrize('stdout,native_exit', [
    (('\n'.join(IDS) + '\ntests/test_a.py::test_extra\n\n').encode(), 0), ((IDS[0] + '\n\n').encode(), 0),
    (b'ERROR tests/test_a.py - ImportError\n\n', 2), (b'no tests ran\n', 5), (COLLECTED, 4),
    ((IDS[0] + '\n' + IDS[1] + '[x]\n\n').encode(), 0), ((IDS[0] + '\n' + IDS[0] + '\n' + IDS[1] + '\n').encode(), 0),
])
def test_inexact_discovery_never_executes(store, stdout, native_exit):
    result, execution, workspace, _ = run(store, (stdout, native_exit, {'stderr': b'collect detail'}))
    assert result.discovery.status == 'collection_error' and result.execution is None
    assert result.failure_layer == 'discovery' and 'collect detail' in result.discovery.errors
    assert len(execution.calls) == 1 and result.cleanup == 'confirmed'


@pytest.mark.parametrize('changes', [dict(delivery='unknown'), dict(completion='unknown'),
    dict(reason='host_timeout', failure_layer='host_supervision'), dict(worker_cleanup='unconfirmed'),
    dict(native_exit=None), dict(operation=str(uuid4()))])
def test_incomplete_discovery_receipt_is_execution_failure(store, changes):
    result, execution, _, _ = run(store, (COLLECTED, 0, changes))
    assert result.discovery.status == 'execution_failure' and result.failure_layer == 'discovery'
    assert result.discovery.receipt is not None and len(execution.calls) == 1


def test_execution_error_keeps_receipt_and_is_not_retried(store):
    failed = lambda planned: ExecutionError(replace(planned, delivery='unknown', reason='worker_loss'))
    result, execution, _, _ = run(store, (COLLECTED, 0), failed)
    assert result.execution.status == 'execution_failure' and result.failure_layer == 'execution'
    assert result.execution.receipt.delivery == 'unknown' and result.execution.junit is None
    assert len(execution.calls) == 2 and 'worker_loss' in result.detail


def test_incomplete_execution_receipt_stores_nothing(store):
    result, _, _, _ = run(store, (COLLECTED, 0), (FAILED, 1, dict(completion='unknown')))
    assert (result.execution.status, result.execution.junit, result.failure_layer) == ('execution_failure', None, 'execution')


@pytest.mark.parametrize('stdout,native_exit,status,layer', [
    (FAILED, 0, 'invalid_report', 'report'), (junit(), 1, 'invalid_report', 'report'),
    (junit(security='<skipped message="s"/>'), 1, 'invalid_report', 'report'),
    (b'<!DOCTYPE x>' + junit(), 0, 'invalid_report', 'report'), (b'', 1, 'invalid_report', 'report'),
    (FAILED.replace(b'test_security"', b'test_other"'), 1, 'invalid_report', 'report'),
    (FAILED, 2, 'execution_failure', 'execution'), (b'', 4, 'execution_failure', 'execution'),
])
def test_inconsistent_or_invalid_junit_is_retained_not_admitted(store, stdout, native_exit, status, layer):
    result, _, _, _ = run(store, (COLLECTED, 0), (stdout, native_exit))
    assert (result.execution.status, result.failure_layer, result.execution.claims) == (status, layer, None)
    assert store.get(result.execution.junit) == stdout


def test_skips_are_completed_claims_for_the_gates_to_reject(store):
    result, _, _, _ = run(store, (COLLECTED, 0), (junit(security='<skipped message="s">t</skipped>'), 0))
    assert result.execution.status == 'completed' and result.execution.claims.claims.security.outcome == 'skipped'


@pytest.mark.parametrize('release,expected', [(RuntimeError('gone'), 'unconfirmed'), ('unconfirmed', 'unconfirmed')])
def test_release_failure_is_unconfirmed_and_keeps_outcome(store, release, expected):
    result, _, _, _ = run(store, (COLLECTED, 0), (FAILED, 1), workspace=Workspace(store, '/work', release=release))
    assert (result.cleanup, result.execution.status, result.failure_layer) == (expected, 'completed', None)


def test_prepare_failure_and_foreign_workspace(store):
    result, execution, _, _ = run(store, workspace=Workspace(store, '/work', prepare_error=OSError('quota')))
    assert (result.failure_layer, result.cleanup, result.workspace) == ('workspace', 'unconfirmed', None)
    assert execution.calls == [] and 'quota' in result.detail
    result, execution, workspace, _ = run(store, workspace=Workspace(store, '/work', digest='0'*64))
    assert (result.failure_layer, result.cleanup, execution.calls) == ('workspace', 'confirmed', [])
    assert [c[0] for c in workspace.calls] == ['prepare', 'release']


@pytest.mark.parametrize('ids', [('other/test_b.py::test_control', IDS[1]), (IDS[0], IDS[0]),
    (IDS[0], 'tests/test_a.py::test_security[1]'), (IDS[0], 'tests/test_a.py::' + 'x'*130)])
def test_ids_must_be_distinct_plain_and_inside_the_patch(store, ids):
    workspace = Workspace(store, '/work')
    with pytest.raises(ValueError): run(store, workspace=workspace, ids=ids)
    assert workspace.calls == []


def test_option_like_patch_path_is_refused(store):
    patch = ApprovedPatch((PatchFile('-p.py', b''),), ('-p.py',))
    with pytest.raises(ValueError): run(store, patch=patch, ids=('-p.py::test_a', '-p.py::test_b'))


@pytest.mark.parametrize('variant', ['vulnerable', 'fixed'])
def test_reviewed_spec0018_fixture_through_real_pytest(store, tmp_path, variant):
    root = (tmp_path / 'workspace').resolve()
    reviewed = (FIXTURE / 'test_documents.py').read_bytes()
    patch = ApprovedPatch((PatchFile('test_documents.py', reviewed),), ('test_documents.py',))
    ids = ('test_documents.py::test_benign_control', 'test_documents.py::test_security_rejects_outside_read')
    runner = PytestRunner(ReviewedWorkspace(store, root, variant), ReviewedLocalExecution(root), store,
                          PytestRunnerConfig(PREFIX, '.corsair-junit.xml', str(root)))
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=DISCOVER,
                        operation=uuid4())
    assert result.discovery.status == 'discovered', result.discovery.errors
    assert (result.failure_layer, result.cleanup, result.execution.status) == (None, 'confirmed', 'completed'), result.detail
    control, security = result.execution.cases
    witnesses = [json.loads(line) for case in (control, security)
                 for line in case.captured_output.splitlines() if line.startswith('{')]
    assert [w['test'] for w in witnesses] == ['control', 'security'] and control.outcome == 'passed'
    if variant == 'vulnerable':
        line = next(n for n, text in enumerate(reviewed.decode().splitlines(), 1)
                    if 'security assertion: application opened the outside fixture' in text)
        failure = security.failure
        assert security.outcome == 'failed' and result.execution.receipt.native_exit == 1
        assert (failure.kind, failure.type, failure.path, failure.function, failure.line) == (
            'failure', 'AssertionError', 'test_documents.py', 'test_security_rejects_outside_read', line)
        assert witnesses[1]['exception'] is None and any(o.endswith('/outside.txt') for o in witnesses[1]['opens'])
    else:
        assert security.outcome == 'passed' and result.execution.receipt.native_exit == 0
        assert witnesses[1]['exception'] == 'ValueError' and witnesses[1]['opens'] == []
    assert result.execution.claims.claims.security.outcome == ('failed' if variant == 'vulnerable' else 'passed')
    assert store.get(result.execution.junit) == result.execution.receipt.stdout
