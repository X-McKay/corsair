"""Native 1E fixed projects; no application adapter or finding-validation claim."""
import copy
import hashlib
import ipaddress
import json
import shutil
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from openshell import SandboxClient, TlsConfig
import pytest
import yaml

from tests.qualification.support import ROOT, NetworkFixture
from tests.qualification.gateway import native_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_policy import require_network, owned_sandbox, observe_policy, global_policy_observation, wait_logging_activation, expect_permission_denied
from tests.qualification.prepare_toolchains import JAVA_TESTS, LAUNCHER, PYTHONS, RUBY_RUN, RUBY_SUMMARY, RUBY_TESTS, SOURCE, image_receipt, source_hashes
from corsair.adapters.maven_runner import WRAPPER, MavenRunner, MavenRunnerConfig, selection
from corsair.reports.junit_listing import listed

# Exact interpreter and pytest each Python toolchain image carries (its requirements.txt pins).
PYTHON_TOOLCHAINS = {'python': ('/usr/local/bin/python3.12', (3, 12), '9.0.3'),
                     'python37': ('/usr/local/bin/python3.7', (3, 7), '7.4.4')}


@pytest.fixture
def image_kube(kube, request):
    """Per-image evidence: each gate writes under `<evidence>/<test name>/`, so one run of all toolchain gates keeps
    every image's receipts apart."""
    view = copy.copy(kube)
    view.evidence = kube.evidence / request.node.name
    view.evidence.mkdir(mode=0o700)
    return view


@pytest.fixture(scope='module')
def toolchain_gateway(kube, request):
    """One installed gateway for every selected image: its teardown uninstalls it, so a per-test gateway would leave
    the second gate without one. Its controls and cleanup receipts are at the run's top level."""
    require_network(kube, request.config.getoption('--network-evidence'))
    with native_gateway(kube) as value:
        yield value


def toolchain_policy(language):
    policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    # Ruby, Bundler and the bundled gems live under /usr/local, already read-only.
    policy['filesystem_policy']['read_only'] += ['/opt/corsair-fixture'] + ([] if language in PYTHONS or language == 'ruby31' else ['/opt/java/openjdk', '/opt/corsair-m2', '/opt/corsair-m2.sha256', '/opt/corsair-junit', '/opt/corsair-junit.sha256'])
    return policy


