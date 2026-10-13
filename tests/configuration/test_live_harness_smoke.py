"""Offline smoke checks of the live harnesses: the Python a RIG0 run executes before its first native command.

These catch wiring bugs (an evidence directory not created, a gateway fixture whose teardown leaves later gates
without one, a fixture that does not resolve, a CLI that fails to parse) in CI instead of on the shared cluster. They
qualify nothing: every native command, gateway and image is a stub, and what runs after the first one is unchecked.
"""
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tests.qualification import qualify_image
from tests.qualification.support import ROOT

LIVE = ROOT / 'tests/qualification'


def make_markers():
    """Markers the Makefile's live targets select, each of which is one pytest run with one installed gateway."""
    return sorted(set(re.findall(r'pytest \$\(PYTEST_ROOT\) tests/qualification -m ([a-z0-9_]+)', (ROOT / 'Makefile').read_text())))


# One pytest session per make target, as on RIG0 (each target is its own run with its own evidence directory), then
# one for any live test no target selects.
DRIVER = """
import json, os, sys, pytest
out, markers = sys.argv[1], json.loads(sys.argv[2])
selections = [(m, m) for m in markers] + [('unselected', 'not (' + ' or '.join(markers) + ')')]
merged = {'runs': {}}
for name, expression in selections:
    os.environ['CORSAIR_SMOKE_RESULTS'] = out + '.' + name
    code = pytest.main(['-c', 'pyproject.toml', '--rootdir', '.', '--noconftest', '-p', 'tests.conftest',
                        '-p', 'tests.configuration.live_harness_stubs', '-p', 'no:cacheprovider', '-q', '--tb=no',
                        '--basetemp', out + '.tmp-' + name, '-m', expression, 'tests/qualification'])
    merged['runs'][name] = dict(json.load(open(out + '.' + name)), exit=int(code)) if os.path.exists(out + '.' + name) else {'exit': int(code)}
json.dump(merged, open(out, 'w'))
"""


