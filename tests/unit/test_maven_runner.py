"""Maven runner orchestration over fake ports, replaying real Surefire reports as the wrapper's stdout."""
from pathlib import Path
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.maven_runner import DISCOVER, WRAPPER, MavenRunner, MavenRunnerConfig, selection
from corsair.ports.execution import ExecutionError
from corsair.ports.test_runner import ApprovedPatch, PatchFile, WitnessRequest
from tests.unit.test_pytest_runner import Scripted, Workspace, store  # noqa: F401  (fixture)

REPORTS = Path(__file__).with_name('surefire')
ROOT = '/sandbox/src'
MVN = ('/usr/share/maven/bin/mvn', '-B', '-ntp', '-o', '-Dmaven.repo.local=/opt/corsair-m2', '-f', ROOT + '/pom.xml', 'test')
WIKI = 'jspwiki-main/org.apache.wiki.BenchmarkWikiServletForwardingTest#'
IDS = (WIKI + 'benignPageKeepsEncodedPageParameter', WIKI + 'inertWebRootResourceCannotSelectForwardTarget')
TEST_PATH = 'jspwiki-main/src/test/java/org/apache/wiki/BenchmarkWikiServletForwardingTest.java'
PATCH = ApprovedPatch((PatchFile(TEST_PATH, b'class BenchmarkWikiServletForwardingTest {}\n'),), (TEST_PATH,))
REPORT = f'{ROOT}/jspwiki-main/target/surefire-reports/TEST-org.apache.wiki.BenchmarkWikiServletForwardingTest.xml'
LISTED = (REPORTS / 'listing-jspwiki.txt').read_bytes()
JAVA, CONSOLE = '/opt/java/openjdk/bin/java', '/opt/corsair/junit-platform-console-standalone.jar'
PREFIX = MVN[:-1]
SKIPPED = ('<testsuite name="org.apache.wiki.BenchmarkWikiServletForwardingTest">' + ''.join(
    f'<testcase name="{m}" classname="org.apache.wiki.BenchmarkWikiServletForwardingTest"><skipped/></testcase>'
    for m in ('benignPageKeepsEncodedPageParameter', 'inertWebRootResourceCannotSelectForwardTarget')) + '</testsuite>').encode()
BASELINE = (REPORTS / 'jspwiki-baseline-surefire3.xml').read_bytes()
CANDIDATE = (REPORTS / 'jspwiki-candidate-surefire3.xml').read_bytes()


def run(store, *steps, ids=IDS, patch=PATCH, witness=None, **config):
    workspace, execution = Workspace(store, ROOT), Scripted(*steps)
    runner = MavenRunner(workspace, execution, store, MavenRunnerConfig(MVN, ROOT, JAVA, CONSOLE, **config))
    operation = uuid4()
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=PREFIX,
                        operation=operation, witness=witness)
    return result, execution, workspace, operation


def test_listed_discovery_then_one_execution_admits_claims_from_surefire(store):
    result, execution, workspace, operation = run(store, (LISTED, 0), (BASELINE, 1))
    selected = ('-pl', 'jspwiki-main', '-am', '-Dsurefire.failIfNoSpecifiedTests=false',
                '-Dtest=org.apache.wiki.BenchmarkWikiServletForwardingTest#benignPageKeepsEncodedPageParameter'
                '+inertWebRootResourceCannotSelectForwardTarget')
    assert [call[0] for call in execution.calls] == [
        ('/bin/sh', '-c', DISCOVER, 'corsair-maven-discover', f'{ROOT}/jspwiki-main/target/corsair-test.classpath',
         f'{ROOT}/jspwiki-main/target/test-classes:{ROOT}/jspwiki-main/target/classes', JAVA, CONSOLE,
         *(i.removeprefix('jspwiki-main/') for i in IDS), *PREFIX, *selected[:-1], 'test-compile',
         'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath',
         '-Dmdep.outputFile=target/corsair-test.classpath', '-Dmdep.includeScope=test'),
        ('/bin/sh', '-c', WRAPPER, 'corsair-maven', REPORT, *MVN, *selected)]
    assert [call[1] for call in execution.calls] == [uuid5(operation, 'discovery'), uuid5(operation, 'execution')]
    assert result.failure_layer is None and result.cleanup == 'confirmed' and result.discovery.test_ids == IDS
    assert [case.outcome for case in result.execution.cases] == ['passed', 'failed']
    claims = result.execution.claims
    assert store.get(claims.report) == BASELINE and claims.native_exit == 1
    assert (claims.claims.control.test_id, claims.claims.security.outcome) == (IDS[0], 'failed')
    assert result.execution.cases[1].failure.line == 63 and workspace.calls[-1][0] == 'release'


def test_candidate_passes_with_exit_zero(store):
    result, *_ = run(store, (LISTED, 0), (CANDIDATE, 0))
    assert result.execution.status == 'completed' and result.execution.claims.claims.security.outcome == 'passed'


