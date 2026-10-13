"""Minitest runner orchestration over fake ports, replaying real listings and reports captured on Ruby 3.1.7.

`minitest_reports/` holds the runner's own discovery and execution output for Minitest 5.14.4, 5.15.0 and
5.27.0 in the `ruby31` image (see its README); the project there is the fixture these ids name.
"""
import json
from pathlib import Path
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.minitest_runner import CHDIR, LIST, RUN, MinitestRunner, MinitestRunnerConfig, listed
from corsair.ports.execution import ExecutionError
from corsair.ports.test_runner import ApprovedPatch, PatchFile, RubyTestId, WitnessRequest
from corsair.reports.minitest import MinitestReportError, parse_minitest
from tests.unit.test_pytest_runner import Scripted, Workspace, store  # noqa: F401  (fixture)

REPORTS = Path(__file__).with_name('minitest_reports')
VERSIONS = ('5.14.4', '5.15.0', '5.27.0')
ROOT = '/ws'
RUBY = ('/usr/bin/env', 'BUNDLE_FROZEN=true', '/usr/local/bin/bundle', 'exec', '/usr/local/bin/ruby', '-Itest', '-Ilib')
TEST_PATH = 'test/corsair_widget_test.rb'
F = TEST_PATH + '::Widget::CorsairTest#'
IDS = (F + 'test_control', F + 'test_fixed')
MIXED = tuple(F + m for m in ('test_control', 'test_security', 'test_error', 'test_skipped'))
PATCH = ApprovedPatch((PatchFile(TEST_PATH, (REPORTS / 'project' / TEST_PATH).read_bytes()),), (TEST_PATH,))


def capture(version, kind):
    return (REPORTS / f'ruby3.1.7-minitest{version}-{kind}').read_bytes()


def run(store, *steps, ids=IDS, patch=PATCH, witness=None, command=RUBY):
    workspace, execution = Workspace(store, ROOT), Scripted(*steps)
    runner = MinitestRunner(workspace, execution, store, MinitestRunnerConfig(RUBY, ROOT))
    operation = uuid4()
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=command,
                        operation=operation, witness=witness)
    return result, execution, workspace, operation


def listing(*methods):
    return ''.join(f'Widget::CorsairTest#{m}\n' for m in sorted(methods)).encode()


@pytest.mark.parametrize('version', VERSIONS)
def test_real_listing_and_reports_parse_on_every_captured_version(version):
    assert listed(capture(version, 'listing.txt')) == tuple(
        ('Widget::CorsairTest', m) for m in ('test_control', 'test_error', 'test_security', 'test_skipped'))
    cases = parse_minitest(capture(version, 'report.json'), MIXED, root=ROOT, test_paths=frozenset({TEST_PATH}))
    assert [case.outcome for case in cases] == ['passed', 'failed', 'error', 'skipped']
    failed, error = cases[1].failure, cases[2].failure
    assert (failed.kind, failed.type, failed.path, failed.function, failed.line) == (
        'failure', 'Minitest::Assertion', TEST_PATH, 'test_security', 10)
    assert 'Expected: "&lt;b&gt;"' in failed.message
    assert (error.kind, error.type, error.path, error.function, error.line, error.message) == (
        'error', 'ArgumentError', TEST_PATH, 'test_error', 18, 'boom')
    assert [c.outcome for c in parse_minitest(capture(version, 'pass.json'), IDS, root=ROOT,
                                              test_paths=frozenset({TEST_PATH}))] == ['passed', 'passed']


@pytest.mark.parametrize('version', VERSIONS)
def test_listed_discovery_then_one_execution_admits_claims(store, version):
    result, execution, workspace, operation = run(store, (listing('test_control', 'test_fixed'), 0),
                                                  (capture(version, 'pass.json'), 0))
    args = ('--', TEST_PATH, 'Widget::CorsairTest', 'test_control', 'test_fixed')
    assert [call[0] for call in execution.calls] == [
        ('/bin/sh', '-c', CHDIR, 'corsair-minitest', ROOT, *RUBY, '-e', LIST, *args),
        ('/bin/sh', '-c', CHDIR, 'corsair-minitest', ROOT, *RUBY, '-e', RUN, *args)]
    assert [call[1] for call in execution.calls] == [uuid5(operation, 'discovery'), uuid5(operation, 'execution')]
    assert result.failure_layer is None and result.cleanup == 'confirmed' and result.discovery.test_ids == IDS
    claims = result.execution.claims
    assert store.get(claims.report) == capture(version, 'pass.json') and claims.native_exit == 0
    assert (claims.claims.control.test_id, claims.claims.security.outcome) == (IDS[0], 'passed')
    assert workspace.calls[-1][0] == 'release'