@pytest.fixture(scope='module')
def stub_run(tmp_path_factory):
    results = tmp_path_factory.mktemp('smoke') / 'results.json'
    env = dict(os.environ, CORSAIR_CASE_SOURCES=str(tmp_path_factory.mktemp('sources')))
    completed = subprocess.run([sys.executable, '-c', DRIVER, str(results), json.dumps(make_markers())],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert results.is_file(), completed.stdout[-4000:] + completed.stderr[-4000:]
    return json.loads(results.read_text())['runs']


def test_every_live_test_reaches_its_first_native_call_without_a_harness_error(stub_run):
    outcomes = {test: outcome for run in stub_run.values() for test, outcome in run.get('outcomes', {}).items()}
    assert len(outcomes) > 20, 'Live tests were not collected: ' + json.dumps({k: v.get('exit') for k, v in stub_run.items()})
    broken = {test: outcome for test, outcome in outcomes.items() if not (outcome == 'passed' or outcome.startswith('stopped:'))}
    assert not broken, json.dumps(broken, indent=2)


def test_each_make_target_installs_at_most_one_gateway(stub_run):
    """`make openshell-install` installs one gateway, and the first fixture that consumes it uninstalls it."""
    several = {name: run['installs'] for name, run in stub_run.items() if name != 'unselected' and len(run.get('installs', [])) > 1}
    assert several == {}


def test_every_live_test_resolves_its_fixtures_with_the_real_conftest():
    completed = subprocess.run([sys.executable, '-m', 'pytest', '-c', str(ROOT / 'pyproject.toml'), '--rootdir', str(ROOT),
                                '-p', 'no:cacheprovider', '--setup-plan', '-q', str(LIVE)],
                               cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert completed.returncode == 0 and 'not found' not in completed.stdout, completed.stdout[-4000:]


def harness_clis():
    paths = [*sorted(LIVE.glob('*.py')), ROOT / 'deploy/kind/bootstrap.py']
    return [str(p.relative_to(ROOT).with_suffix('')).replace('/', '.') for p in paths if 'ArgumentParser(' in p.read_text()]


@pytest.mark.parametrize('module', harness_clis())
def test_every_harness_cli_imports_and_parses(module):
    # A subprocess: some harnesses set the process umask before parsing. PYTHONPATH as the make targets set it.
    env = dict(os.environ, PYTHONPATH=f'{ROOT / "src"}:{ROOT}')
    completed = subprocess.run([sys.executable, '-m', module, '--help'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0 and 'usage:' in completed.stdout, completed.stderr[-2000:]


def test_image_case_harness_creates_its_evidence_and_records_the_runner_result(tmp_path, monkeypatch):
    """Stubbed Docker and runner: the java image-case `run` phase up to the runner and back to its summary."""
    case = importlib.import_module('tests.qualification.java_image_case')
    calls = []

    def docker(*args, stdin=None, timeout=900):
        calls.append(args)
        if args[0] == 'inspect':
            return SimpleNamespace(returncode=1, stdout=b'', stderr=b'Error: No such object: stub')
        return SimpleNamespace(returncode=0, stdout=b'stub-container\n', stderr=b'')

    class Runner:
        def __init__(self, workspace, execution, store, config):
            pass

        def run(self, patch, **kwargs):
            return SimpleNamespace(failure_layer=None, detail='stub', cleanup='confirmed', discovery=None, execution=None)

    monkeypatch.setattr(case, 'docker', docker)
    monkeypatch.setattr(case, 'MavenRunner', Runner)
    checkout = tmp_path / 'checkout'
    (checkout / 'src/test/java/org/example').mkdir(parents=True)
    (checkout / 'src/test/java/org/example/ExampleTest.java').write_text('class ExampleTest {}')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    ids = ('org.example.ExampleTest#control', 'org.example.ExampleTest#security')
    summary = case.run('image', checkout, tmp_path / 'm2', 'a' * 40, ids, evidence, checkout, 60)
    assert summary['container_cleanup'] == 'confirmed' and json.loads((evidence / 'run.json').read_text())['ids'] == list(ids)
    assert calls[0][:2] == ('run', '-d') and ('rm', '--force', 'stub-container') in calls


class Answers:
    """Cluster answers for the qualify-image orchestrator."""

    def __init__(self, owned=True, installed=True, admission=(), network=()):
        self._owned, self._installed, self.good = owned, installed, {'admission': set(admission), 'network': set(network)}

    def owned(self):
        return self._owned

    def node_uid(self):
        return 'node-1'

    def sandbox_installed(self):
        return self._installed

    def admission_ok(self, path):
        assert str(path) in self.good['admission'], 'refused'

    def network_ok(self, path):
        assert str(path) in self.good['network'], 'refused'


def orchestrate(tmp_path, monkeypatch, answers, fail=None, case=None, prepared=False, retained_gateway=False, admission=None):
    monkeypatch.setattr(qualify_image, 'QUALIFY', tmp_path / 'qualify')
    monkeypatch.setattr(qualify_image, 'GATEWAY_STATE', tmp_path / 'openshell')
    monkeypatch.setattr(qualify_image, 'image_cache_state', lambda toolchain: 'prepared' if prepared else 'absent')
    if retained_gateway:
        (tmp_path / 'openshell').mkdir()
    calls = []

    def runner(target, log, variables):
        calls.append((target, {k: str(v) for k, v in variables.items()}))
        log.write_text('stub\n')
        return 2 if target == fail else 0

    run = qualify_image.Run('java8', case, tmp_path / 'qualify' / 'run', answers, runner=runner, admission=admission)
    stop = run.execute()
    qualify_image.write_summary(run, stop, 'start', 'end', {'commit': 'c' * 40, 'branch': 'b', 'checkout': '/x'})
    return run, stop, calls


def test_qualify_image_fresh_cluster_runs_the_whole_chain_in_order(tmp_path, monkeypatch):
    run, stop, calls = orchestrate(tmp_path, monkeypatch, Answers(owned=False, installed=False), case='CVE-1')
    assert stop.step is None
    assert [t for t, _ in calls] == ['tools', 'kind-up', 'admission-artifacts', 'admission-install', 'qualify-admission',
                                     'qualify-network', 'toolchain-images', 'toolchain-images-load', 'openshell-install',
                                     'qualify-toolchain', 'openshell-install', 'qualify-java8-case']
    variables = dict(calls)
    assert variables['qualify-toolchain']['TOOLCHAINS'] == 'java8'
    assert variables['qualify-toolchain']['CORSAIR_NETWORK_RUN'] == str(run.root / 'network')
    assert variables['openshell-install']['CORSAIR_ADMISSION_RUN'] == str(run.root / 'admission')
    assert variables['qualify-java8-case']['CASE'] == 'CVE-1'
    assert '**passed**' in (run.root / 'SUMMARY.md').read_text()


def test_qualify_image_reuses_evidence_the_gate_checks_accept_and_stops_at_the_first_failure(tmp_path, monkeypatch):
    earlier = tmp_path / 'qualify' / 'earlier'
    for name in ('admission', 'network'):
        (earlier / name).mkdir(parents=True)
    answers = Answers(admission={str(earlier / 'admission')}, network={str(earlier / 'network')})
    run, stop, calls = orchestrate(tmp_path, monkeypatch, answers, fail='qualify-toolchain', prepared=True)
    assert [t for t, _ in calls] == ['tools', 'toolchain-images-load', 'openshell-install', 'qualify-toolchain']
    assert run.steps['admission']['outcome'] == run.steps['network']['outcome'] == 'reused'
    assert stop.step == 'gate' and run.steps['case']['outcome'] == 'unrun'
    summary = json.loads((run.root / 'summary.json').read_text())
    assert summary['outcome'] == 'failed' and summary['failed_step'] == 'gate'


def test_qualify_image_refuses_retained_state_instead_of_adopting_it(tmp_path, monkeypatch):
    run, stop, calls = orchestrate(tmp_path, monkeypatch, Answers(), retained_gateway=True)
    assert stop.step == 'gateway' and 'openshell-install' not in [t for t, _ in calls]
    assert 'qualify-gateway' in run.steps['gateway']['detail']


def test_qualify_image_refused_earlier_evidence_is_recorded_and_rerun(tmp_path, monkeypatch):
    earlier = tmp_path / 'qualify' / 'earlier' / 'admission'
    earlier.mkdir(parents=True)
    run, stop, calls = orchestrate(tmp_path, monkeypatch, Answers(), prepared=True)
    assert run.steps['admission']['refused_candidates'][0]['path'] == str(earlier)
    assert 'qualify-admission' in [t for t, _ in calls] and 'admission-install' not in [t for t, _ in calls]


def test_rig0_allow_rules_cover_the_runbook_and_never_the_blocked_commands():
    """deploy/rig0/settings.local.json: Al merges it into RIG0's .claude/settings.local.json once."""
    rules = json.loads((ROOT / 'deploy/rig0/settings.local.json').read_text())['permissions']
    assert all(rule.startswith('Bash(') and rule.endswith(')') for rule in rules['allow'] + rules['deny'])
    allowed = ' '.join(rules['allow'])
    for blocked in ('mkfs', 'dd if=', 'delete', 'workspace-storage', 'qualify-gateway', 'kind-up', '--force'):
        assert blocked not in allowed
    targets = qualify_image.make_targets()
    for target in re.findall(r'make -C \S+ ([a-z0-9-]+)', allowed):
        assert target in targets
    # The five substrings Al's pre-bash hook refuses (PLAN-0040), and make options that would replace the Makefile.
    assert {'Bash(*mkfs*)', 'Bash(*dd if=*)', 'Bash(*delete namespace*)', 'Bash(*delete --all*)', 'Bash(*rm -rf /*)',
            'Bash(make *--eval*)', 'Bash(make * -f*)', 'Bash(make *--file*)'} <= set(rules['deny'])


@pytest.mark.parametrize('argv', [
    ['qualify-image', 'TOOLCHAIN=java8', 'kind-down'],
    ['kind-up', 'qualify-image', 'TOOLCHAIN=java8'],
    ['qualify-image', 'TOOLCHAIN=java8";id;"'],
    ['qualify-image', 'TOOLCHAIN=java8 python'],
    ['qualify-image'],
    ['qualify-image', 'TOOLCHAIN=java8', 'SHELL=/tmp/other'],
    ['archive-runs', 'PYTHONPATH=/tmp/other'],
    ['cluster-status', 'qualify-gateway'],
])
def test_pre_allowed_targets_refuse_extra_goals_variables_and_unknown_toolchains(argv):
    completed = subprocess.run(['make', '-n', '--no-print-directory', '-C', str(ROOT), *argv], capture_output=True, text=True, timeout=60)
    assert completed.returncode != 0 and '***' in completed.stderr and not completed.stdout.strip()


def test_pre_allowed_targets_keep_values_out_of_recipe_text():
    completed = subprocess.run(['make', '-n', '--no-print-directory', '-C', str(ROOT), 'qualify-image', 'TOOLCHAIN=java8', 'CASE=x"; id; "'],
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0 and 'id;' not in completed.stdout and '"$QUALIFY_CASE"' in completed.stdout
    with pytest.raises(SystemExit):
        qualify_image.main(['run', '--toolchain', 'java8', '--case', 'x"; id; "'])


def test_qualify_image_stops_when_explicitly_named_evidence_is_refused(tmp_path, monkeypatch):
    run, stop, calls = orchestrate(tmp_path, monkeypatch, Answers(), prepared=True, admission=str(tmp_path / 'named'))
    assert stop.step == 'admission' and 'qualify-admission' not in [t for t, _ in calls]
    assert 'named explicitly' in run.steps['admission']['detail']


def test_qualify_image_refuses_a_case_its_case_target_does_not_run_before_installing_anything(monkeypatch):
    assert qualify_image.case_ids('python37') == ['CVE-2021-32839'] and qualify_image.case_ids('java8') == []
    monkeypatch.setattr(qualify_image, 'git', lambda *args: '' if args[0] == 'status' else 'x')
    for toolchain, case in (('python37', 'CVE-0000-0000'), ('java8', 'VUL4J-6')):
        with pytest.raises(SystemExit, match='does not run'):
            qualify_image.main(['run', '--toolchain', toolchain, '--case', case])
