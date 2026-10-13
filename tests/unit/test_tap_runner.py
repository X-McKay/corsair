"""TAP report admission and runner orchestration over real Perl 5.26.3 output (tap_reports/runner/README.md)."""
import json
from pathlib import Path
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.native_runner import WITNESS_READ
from corsair.adapters.tap_runner import LISTER, WRAPPER, TapRunner, TapRunnerConfig, listed
from corsair.adapters.tap_runner import PERL_PROBE_SHA256, perl_probe_argv
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PerlTestId, WitnessRequest
from corsair.reports.tap import TapError, parse_tap
from tests.unit.test_pytest_runner import Scripted, Workspace, store  # noqa: F401  (fixture)

CAPTURES = Path(__file__).with_name('tap_reports') / 'runner'
EXITS = json.loads((CAPTURES / 'exits.json').read_text())
ROOT = '/sandbox/src'
PERL = ('/usr/local/bin/perl', '-Iblib/lib', '-Iblib/arch', '-Ilib')


def ids(name):
    return (f't/{name}.t#test_control', f't/{name}.t#test_security')


def tap(name):
    return (CAPTURES / f'{name}.tap').read_bytes()


def parse(name, exit_status=None):
    return parse_tap(tap(name), ids(name), exit_status=EXITS[name]['run_exit'] if exit_status is None else exit_status,
                     test_paths=frozenset({f't/{name}.t'}))


def test_every_capture_has_its_source_and_exit_statuses():
    names = sorted(path.stem for path in CAPTURES.glob('*.t'))
    assert names == sorted(EXITS) and all((CAPTURES / f'{n}.tap').exists() and (CAPTURES / f'{n}.list').exists() for n in names)


def test_passing_and_failing_subtests_are_admitted_with_test_more_diagnostics():
    assert [case.outcome for case in parse('pass')] == ['passed', 'passed']
    control, security = parse('fail')
    assert (control.outcome, security.outcome) == ('passed', 'failed')
    failure = security.failure
    assert (failure.kind, failure.path, failure.function, failure.line) == ('failure', 't/fail.t', 'test_security', 8)
    assert "got: '0'" in failure.message and "expected: '1'" in failure.message


def test_a_subtest_that_dies_is_an_error_with_its_message():
    control, security = parse('die')
    assert (control.outcome, security.outcome) == ('passed', 'error')
    assert security.failure.kind == 'error' and 'boom in security' in security.failure.message


def test_a_skip_inside_a_subtest_makes_it_skipped_not_passed():
    assert [case.outcome for case in parse('innerskip')] == ['passed', 'skipped']


@pytest.mark.parametrize('name, message', [
    ('todo', 'todo'),
    ('extra', 'outside a subtest'),
    ('bail', 'bailed out'),
    ('noplan', 'plan'),
    ('skipall', 'skipped all'),
    ('controldie', 'Missing subtests'),
])
def test_streams_that_hide_or_lose_an_outcome_are_refused(name, message):
    with pytest.raises(TapError, match=message):
        parse(name)


@pytest.mark.parametrize('name, exit_status', [('pass', 1), ('fail', 0), ('fail', 255), ('die', 1)])
def test_the_exit_status_must_agree_with_the_outcomes(name, exit_status):
    with pytest.raises(TapError, match='Exit'):
        parse(name, exit_status)


def test_ids_must_be_two_subtests_of_one_file():
    with pytest.raises(TapError):
        parse_tap(tap('pass'), ('t/pass.t#test_control', 't/other.t#test_security'), exit_status=0,
                  test_paths=frozenset({'t/pass.t'}))
    with pytest.raises(ValueError):
        PerlTestId.parse('../t/pass.t#test_control')


def test_the_lister_names_subtests_and_refuses_tests_outside_them():
    assert listed((CAPTURES / 'pass.list').read_bytes()) == ('test_control', 'test_security')
    assert listed((CAPTURES / 'extra.list').read_bytes()) is None
    assert listed((CAPTURES / 'skipall.list').read_bytes()) == ()
    assert EXITS['syntaxerr']['list_exit'] != 0 and EXITS['bail']['list_exit'] != 0


def run(store, name, *steps, witness=None, discovery=PERL, record=None):
    path = f't/{name}.t'
    patch = ApprovedPatch((PatchFile(path, (CAPTURES / f'{name}.t').read_bytes()),), (path,))
    workspace, execution = Workspace(store, ROOT), Scripted(*steps)
    runner = TapRunner(workspace, execution, store, TapRunnerConfig(PERL, ROOT, witness_record_path=record))
    operation = uuid4()
    result = runner.run(patch, control_test_id=ids(name)[0], security_test_id=ids(name)[1], discovery_command=discovery,
                        operation=operation, witness=witness)
    return result, execution, workspace, operation