def test_root_module_selects_without_reactor_arguments():
    assert selection(('corsair.sample.DocumentsTest#a', 'corsair.sample.DocumentsTest#b')) == (
        '-Dtest=corsair.sample.DocumentsTest#a+b',)


@pytest.mark.parametrize('stdout, native_exit, detail', [
    (LISTED, 1, 'exit 1'),                                                  # compile or classpath failure
    ((REPORTS / 'listing-junit4.txt').read_bytes(), 0, "found ['jspwiki-main/corsair.sample.LegacyTest#security'"),
    (LISTED.replace(b'[         2 tests found      ]', b'[         3 tests found      ]'), 0, 'found []'),
    (LISTED.replace(b'[method:benignPageKeepsEncodedPageParameter()]', b'[method:benignPageKeepsEncodedPageParameter(int)]'), 0, 'found []'),
    (LISTED.replace(b'inertWebRootResourceCannotSelectForwardTarget() ([engine', b'x ([engine').replace(
        b'[method:inertWebRootResourceCannotSelectForwardTarget()]', b'[method:benignPageKeepsEncodedPageParameter()]'), 0, 'found'),
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
    (b'', 1, 'execution_failure', 'execution'),        # build failed before Surefire reported
    (BASELINE, 0, 'invalid_report', 'report'),         # failure reported but Maven succeeded
    (CANDIDATE, 1, 'invalid_report', 'report'),        # Maven failed with every test passing
    (BASELINE, 137, 'execution_failure', 'execution'),
    (SKIPPED, 0, 'completed', None),                   # skips are claims for the gates to reject
    (BASELINE.replace(b'benignPageKeepsEncodedPageParameter', b'other'), 1, 'invalid_report', 'report'),
])
def test_inconsistent_or_missing_reports_are_retained_not_admitted(store, stdout, native_exit, status, layer):
    result, *_ = run(store, (LISTED, 0), (stdout, native_exit))
    assert (result.execution.status, result.failure_layer) == (status, layer)
    if stdout and status != 'completed':
        assert result.execution.claims is None and store.get(result.execution.junit) == stdout


def test_witness_requests_are_unavailable_without_running_anything(store):
    request = WitnessRequest('jspwiki-main/src/main/java/org/apache/wiki/WikiServlet.java', 'WikiServlet.doGet', 'x.txt')
    result, execution, *_ = run(store, (LISTED, 0), (BASELINE, 1), witness=request)
    assert result.witness.status == 'unavailable' and 'SPEC-0039' in result.witness.detail
    assert len(execution.calls) == 2


@pytest.mark.parametrize('ids', [
    (IDS[0], IDS[0]),
    (IDS[0], 'tests/test_a.py::test_x'),
    (IDS[0], 'jspwiki-main/org.apache.wiki.OtherTest#x'),                    # outside the patch, other class
    ('org.apache.wiki.BenchmarkWikiServletForwardingTest#a', IDS[1]),       # wrong module for the patch file
    (IDS[0], 'other/org.apache.wiki.BenchmarkWikiServletForwardingTest#x'),
])
def test_ids_must_be_distinct_java_methods_of_one_patch_class(store, ids):
    with pytest.raises(ValueError):
        run(store, ids=ids)


def test_two_classes_are_refused_before_any_workspace(store):
    other = 'jspwiki-main/src/test/java/org/apache/wiki/OtherTest.java'
    patch = ApprovedPatch((PATCH.files[0], PatchFile(other, b'class OtherTest {}\n')), (TEST_PATH, other))
    with pytest.raises(ValueError, match='one class'):
        run(store, ids=(IDS[0], 'jspwiki-main/org.apache.wiki.OtherTest#x'), patch=patch)


@pytest.mark.parametrize('config', [dict(reports_dir='../reports'), dict(test_root='/abs'), dict(max_report_bytes=0),
                                    dict(output_dir='../out'), dict(dependency_plugin='maven-dependency-plugin'), dict(java='java')])
def test_operator_config_is_bounded(config):
    with pytest.raises(ValueError):
        MavenRunnerConfig(MVN, ROOT, **{'java': JAVA, 'console_jar': CONSOLE, **config})
    with pytest.raises(ValueError):
        MavenRunnerConfig(MVN, 'relative', JAVA, CONSOLE)


def test_java_runs_become_gate_evidence(store):
    from corsair.composition.evidence import run_evidence
    from corsair.core.disposition import EnvironmentIdentity
    identity = EnvironmentIdentity(image_digest='1' * 64, recipe_sha256='2' * 64, dependency_inventory_sha256='3' * 64,
                                   policy_revision='policy-1', limits_sha256='4' * 64)
    result, *_ = run(store, (LISTED, 0), (BASELINE, 1))
    evidence = run_evidence(result, environment=identity)
    assert evidence.discovered_test_ids == IDS and evidence.witness is None
    control, security = evidence.outcomes
    assert (control.test_id, control.outcome, security.outcome) == (IDS[0], 'passed', 'failed')
    assert (security.failure.path, security.failure.function, security.failure.line) == (
        TEST_PATH, 'inertWebRootResourceCannotSelectForwardTarget', 63)