def test_failed_security_test_is_a_claim_with_its_location(store):
    report = json.loads(capture('5.15.0', 'report.json'))
    report['tests'] = [t for t in report['tests'] if t['name'] in ('test_control', 'test_security')]
    ids = (F + 'test_control', F + 'test_security')
    result, *_ = run(store, (listing('test_control', 'test_security'), 0), (json.dumps(report).encode(), 1), ids=ids)
    assert result.execution.status == 'completed'
    assert [case.outcome for case in result.execution.cases] == ['passed', 'failed']
    assert result.execution.claims.claims.security.outcome == 'failed' and result.execution.cases[1].failure.line == 10


@pytest.mark.parametrize('stdout, native_exit, detail', [
    (listing('test_control', 'test_fixed'), 1, 'exit 1'),              # load or class failure
    (listing('test_control'), 0, 'found ['),                            # selected method missing
    (listing('test_control', 'test_fixed') + b'helper noise\n', 0, 'found []'),
    (listing('test_control', 'test_fixed').replace(b'Widget::', b'Other::'), 0, 'found ['),
    (b'', 0, 'found []'),
])
def test_inexact_or_failed_discovery_never_executes(store, stdout, native_exit, detail):
    result, execution, *_ = run(store, (stdout, native_exit))
    assert result.discovery.status == 'collection_error' and result.execution is None
    assert result.failure_layer == 'discovery' and detail in result.detail and len(execution.calls) == 1
    assert result.cleanup == 'confirmed'


def test_execution_error_is_not_retried(store):
    result, execution, *_ = run(store, (listing('test_control', 'test_fixed'), 0), lambda planned: ExecutionError(planned))
    assert result.failure_layer == 'execution' and result.execution.status == 'execution_failure'
    assert len(execution.calls) == 2 and result.cleanup == 'confirmed'


PASS = capture('5.15.0', 'pass.json')


@pytest.mark.parametrize('stdout, native_exit, status, layer', [
    (b'', 1, 'execution_failure', 'execution'),                        # load or Bundler failure, no report
    (PASS, 1, 'invalid_report', 'report'),                             # exit conflicts with outcomes
    (PASS, 137, 'execution_failure', 'execution'),
    (PASS.replace(b'test_fixed', b'test_other'), 0, 'invalid_report', 'report'),
    (PASS.replace(b'corsair-minitest-v1', b'corsair-minitest-v0'), 0, 'invalid_report', 'report'),
    (b'{"schema": "corsair-minitest-v1", "tests": [], "tests": []}', 0, 'invalid_report', 'report'),
    (PASS + b'trailing', 0, 'invalid_report', 'report'),
    (PASS.replace(b'"class":"Widget::CorsairTest"', b'"class":[]', 1), 0, 'invalid_report', 'report'),  # unhashable identity
])
def test_inconsistent_or_missing_reports_are_retained_not_admitted(store, stdout, native_exit, status, layer):
    result, *_ = run(store, (listing('test_control', 'test_fixed'), 0), (stdout, native_exit))
    assert (result.execution.status, result.failure_layer) == (status, layer)
    if stdout:
        assert result.execution.claims is None and store.get(result.execution.junit) == stdout


