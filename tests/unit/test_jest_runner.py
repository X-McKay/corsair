"""Jest runner orchestration over fake ports, replaying real Jest 24.8.0 reports from Node 8.17.0 as the wrapper's stdout."""
from pathlib import Path
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.jest_runner import LIST_NOTHING, WRAPPER, JestRunner, JestRunnerConfig, selection
from corsair.ports.execution import ExecutionError
from corsair.ports.test_runner import ApprovedPatch, JsTestId, PatchFile, WitnessRequest
from tests.unit.test_pytest_runner import Scripted, Workspace, store  # noqa: F401  (fixture)

REPORTS = Path(__file__).with_name('jest_reports')
ROOT = '/sandbox/src'
JEST = ('/usr/local/bin/node', 'node_modules/jest/bin/jest.js', '--ci')
REPORT = '/tmp/corsair-jest.json'
TEST_PATH = 'test/corsair.test.js'
IDS = (TEST_PATH + '::corsair_control', TEST_PATH + '::traversal::corsair_security')
PATCH = ApprovedPatch((PatchFile(TEST_PATH, (REPORTS / 'baseline.test.js').read_bytes()),), (TEST_PATH,))
LISTED = (REPORTS / 'node8-jest24.8.0-baseline-listing.json').read_bytes()
BASELINE = (REPORTS / 'node8-jest24.8.0-baseline-run.json').read_bytes()
CANDIDATE = (REPORTS / 'node8-jest24.8.0-candidate-run.json').read_bytes()


def run(store, *steps, ids=IDS, patch=PATCH, witness=None):
    workspace, execution = Workspace(store, ROOT), Scripted(*steps)
    runner = JestRunner(workspace, execution, store, JestRunnerConfig(JEST, ROOT, REPORT))
    operation = uuid4()
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=JEST,
                        operation=operation, witness=witness)
    return result, execution, workspace, operation


def test_listed_discovery_then_one_execution_admits_claims_from_jest(store):
    result, execution, workspace, operation = run(store, (LISTED, 0), (BASELINE, 1))
    file = ('--runTestsByPath', TEST_PATH)
    assert [call[0] for call in execution.calls] == [
        ('/bin/sh', '-c', WRAPPER, 'corsair-jest', REPORT, *JEST, *file, '--testNamePattern', LIST_NOTHING),
        ('/bin/sh', '-c', WRAPPER, 'corsair-jest', REPORT, *JEST, *file,
         '--testNamePattern', '^(?:corsair_control|traversal corsair_security)$')]
    assert [call[1] for call in execution.calls] == [uuid5(operation, 'discovery'), uuid5(operation, 'execution')]
    assert result.failure_layer is None and result.cleanup == 'confirmed' and result.discovery.test_ids == IDS
    assert [case.outcome for case in result.execution.cases] == ['passed', 'failed']
    claims = result.execution.claims
    assert store.get(claims.report) == BASELINE and claims.native_exit == 1
    assert (claims.claims.control.test_id, claims.claims.security.outcome) == (IDS[0], 'failed')
    failure = result.execution.cases[1].failure
    assert (failure.type, failure.path, failure.function, failure.line) == ('Error', TEST_PATH, 'corsair_security', 11)
    assert workspace.calls[-1][0] == 'release'


def test_candidate_passes_with_exit_zero(store):
    result, *_ = run(store, (LISTED, 0), (CANDIDATE, 0))
    assert result.execution.status == 'completed' and result.execution.claims.claims.security.outcome == 'passed'


@pytest.mark.parametrize('stdout, native_exit, detail', [
    ((REPORTS / 'node8-jest24.8.0-syntax-listing.json').read_bytes(), 1, 'exit 1'),  # suite failed to load
    (LISTED, 1, 'exit 1'),
    (LISTED.replace(b'"traversal"', b'"other"'), 0, "found ['test/corsair.test.js::corsair_control', 'test/corsair.test.js::other::corsair_security']"),
    (LISTED.replace(b'"status":"pending","title":"corsair_control"', b'"status":"passed","title":"corsair_control"'), 0, 'found []'),
    ((REPORTS / 'node8-jest24.8.0-nontest-listing.json').read_bytes(), 1, 'found []'),  # not a test file for the config
    (b'', 0, 'found []'),
])
def test_inexact_or_failed_discovery_never_executes(store, stdout, native_exit, detail):
    result, execution, workspace, _ = run(store, (stdout, native_exit))
    assert result.discovery.status == 'collection_error' and result.execution is None
    assert result.failure_layer == 'discovery' and detail in result.detail and len(execution.calls) == 1
    assert result.cleanup == 'confirmed'


def test_execution_error_is_not_retried(store):
    result, execution, *_ = run(store, (LISTED, 0), lambda planned: ExecutionError(planned))
    assert result.failure_layer == 'execution' and result.execution.status == 'execution_failure'
    assert len(execution.calls) == 2 and result.cleanup == 'confirmed'