def native_report(text, expected):
    """Reject incomplete, stale-format or nonexecuted native report claims."""
    root = ET.fromstring(text)
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    assert suites and all(s.attrib['tests'] == str(len(s.findall('testcase'))) for s in suites)
    assert sum(int(s.attrib['tests']) for s in suites) == len(expected)
    assert all(all(s.attrib[key] == '0' for key in ('failures', 'errors', 'skipped')) for s in suites)
    cases = [case for suite in suites for case in suite.findall('testcase')]
    assert sorted((c.attrib['classname'], c.attrib['name']) for c in cases) == sorted(expected)
    assert all(not any(c.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for c in cases)
    return {'tests': len(cases), 'ids': [(c.attrib['classname'], c.attrib['name']) for c in cases], 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def expect_completed(result, exit_code, evidence_text):
    assert result.exit_code == exit_code
    assert evidence_text in result.stdout + result.stderr, 'Missing native producing-layer detail'


def stage_project(kube, cli, sdk, name, language, record):
    project = kube.evidence / (language + '-project')
    project.mkdir()
    if language in PYTHONS:
        shutil.copyfile(SOURCE / language / 'test_native.py', project / 'test_native.py')
    elif language == 'ruby31':
        for path in ('Gemfile', 'Gemfile.lock'):
            shutil.copyfile(SOURCE / language / path, project / path)
        shutil.copytree(SOURCE / language / 'test', project / 'test')
    else:
        shutil.copyfile(SOURCE / language / 'pom.xml', project / 'pom.xml')
        shutil.copytree(SOURCE / language / 'src', project / 'src')
    cwd = sdk.call('exec', name, ['/bin/pwd'], workspace='default', no_login_shell=True, timeout_seconds=20)
    assert cwd.exit_code == 0 and cwd.stderr == '' and cwd.stdout.startswith('/') and cwd.stdout.count('\n') == 1
    remote = cwd.stdout.rstrip('\n') + '/' + project.name
    cli('sandbox', 'upload', '--no-git-ignore', name, str(project))
    hashes = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(project.rglob('*')) if p.is_file()}
    result = sdk.call('exec', name, ['/usr/bin/sha256sum', *hashes], workspace='default', workdir=remote, no_login_shell=True, timeout_seconds=20)
    assert result.exit_code == 0 and result.stderr == ''
    assert result.stdout == ''.join(h + '  ' + p + '\n' for p, h in hashes.items())
    record.update(project_hashes=hashes, workdir=remote)
    return remote


def execute(sdk, name, argv, workdir, timeout=60):
    return sdk.call('exec', name, argv, workspace='default', workdir=workdir, no_login_shell=True, timeout_seconds=timeout)


def report(sdk, name, remote, expected, record):
    result = execute(sdk, name, ['/bin/cat', remote], '/tmp')
    assert result.exit_code == 0 and result.stderr == ''
    record.setdefault('native_reports', []).append(native_report(result.stdout, expected))


def python_offline(sdk, name, remote, record, language='python'):
    python, series, pytest_version = PYTHON_TOOLCHAINS[language]
    result = execute(sdk, name, [python, '-c', f'import sys,pytest; assert sys.version_info[:2]=={series!r}; assert pytest.__version__=={pytest_version!r}; print(sys.version); print(pytest.__version__)'], remote)
    expect_completed(result, 0, pytest_version)
    record['versions'] = result.stdout
    result = execute(sdk, name, [python, '-m', 'pytest', '-q', 'test_native.py', '--junitxml=' + remote + '/passed.xml'], remote)
    expect_completed(result, 0, '1 passed')
    report(sdk, name, remote + '/passed.xml', [('test_native', 'test_native_roundtrip')], record)
    setup = execute(sdk, name, ['/bin/sh', '-ec', 'mkdir /tmp/no-tests; printf "def test_syntax(:\\n" > /tmp/test_syntax.py; printf "def test_assertion():\\n    assert 1 == 2\\n" > /tmp/test_assertion.py'], remote)
    expect_completed(setup, 0, '')
    result = execute(sdk, name, [python, '-m', 'pytest', '-q', '/tmp/test_syntax.py'], remote)
    expect_completed(result, 2, 'SyntaxError')
    result = execute(sdk, name, [python, '-m', 'pytest', '-q', '/tmp/no-tests'], remote)
    expect_completed(result, 5, 'no tests ran')
    result = execute(sdk, name, [python, '-m', 'pytest', '-q', '/tmp/test_assertion.py'], remote)
    expect_completed(result, 1, 'AssertionError')
    record['offline_diagnostics'] = ['syntax/collection', 'no-discovery', 'assertion']


# Per-image expectations: the same fixture shape and diagnostics, the image's own JDK and JUnit generation.
JAVA = {
    'java': {'javac': 'javac 17.', 'runtime': 'Java version: 17.', 'expected': 'expected: <1> but was: <2>',
             'assertion': 'package corsair; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class AssertionTest { @Test void deliberateFailure() { assertEquals(1, 2); } }',
             'engine': 'junit-jupiter'},
    'java8': {'javac': 'javac 1.8.0_', 'runtime': 'Java version: 1.8.0_', 'expected': 'expected:<1> but was:<2>',
              'assertion': 'package corsair; import org.junit.Test; import static org.junit.Assert.assertEquals; public class AssertionTest { @Test public void deliberateFailure() { assertEquals(1, 2); } }',
              'engine': 'junit-vintage'},
}
FIXTURE_IDS = tuple('corsair.NativeTest#' + name for name in JAVA_TESTS)


def java_offline(sdk, name, remote, record, language):
    expect = JAVA[language]
    result = execute(sdk, name, ['/bin/sh', '-ec', 'sha256sum -c /opt/corsair-junit.sha256 >/dev/null; cd /opt/corsair-m2; sha256sum -c /opt/corsair-m2.sha256 >/dev/null; cp -R /opt/corsair-m2 /tmp/m2; /opt/java/openjdk/bin/javac -version 2>&1; /usr/share/maven/bin/mvn -version'], remote)
    expect_completed(result, 0, 'Apache Maven 3.10.0')
    assert expect['javac'] in result.stdout and expect['runtime'] in result.stdout
    record['versions'] = result.stdout
    mvn = ['/usr/share/maven/bin/mvn', '-B', '-ntp', '-o', '-Dmaven.repo.local=/tmp/m2']
    result = execute(sdk, name, mvn + ['test'], remote)
    expect_completed(result, 0, f'Tests run: {len(JAVA_TESTS)}, Failures: 0, Errors: 0, Skipped: 0')
    report(sdk, name, remote + '/target/surefire-reports/TEST-corsair.NativeTest.xml', [('corsair.NativeTest', n) for n in JAVA_TESTS], record)
    java_runner_commands(sdk, name, remote, record, expect['engine'])
    result = execute(sdk, name, mvn + ['-Pmissing-artifact', 'test'], remote)
    expect_completed(result, 1, 'absent-artifact')
    assert 'DependencyResolutionException' in result.stdout
    assert 'prefixes: Path corsair/qualification/absent-artifact/0.0.0/absent-artifact-0.0.0.jar NOT allowed from central' in result.stdout
    result = execute(sdk, name, mvn + ['-Dtest=AbsentTest', 'test'], remote)
    expect_completed(result, 1, 'No tests matching pattern')
    setup = execute(sdk, name, ['/bin/sh', '-ec', 'cp -R . /tmp/java-syntax; printf "package corsair; class SyntaxTest { invalid Java; }\\n" > /tmp/java-syntax/src/test/java/corsair/SyntaxTest.java; cp -R . /tmp/java-assertion; printf "%s\\n" "$1" > /tmp/java-assertion/src/test/java/corsair/AssertionTest.java', 'corsair-setup', expect['assertion']], remote)
    expect_completed(setup, 0, '')
    result = execute(sdk, name, mvn + ['test'], '/tmp/java-syntax')
    expect_completed(result, 1, 'COMPILATION ERROR')
    result = execute(sdk, name, mvn + ['test'], '/tmp/java-assertion')
    expect_completed(result, 1, f'Tests run: {len(JAVA_TESTS) + 1}, Failures: 1, Errors: 0, Skipped: 0')
    assert expect['expected'] in result.stdout
    record['offline_diagnostics'] = ['missing-artifact/native-Maven-prefix-resolver', 'no-discovery', 'compilation', 'assertion']


def java_runner_commands(sdk, name, remote, record, engine):
    """The Maven runner's own discovery and execution argv (SPEC-0041) on the fixture, offline in the sandbox."""
    config = MavenRunnerConfig(command=('/usr/share/maven/bin/mvn', '-B', '-ntp', '-o', '-Dmaven.repo.local=/tmp/m2', f'--file={remote}/pom.xml'),
                               workspace_root=remote, java='/opt/java/openjdk/bin/java', console_jar=LAUNCHER)
    runner = MavenRunner(None, None, None, config)
    listing = execute(sdk, name, list(runner._discovery_argv(FIXTURE_IDS)), remote, timeout=120)
    expect_completed(listing, 0, f'[engine:{engine}]')
    found = listed(listing.stdout.encode())
    assert found is not None and sorted(found) == sorted(('corsair.NativeTest', n) for n in JAVA_TESTS), listing.stdout
    report_path = runner._report(FIXTURE_IDS)
    argv = ['/bin/sh', '-c', WRAPPER, 'corsair-maven', report_path, *config.command, *selection(FIXTURE_IDS), 'test']
    result = execute(sdk, name, argv, remote, timeout=120)
    assert result.exit_code == 0, result.stderr[-2000:]
    record.setdefault('native_reports', []).append(native_report(result.stdout, [('corsair.NativeTest', n) for n in JAVA_TESTS]))
    record['runner_commands'] = {'listing': found, 'listing_sha256': hashlib.sha256(listing.stdout.encode()).hexdigest(), 'engine': engine}


def minitest_report(text, expected, summary):
    """Minitest's verbose run is its only native report: every expected test passed once, nothing else ran."""
    lines = [line for line in text.splitlines() if ' = ' in line and '#' in line.split(' = ', 1)[0]]
    assert sorted(line.split(' = ', 1)[0] for line in lines) == sorted(expected)
    assert all(line.endswith(' = .') for line in lines)
    assert text.rstrip().endswith(summary)
    return {'tests': len(lines), 'ids': sorted(expected), 'summary': summary, 'sha256': hashlib.sha256(text.encode()).hexdigest()}


RUBY_DIAGNOSTICS = {
    'missing': 'gem "corsair-qualification-absent-gem", "0.0.0"',
    'syntax': 'require "minitest/autorun"\nclass SyntaxTest < Minitest::Test\n  def test_syntax(\nend\n',
    'assertion': 'require "minitest/autorun"\nclass AssertionTest < Minitest::Test\n  def test_deliberate_failure\n    assert_equal 1, 2\n  end\nend\n',
}


def ruby_offline(sdk, name, remote, record):
    bundle = ['/usr/bin/env', 'BUNDLE_FROZEN=true', '/usr/local/bin/bundle', 'exec', '/usr/local/bin/ruby', '-Itest']
    result = execute(sdk, name, ['/bin/sh', '-ec', '/usr/local/bin/ruby -v; /usr/local/bin/bundle -v; BUNDLE_FROZEN=true /usr/local/bin/bundle exec /usr/local/bin/ruby -e "require %q(minitest); puts Minitest::VERSION"'], remote)
    expect_completed(result, 0, 'ruby 3.1.7')
    assert 'Bundler version 2.3.27' in result.stdout and result.stdout.endswith('5.15.0\n')
    record['versions'] = result.stdout
    result = execute(sdk, name, RUBY_RUN, remote)
    expect_completed(result, 0, RUBY_SUMMARY)
    record.setdefault('native_reports', []).append(minitest_report(result.stdout, ['NativeTest#' + n for n in RUBY_TESTS], RUBY_SUMMARY))
    # Gems the project needs cannot land in the image's GEM_HOME: setup installs them under the workspace.
    expect_permission_denied(execute(sdk, name, ['/usr/bin/touch', '/usr/local/bundle/corsair-probe'], remote))
    setup = execute(sdk, name, ['/bin/sh', '-ec', 'cp -R . /tmp/ruby-missing; printf "%s\\n" "$1" >> /tmp/ruby-missing/Gemfile; printf "%s" "$2" > /tmp/syntax_test.rb; printf "%s" "$3" > /tmp/assertion_test.rb',
                                'corsair-setup', RUBY_DIAGNOSTICS['missing'], RUBY_DIAGNOSTICS['syntax'], RUBY_DIAGNOSTICS['assertion']], remote)
    expect_completed(setup, 0, '')
    result = execute(sdk, name, ['/usr/local/bin/bundle', 'install', '--local'], '/tmp/ruby-missing')
    expect_completed(result, 7, "Could not find gem 'corsair-qualification-absent-gem (= 0.0.0)' in cached gems")
    # Minitest exits 0 when nothing matches; only its summary shows that no test ran.
    result = execute(sdk, name, bundle + ['test/native_test.rb', '-n', 'test_absent'], remote)
    expect_completed(result, 0, '0 runs, 0 assertions, 0 failures, 0 errors, 0 skips')
    result = execute(sdk, name, bundle + ['/tmp/syntax_test.rb'], remote)
    expect_completed(result, 1, "syntax error, unexpected `end'")
    result = execute(sdk, name, bundle + ['/tmp/assertion_test.rb'], remote)
    expect_completed(result, 1, '1 runs, 1 assertions, 1 failures, 0 errors, 0 skips')
    assert 'AssertionTest#test_deliberate_failure' in result.stdout and 'Expected: 1\n  Actual: 2' in result.stdout
    record['offline_diagnostics'] = ['read-only-GEM_HOME', 'missing-gem/bundler-local-resolution', 'no-discovery (exit 0, 0 runs)', 'syntax', 'assertion']


def native_events(logs):
    return [json.loads(line.split('OCSF-JSON ', 1)[1]) for line in logs.splitlines() if 'OCSF-JSON ' in line]


def expect_registry_unavailable(result, events, before, sandbox_id):
    assert result.exit_code == 1
    # CPython before 3.10 names a socket timeout `socket.timeout`; 3.10+ aliases it to TimeoutError.
    assert any(detail in result.stderr for detail in ('http.client.RemoteDisconnected: Remote end closed connection without response', 'TimeoutError: timed out', 'socket.timeout: timed out'))
    address = str(ipaddress.ip_address(result.stdout.strip()))
    assert result.stdout == address + '\n'
    fresh = [e for e in events if e.get('metadata', {}).get('uid') and e['metadata']['uid'] not in before and e.get('container', {}).get('uid') == sandbox_id]
    assert not any(e.get('action_id') == 2 for e in fresh), 'A fresh policy denial cannot qualify unavailable registry'
    failure = [e for e in fresh if e.get('status_id') == 2 and e.get('class_uid') == 4001 and e.get('activity_id') == 4 and e.get('message') == 'Proxy connection error: Connection refused (os error 111)' and e.get('dst_endpoint') == {'ip': address, 'port': 5679}]
    assert failure, 'Missing fresh original-sandbox native upstream connection-refused event'
    return failure


def dependency_policy(endpoint, language='python'):
    policy = toolchain_policy(language)
    wheel = next(w for w in json.loads((SOURCE / language / 'wheels.json').read_text()) if w['name'] == 'six')
    missing = '/simple/corsair-qualification-missing-artifact-1e-0001/'
    local = f'echo.{endpoint.namespace}.svc.cluster.local'
    unavailable = f'unavailable.{endpoint.namespace}.svc.cluster.local'
    policy['network_policies'] = {'dependencies': {'name': 'fixed-native-dependencies', 'binaries': [{'path': PYTHON_TOOLCHAINS[language][0]}], 'endpoints': [
        {'host': 'files.pythonhosted.org', 'port': 443, 'protocol': 'rest', 'enforcement': 'enforce', 'rules': [{'allow': {'method': 'GET', 'path': urlparse(wheel['url']).path}}]},
        {'host': 'pypi.org', 'port': 443, 'protocol': 'rest', 'enforcement': 'enforce', 'rules': [{'allow': {'method': 'GET', 'path': missing}}]},
        {'host': local, 'port': 5678, 'allowed_ips': [endpoint.endpoints['service'] + '/32'], 'protocol': 'rest', 'enforcement': 'enforce', 'rules': [{'allow': {'method': 'GET', 'path': '/**'}}]},
        {'host': unavailable, 'port': 5679, 'allowed_ips': [endpoint.unavailable_address + '/32'], 'protocol': 'rest', 'enforcement': 'enforce', 'rules': [{'allow': {'method': 'GET', 'path': '/**'}}]},
    ]}}
    return policy, wheel, missing, local, unavailable


def python_dependencies(kube, cli, sdk, name, remote, record, endpoint, pair, language='python'):
    python = PYTHON_TOOLCHAINS[language][0]
    prefix = '' if language == 'python' else language + '-'  # keep each image's evidence when both run
    service = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'unavailable'}, 'spec': {'selector': {'app': 'corsair-qualification', 'role': 'echo'}, 'ports': [{'port': 5679, 'targetPort': 5679}]}}
    service_file = kube.evidence / (prefix + 'unavailable-registry.yaml')
    service_file.write_text(yaml.safe_dump(service))
    kube.run('create', '-n', endpoint.namespace, '-f', service_file)
    actual = kube.get('service', 'unavailable', '-n', endpoint.namespace)
    record['unavailable_service_uid'] = actual['metadata']['uid']
    endpoint.unavailable_address = actual['spec']['clusterIP']
    # Both the original Pod and separate Service explicitly refuse connections.
    for address in (endpoint.endpoints['pod'], endpoint.unavailable_address):
        closed = kube.run('exec', '-n', endpoint.namespace, 'probe-allowed', '--', '/usr/bin/curl', '-sS', '--connect-timeout', '5', '--max-time', '10', f'http://{address}:5679/simple/six/', check=False, timeout=20)
        assert closed.returncode == 7 and 'Failed to connect' in closed.stderr
    endpoint.allowed('probe-allowed')
    cli('settings', 'set', name, '--key', 'ocsf_json_enabled', '--value', 'true')
    wait_logging_activation(kube, pair['supervisor'])
    policy, wheel, missing, local, unavailable = dependency_policy(endpoint, language)
    path = kube.evidence / (prefix + 'dependencies-policy.yaml')
    path.write_text(yaml.safe_dump(policy))
    cli('policy', 'set', name, '--policy', str(path), '--wait')
    observe_policy(cli, name, policy, record)
    requirement = f"six @ {wheel['url']} --hash=sha256:{wheel['sha256']}\n"
    execute(sdk, name, [python, '-c', 'from pathlib import Path; Path("cold.txt").write_text(' + repr(requirement) + ')'], remote)
    result = execute(sdk, name, [python, '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check', '--no-cache-dir', '--no-deps', '--require-hashes', '--retries', '0', '--timeout', '10', '--target', remote + '/cold', '-r', 'cold.txt'], remote)
    expect_completed(result, 0, 'Successfully installed six-1.17.0')
    result = execute(sdk, name, [python, '-c', 'import sys; sys.path.insert(0,"cold"); import six; assert six.__version__=="1.17.0"; assert six.__file__.startswith(' + repr(remote + '/cold/') + '); print(six.__version__); print(six.__file__)'], remote)
    expect_completed(result, 0, '1.17.0')
    # Keep native HTTP detail separate from pip's resolver diagnostic.
    request = 'import urllib.request,urllib.error;\ntry:\n r=urllib.request.urlopen(' + repr('https://pypi.org' + missing) + ',timeout=10); print(r.status); print(r.read().decode())\nexcept urllib.error.HTTPError as e:\n print(e.code); print(e.read().decode())'
    result = execute(sdk, name, [python, '-c', request], remote)
    expect_completed(result, 0, '404')
    assert result.stdout.startswith('404\n') and 'policy_denied' not in result.stdout
    result = execute(sdk, name, [python, '-m', 'pip', '--isolated', 'download', '--disable-pip-version-check', '--no-cache-dir', '--no-deps', '--retries', '0', '--timeout', '10', '--index-url', 'https://pypi.org/simple/', '--dest', '/tmp/missing', 'corsair-qualification-missing-artifact-1e-0001==0.0.0'], remote)
    expect_completed(result, 1, 'No matching distribution found')
    assert 'policy_denied' not in result.stdout + result.stderr and 'CERTIFICATE_VERIFY_FAILED' not in result.stdout + result.stderr
    control_request = 'import urllib.request; r=urllib.request.urlopen(' + repr(f'http://{local}:5678/simple/six/') + ',timeout=10); print(r.status); print(r.read().decode())'
    result = execute(sdk, name, [python, '-c', control_request], remote)
    expect_completed(result, 0, 'corsair-network-ok')
    assert result.stdout.startswith('200\n')
    request = request.replace(repr('https://pypi.org' + missing), repr(f'http://{unavailable}:5679/simple/six/'))
    request = 'import socket; print(socket.gethostbyname(' + repr(unavailable) + '),flush=True);\n' + request
    before_logs = kube.run('logs', '-n', 'openshell', pair['supervisor']['metadata']['name'], '--timestamps=true').stdout
    before = {e['metadata']['uid'] for e in native_events(before_logs)}
    try:
        result = execute(sdk, name, [python, '-c', request], remote)
    finally:
        # Export before original supervisor deletion, including failed assertions.
        logs = kube.run('logs', '-n', 'openshell', pair['supervisor']['metadata']['name'], '--timestamps=true').stdout
    failures = expect_registry_unavailable(result, native_events(logs), before, record['sandbox_id'])
    record['dependency_diagnostics'] = {'cold_install': 'six==1.17.0 hash-checked, no-cache, actual import', 'missing_artifact': 'permitted PyPI 404 plus pip resolver failure', 'unavailable_registry': {'host': unavailable, 'port': 5679, 'native_events': failures, 'client_stderr': result.stderr}, 'ordinary_port_control': closed.returncode}