def test_listed_discovery_then_one_execution_admits_claims_from_tap(store):
    result, execution, workspace, operation = run(store, 'fail', ((CAPTURES / 'fail.list').read_bytes(), 0),
                                                  (tap('fail'), 1))
    assert [call[0] for call in execution.calls] == [
        ('/bin/sh', '-c', WRAPPER, 'corsair-tap-discover', ROOT, *PERL, '-e', LISTER, 't/fail.t'),
        ('/bin/sh', '-c', WRAPPER, 'corsair-tap', ROOT, *PERL, 't/fail.t')]
    assert [call[1] for call in execution.calls] == [uuid5(operation, 'discovery'), uuid5(operation, 'execution')]
    assert result.failure_layer is None and result.cleanup == 'confirmed' and result.discovery.test_ids == ids('fail')
    claims = result.execution.claims
    assert store.get(claims.report) == tap('fail') and claims.native_exit == 1
    assert (claims.claims.control.outcome, claims.claims.security.outcome) == ('passed', 'failed')
    assert workspace.calls[-1][0] == 'release'


@pytest.mark.parametrize('name, native_exit', [('extra', 0), ('syntaxerr', 2), ('skipall', 0)])
def test_inexact_or_failed_listing_never_executes(store, name, native_exit):
    result, execution, *_ = run(store, name, ((CAPTURES / f'{name}.list').read_bytes(), native_exit))
    assert result.failure_layer == 'discovery' and result.execution is None and len(execution.calls) == 1


def test_a_hidden_outcome_is_retained_but_not_admitted(store):
    result, *_ = run(store, 'todo', ((CAPTURES / 'todo.list').read_bytes(), 0), (tap('todo'), 0))
    assert result.failure_layer == 'report' and result.execution.status == 'invalid_report'
    assert result.execution.claims is None and store.get(result.execution.junit) == tap('todo')


RECORD = '/tmp/corsair-witness.json'
WITNESS = WitnessRequest('lib/HTTP/Tiny.pm', 'HTTP.Tiny.new', 'effect.txt')


def test_a_witness_runs_the_file_through_the_probe_and_reads_its_record_once(store):
    record = b'{"schema": "corsair-witness-v2"}'
    result, execution, _, operation = run(store, 'fail', ((CAPTURES / 'fail.list').read_bytes(), 0), (tap('fail'), 1),
                                          (record, 0), witness=WITNESS, record=RECORD)
    nonce = str(uuid5(operation, 'witness-nonce'))
    probed = perl_probe_argv(PERL, WITNESS, 't/fail.t', root=ROOT, record_path=RECORD, nonce=nonce)
    assert [call[0] for call in execution.calls][1:] == [
        ('/bin/sh', '-c', WRAPPER, 'corsair-tap', ROOT, *probed), ('/bin/sh', '-c', WITNESS_READ, 'corsair-witness', RECORD)]
    assert result.execution.status == 'completed' and result.witness.status == 'captured'
    assert (result.witness.probe_sha256, result.witness.nonce, result.witness.record) == (PERL_PROBE_SHA256, nonce, record)
    assert store.get(result.witness.artifact) == record


def test_a_witness_is_not_read_after_a_failed_execution_and_needs_an_operator_record_path(store):
    result, execution, *_ = run(store, 'pass', ((CAPTURES / 'pass.list').read_bytes(), 0), (tap('pass'), 1),
                                witness=WITNESS, record=RECORD)
    assert result.execution.status == 'invalid_report' and result.witness.status == 'unavailable'
    assert len(execution.calls) == 2
    with pytest.raises(ValueError, match='record path'):
        run(store, 'pass', witness=WITNESS)
    with pytest.raises(ValueError):
        TapRunnerConfig(PERL, ROOT, witness_record_path=f'{ROOT}/witness.json')


@pytest.mark.parametrize('command', [('perl', '-Ilib'), ('/usr/local/bin/perl', '-e', '1'), ('/usr/local/bin/perl', '-I/abs')])
def test_operator_prefix_is_an_absolute_perl_with_relative_includes_only(command):
    with pytest.raises(ValueError):
        TapRunnerConfig(command, ROOT)


@pytest.mark.parametrize('command', [('prove', '--dry', '-b', 't/'), ('/usr/local/bin/perl',)])
def test_environment_discovery_command_is_accepted_not_run(store, command):
    # The runner builds its own listing, so the environment's discovery command is carried, never run: the argv
    # executed and the result are those of the operator prefix. An empty command is still refused.
    steps = (((CAPTURES / 'fail.list').read_bytes(), 0), (tap('fail'), 1))
    expected, executed, *_ = run(store, 'fail', *steps)
    result, execution, *_ = run(store, 'fail', *steps, discovery=command)
    assert [call[0] for call in execution.calls] == [call[0] for call in executed.calls]
    assert result.execution.status == expected.execution.status == 'completed'
    with pytest.raises(ValueError):
        run(store, 'fail', discovery=())


def test_tap_runs_become_gate_evidence(store):
    from corsair.composition.evidence import run_evidence
    from corsair.core.disposition import EnvironmentIdentity
    identity = EnvironmentIdentity(image_digest='1' * 64, recipe_sha256='2' * 64, dependency_inventory_sha256='3' * 64,
                                   policy_revision='policy-1', limits_sha256='4' * 64)
    result, *_ = run(store, 'fail', ((CAPTURES / 'fail.list').read_bytes(), 0), (tap('fail'), 1))
    evidence = run_evidence(result, environment=identity)
    control, security = evidence.outcomes
    assert (control.outcome, security.outcome) == ('passed', 'failed')
    assert (security.failure.path, security.failure.function, security.failure.line) == ('t/fail.t', 'test_security', 8)