@pytest.mark.parametrize('stdout, native_exit, status, layer', [
    (b'', 1, 'execution_failure', 'execution'),        # Jest stopped before writing its report
    (BASELINE, 0, 'invalid_report', 'report'),         # failure reported but Jest succeeded
    (CANDIDATE, 1, 'invalid_report', 'report'),        # Jest failed with every test passing
    (BASELINE, 137, 'execution_failure', 'execution'),
    (LISTED, 0, 'completed', None),                    # skips are claims for the gates to reject
    (BASELINE.replace(b'"title":"corsair_control"', b'"title":"other"'), 1, 'invalid_report', 'report'),
    ((REPORTS / 'node8-jest24.8.0-syntax-listing.json').read_bytes(), 1, 'invalid_report', 'report'),
])
def test_inconsistent_or_missing_reports_are_retained_not_admitted(store, stdout, native_exit, status, layer):
    result, *_ = run(store, (LISTED, 0), (stdout, native_exit))
    assert (result.execution.status, result.failure_layer) == (status, layer)
    if stdout and status != 'completed':
        assert result.execution.claims is None and store.get(result.execution.junit) == stdout


def test_witness_requests_are_unavailable_without_running_anything(store):
    request = WitnessRequest('lib/docs.js', 'resolve', 'x.txt')
    result, execution, *_ = run(store, (LISTED, 0), (BASELINE, 1), witness=request)
    assert result.witness.status == 'unavailable' and 'Node.js' in result.witness.detail
    assert len(execution.calls) == 2


@pytest.mark.parametrize('ids', [
    (IDS[0], IDS[0]),
    (IDS[0], 'test/other.test.js::corsair_security'),                 # outside the patch
    (IDS[0], 'tests/test_a.py::test_security'),                       # not a Jest id
    (IDS[0], TEST_PATH + '::corsair security'),                       # titles are identifiers
    (IDS[0], TEST_PATH + '::a::b::c'),                                # one describe level at most
])
def test_ids_must_be_distinct_jest_tests_of_the_patch_file(store, ids):
    with pytest.raises(ValueError):
        run(store, ids=ids)


def test_two_files_are_refused_before_any_workspace(store):
    other = 'test/other.test.js'
    patch = ApprovedPatch((PATCH.files[0], PatchFile(other, b"test('x', () => {});\n")), (TEST_PATH, other))
    with pytest.raises(ValueError, match='one file'):
        run(store, ids=(IDS[0], other + '::corsair_security'), patch=patch)


@pytest.mark.parametrize('command', [JEST + ('-t', 'x'), JEST + ('--testNamePattern=x',), JEST + ('test/x.test.js',),
                                     JEST + ('--json',), JEST + ('--outputFile=/tmp/x',), JEST + ('--watch',), JEST[:1], ('node',) + JEST[1:]])
def test_operator_prefix_cannot_select_or_report(command):
    with pytest.raises(ValueError):
        JestRunnerConfig(command, ROOT, REPORT)


@pytest.mark.parametrize('root, report', [('relative', REPORT), (ROOT, 'relative.json'), (ROOT, ROOT + '/report.json')])
def test_operator_paths_are_bounded(root, report):
    with pytest.raises(ValueError):
        JestRunnerConfig(JEST, root, report)


@pytest.mark.parametrize('command', [JEST + ('--runTestsByPath', 'test/x.test.js'), JEST[:2], ()])
def test_discovery_command_must_be_the_operator_prefix(store, command):
    runner = JestRunner(Workspace(store, ROOT), Scripted(), store, JestRunnerConfig(JEST, ROOT, REPORT))
    with pytest.raises(ValueError, match='prefix'):
        runner.run(PATCH, control_test_id=IDS[0], security_test_id=IDS[1], discovery_command=command, operation=uuid4())


def test_selection_anchors_full_names():
    assert selection((TEST_PATH + '::a', TEST_PATH + '::s::b')) == (
        '--runTestsByPath', TEST_PATH, '--testNamePattern', '^(?:a|s b)$')
    assert str(JsTestId.parse(IDS[1])) == IDS[1] and JsTestId.parse(IDS[1]).full_name == 'traversal corsair_security'


def test_jest_runs_become_gate_evidence(store):
    from corsair.composition.evidence import run_evidence
    from corsair.core.disposition import EnvironmentIdentity
    identity = EnvironmentIdentity(image_digest='1' * 64, recipe_sha256='2' * 64, dependency_inventory_sha256='3' * 64,
                                   policy_revision='policy-1', limits_sha256='4' * 64)
    result, *_ = run(store, (LISTED, 0), (BASELINE, 1))
    evidence = run_evidence(result, environment=identity)
    assert evidence.discovered_test_ids == IDS and evidence.witness is None
    control, security = evidence.outcomes
    assert (control.test_id, control.outcome, security.outcome) == (IDS[0], 'passed', 'failed')
    assert (security.failure.exception_type, security.failure.path, security.failure.function, security.failure.line) == (
        'Error', TEST_PATH, 'corsair_security', 11)