def toolchain_gate(kube, gateway, language):
    """One image's gate, into its own evidence subdirectory; select one image by its test node id."""
    assert not (kube.evidence / 'toolchain.json').exists(), 'Another toolchain gate already wrote this evidence directory'
    sources = ['tests/qualification/test_toolchains.py', 'tests/qualification/prepare_toolchains.py', 'tests/qualification/test_policy.py', 'tests/qualification/test_lifecycle.py', 'tests/qualification/gateway.py', 'tests/qualification/support.py', 'src/corsair/adapters/maven_runner.py', 'src/corsair/reports/junit_listing.py', 'policies/openshell/identity.yaml', 'deploy/runtime-lock.yaml', 'pyproject.toml', 'uv.lock']
    (kube.evidence / 'toolchain-source-hashes.json').write_text(json.dumps(dict(source_hashes(language), **{p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}), indent=2))
    summary = {'outcome': 'failed', 'sandboxes': [], 'internal_retry_counts': 'unknown'}
    endpoint = NetworkFixture(kube, 'toolchain-endpoint')
    attempted = False
    mtls = gateway['mtls']
    with SandboxClient(gateway['endpoint'], tls=TlsConfig(ca_path=mtls / 'ca.crt', cert_path=mtls / 'tls.crt', key_path=mtls / 'tls.key'), timeout=60) as client:
        sdk = SdkReceipts(client, kube.evidence)
        summary['image'] = language
        try:
            summary['global_policy'] = global_policy_observation(gateway['cli']('policy', 'get', '--global', '--full', '-o', 'json', check=False))
            attempted = True
            endpoint.setup()
            image = image_receipt(language)
            record = {'language': language, 'artifact': image}
            summary['sandboxes'].append(record)
            with owned_sandbox(kube, gateway['cli'], sdk, image, toolchain_policy(language), record) as (name, pair):
                remote = stage_project(kube, gateway['cli'], sdk, name, language, record)
                if language in PYTHONS:
                    python_offline(sdk, name, remote, record, language)
                    python_dependencies(kube, gateway['cli'], sdk, name, remote, record, endpoint, pair, language)
                elif language == 'ruby31':
                    ruby_offline(sdk, name, remote, record)
                else:
                    java_offline(sdk, name, remote, record, language)
            assert all(r['outcome'] == 'passed' and r['cleanup_confirmed'] for r in summary['sandboxes'])
            summary['outcome'] = 'passed'
        finally:
            summary['observed_sdk_calls'] = sdk.counter
            try:
                if attempted:
                    endpoint.cleanup()
            finally:
                (kube.evidence / 'toolchain.json').write_text(json.dumps(summary, indent=2))


@pytest.mark.toolchain('java8')
def test_native_java8_toolchain(image_kube, toolchain_gateway):
    toolchain_gate(image_kube, toolchain_gateway, 'java8')


@pytest.mark.toolchain('java')
def test_native_java_toolchain(image_kube, toolchain_gateway):
    toolchain_gate(image_kube, toolchain_gateway, 'java')


@pytest.mark.toolchain('python')
def test_native_python_toolchain(image_kube, toolchain_gateway):
    toolchain_gate(image_kube, toolchain_gateway, 'python')


@pytest.mark.toolchain('python37')
def test_native_python37_toolchain(image_kube, toolchain_gateway):
    """The CPython 3.7 image through the same offline, diagnostic and dependency checks as the 3.12 image."""
    toolchain_gate(image_kube, toolchain_gateway, 'python37')


@pytest.mark.toolchain('ruby31')
def test_native_ruby31_toolchain(image_kube, toolchain_gateway):
    toolchain_gate(image_kube, toolchain_gateway, 'ruby31')