@pytest.mark.parametrize('mutate', [
    lambda t: t[0].update(outcome='failed'),                           # failure missing
    lambda t: t[0].update(outcome='unknown'),
    lambda t: t.append(dict(t[0])),                                    # duplicate result
    lambda t: t[0].update(extra=1),
    lambda t: t.pop(),                                                 # missing result
    lambda t: t[0].update({'class': []}),                              # identities must be strings
    lambda t: t[0].update({'class': {'a': 1}}),
    lambda t: t[0].update(name=['test_control']),
    lambda t: t[0].update(outcome=['passed']),
])
def test_parser_refuses_ambiguous_reports(mutate):
    report = json.loads(PASS)
    mutate(report['tests'])
    with pytest.raises(MinitestReportError):
        parse_minitest(json.dumps(report).encode(), IDS, root=ROOT, test_paths=frozenset({TEST_PATH}))


def test_witness_requests_are_unavailable_without_running_anything(store):
    request = WitnessRequest('lib/widget.rb', 'Widget.escape', 'x.txt')
    result, execution, *_ = run(store, (listing('test_control', 'test_fixed'), 0), (PASS, 0), witness=request)
    assert result.witness.status == 'unavailable' and 'SPEC-0063' in result.witness.detail
    assert len(execution.calls) == 2


@pytest.mark.parametrize('ids', [
    (IDS[0], IDS[0]),
    (IDS[0], 'tests/test_a.py::test_x'),
    (IDS[0], 'test/other_test.rb::Widget::CorsairTest#test_x'),            # outside the patch
    (IDS[0], TEST_PATH + '::Widget::OtherTest#test_x'),                    # other class
    (IDS[0], TEST_PATH + '::Widget::CorsairTest#control'),                 # not a test method
    (IDS[0], TEST_PATH + '::Widget::CorsairTest#test_0001_has spaces'),    # spec-style name
])
def test_ids_must_be_distinct_minitest_methods_of_one_patch_class(store, ids):
    with pytest.raises(ValueError):
        run(store, ids=ids)


@pytest.mark.parametrize('command', [
    ('/usr/local/bin/ruby',), ('ruby', '-Itest'), ('/usr/local/bin/ruby', '-e', 'p 1'), ('/usr/local/bin/ruby', 'test/x.rb'),
    ('/usr/local/bin/bundle', 'exec', 'rake', 'test'), ('/usr/local/bin/ruby', '-epp 1'), ()])
def test_operator_config_is_bounded(command):
    if command == ('/usr/local/bin/ruby',):
        assert MinitestRunnerConfig(command, ROOT).command == command
        with pytest.raises(ValueError):
            MinitestRunnerConfig(command, 'relative')
        return
    with pytest.raises(ValueError):
        MinitestRunnerConfig(command, ROOT)


@pytest.mark.parametrize('command', [('find', 'test', '-name', '*_test.rb'), RUBY + (TEST_PATH,)])
def test_environment_discovery_command_is_recorded_not_run(store, command):
    # The runner builds its own listing, so the environment's discovery command is carried, never run: the argv
    # executed and the result are those of the operator prefix. An empty command is still refused.
    steps = ((listing('test_control', 'test_fixed'), 0), (capture('5.15.0', 'pass.json'), 0))
    expected, executed, *_ = run(store, *steps)
    result, execution, *_ = run(store, *steps, command=command)
    assert [call[0] for call in execution.calls] == [call[0] for call in executed.calls]
    assert result.execution.status == expected.execution.status == 'completed'
    with pytest.raises(ValueError):
        run(store, command=())


def test_ruby_test_ids_round_trip():
    item = RubyTestId.parse(IDS[0])
    assert (item.path, item.class_name, item.method, str(item)) == (TEST_PATH, 'Widget::CorsairTest', 'test_control', IDS[0])


def test_ruby_runs_become_gate_evidence(store):
    from corsair.composition.evidence import run_evidence
    from corsair.core.disposition import EnvironmentIdentity
    identity = EnvironmentIdentity(image_digest='1' * 64, recipe_sha256='2' * 64, dependency_inventory_sha256='3' * 64,
                                   policy_revision='policy-1', limits_sha256='4' * 64)
    result, *_ = run(store, (listing('test_control', 'test_fixed'), 0), (PASS, 0))
    evidence = run_evidence(result, environment=identity)
    assert evidence.discovered_test_ids == IDS and evidence.witness is None
    assert [o.outcome for o in evidence.outcomes] == ['passed', 'passed']
