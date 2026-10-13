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
from tests.qualification.gateway import gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_policy import require_network, owned_sandbox, observe_policy, global_policy_observation, wait_logging_activation
from tests.qualification.prepare_toolchains import JAVA_TESTS, JEST, LAUNCHER, NODE_TESTS, NODES, NPM, PYTHONS, SOURCE, image_receipt, jest_report, source_hashes
from corsair.adapters.maven_runner import WRAPPER, MavenRunner, MavenRunnerConfig, selection
from corsair.reports.junit_listing import listed


@pytest.fixture
def kube(kube, request):
    """Per-image evidence: each gate (and its gateway fixture) writes under `<evidence>/<test name>/`, so one run
    of all toolchain gates keeps every image's receipts apart."""
    view = copy.copy(kube)
    view.evidence = kube.evidence / request.node.name
    view.evidence.mkdir(mode=0o700)
    return view


# Exact interpreter and pytest each Python toolchain image carries (its requirements.txt pins).
PYTHON_TOOLCHAINS = {'python': ('/usr/local/bin/python3.12', (3, 12), '9.0.3'),
                     'python37': ('/usr/local/bin/python3.7', (3, 7), '7.4.4')}


@pytest.fixture
def toolchain_gateway(kube, request):
    require_network(kube, request.config.getoption('--network-evidence'))
    return request.getfixturevalue('gateway')


def toolchain_policy(language):
    policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    policy['filesystem_policy']['read_only'] += ['/opt/corsair-fixture'] + ([] if language in PYTHONS else
        # Node 8's Debian buster base is not merged-/usr: its loader is under /lib64; Yarn is unpacked under /opt.
        ['/lib64', '/opt/corsair-npm', '/opt/yarn-v1.21.1'] if language in NODES else
        ['/opt/java/openjdk', '/opt/corsair-m2', '/opt/corsair-m2.sha256', '/opt/corsair-junit', '/opt/corsair-junit.sha256'])
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
    elif language in NODES:
        for file in ('package.json', 'package-lock.json', 'native.test.js'):
            shutil.copyfile(SOURCE / language / file, project / file)
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


# Exact runtime, package managers and Jest each Node toolchain image carries (upstream image and fixture lockfile).
NODE_TOOLCHAINS = {'node8': {'versions': 'v8.17.0\n6.13.4\n1.21.1\n24.8.0\n', 'yarn': '/opt/yarn-v1.21.1/bin/yarn.js'}}


def node_offline(sdk, name, remote, record, language):
    expect = NODE_TOOLCHAINS[language]
    node, npm = NPM[0], [*NPM, '--cache', '/tmp/npm']
    # The fixture's own lockfile, installed offline from the image cache: npm checks each tarball's SHA-512 again.
    result = execute(sdk, name, ['/bin/sh', '-ec', 'cp -R /opt/corsair-npm /tmp/npm'], remote)
    expect_completed(result, 0, '')
    result = execute(sdk, name, [*npm, 'ci', '--offline'], remote, timeout=120)
    expect_completed(result, 0, 'added ')
    result = execute(sdk, name, ['/bin/sh', '-ec', f'{node} --version; {node} {NPM[1]} --version; {node} {expect["yarn"]} --version; {node} node_modules/jest/bin/jest.js --version'], remote)
    expect_completed(result, 0, '')
    assert result.stdout == expect['versions'], result.stdout
    record['versions'] = result.stdout
    result = execute(sdk, name, [*JEST, '--json', f'--outputFile={remote}/passed.json'], remote, timeout=120)
    expect_completed(result, 0, f'Tests:       {len(NODE_TESTS)} passed, {len(NODE_TESTS)} total')
    passed = execute(sdk, name, ['/bin/cat', remote + '/passed.json'], '/tmp')
    assert passed.exit_code == 0 and passed.stderr == ''
    record.setdefault('native_reports', []).append(jest_report(passed.stdout, NODE_TESTS))
    result = execute(sdk, name, [*npm, 'install', '--offline', '--no-save', 'corsair-qualification-missing-artifact-1e-0001@0.0.0'], remote)
    expect_completed(result, 1, 'ENOTCACHED')
    result = execute(sdk, name, [*JEST, 'corsair-absent-pattern'], remote)
    expect_completed(result, 1, 'No tests found')
    setup = execute(sdk, name, ['/bin/sh', '-ec', 'cp -R . /tmp/node-syntax; printf "test(\'syntax\', () => { invalid JavaScript; });\\n" > /tmp/node-syntax/syntax.test.js; cp -R . /tmp/node-assertion; printf "test(\'deliberate failure\', () => { expect(1).toBe(2); });\\n" > /tmp/node-assertion/assertion.test.js'], remote)
    expect_completed(setup, 0, '')
    result = execute(sdk, name, list(JEST), '/tmp/node-syntax', timeout=120)
    expect_completed(result, 1, 'Test suite failed to run')
    assert 'SyntaxError' in result.stderr
    result = execute(sdk, name, list(JEST), '/tmp/node-assertion', timeout=120)
    expect_completed(result, 1, f'Tests:       1 failed, {len(NODE_TESTS)} passed, {len(NODE_TESTS) + 1} total')
    assert 'Expected: 2' in result.stderr and 'Received: 1' in result.stderr
    record['offline_diagnostics'] = ['missing-package/npm-offline-cache', 'no-discovery', 'syntax/suite', 'assertion']


# One small dependency-free package, pinned by the registry's SHA-512 as a project lockfile pins it.
COLD_PACKAGE = {'name': 'is-number', 'version': '7.0.0', 'resolved': 'https://registry.npmjs.org/is-number/-/is-number-7.0.0.tgz',
                'integrity': 'sha512-41Cifkg6e8TylSpdtTpeLVMqvSBEVzTttHvERD741+pnZ8ANv0004MRL43QKPDlK9cGvNp6NZWZUBlbGXYxxng=='}
MISSING_PACKAGE = 'corsair-qualification-missing-artifact-1e-0001'


def node_dependencies(kube, cli, sdk, name, remote, record, language):
    """A project's registry install at setup: npm through the sandbox policy to registry.npmjs.org (SPEC-0026)."""
    policy = toolchain_policy(language)
    policy['network_policies'] = {'dependencies': {'name': 'fixed-native-dependencies', 'binaries': [{'path': NPM[0]}], 'endpoints': [
        {'host': 'registry.npmjs.org', 'port': 443, 'protocol': 'rest', 'enforcement': 'enforce', 'rules': [
            {'allow': {'method': 'GET', 'path': urlparse(COLD_PACKAGE['resolved']).path}}, {'allow': {'method': 'GET', 'path': '/' + MISSING_PACKAGE}}]},
    ]}}
    path = kube.evidence / (language + '-dependencies-policy.yaml')
    path.write_text(yaml.safe_dump(policy))
    cli('policy', 'set', name, '--policy', str(path), '--wait')
    observe_policy(cli, name, policy, record)
    package = {'name': 'corsair-cold', 'version': '0.0.0', 'private': True, 'dependencies': {COLD_PACKAGE['name']: COLD_PACKAGE['version']}}
    lock = {'name': 'corsair-cold', 'version': '0.0.0', 'lockfileVersion': 1, 'requires': True,
            'dependencies': {COLD_PACKAGE['name']: {k: COLD_PACKAGE[k] for k in ('version', 'resolved', 'integrity')}}}
    write = f"const fs=require('fs'); fs.mkdirSync('/tmp/cold'); fs.writeFileSync('/tmp/cold/package.json', {json.dumps(json.dumps(package))}); fs.writeFileSync('/tmp/cold/package-lock.json', {json.dumps(json.dumps(lock))});"
    result = execute(sdk, name, [NPM[0], '-e', write], remote)
    expect_completed(result, 0, '')
    npm = [*NPM, '--cache', '/tmp/npm-cold', '--fetch-retries=0', '--fetch-timeout=10000']
    result = execute(sdk, name, [*npm, 'ci'], '/tmp/cold', timeout=120)
    expect_completed(result, 0, 'added 1 packages')
    result = execute(sdk, name, [NPM[0], '-e', "const p=require('/tmp/cold/node_modules/is-number/package.json'); console.log(p.version); console.log(require.resolve('is-number', {paths: ['/tmp/cold']}))"], remote)
    expect_completed(result, 0, '7.0.0')
    assert result.stdout == '7.0.0\n/tmp/cold/node_modules/is-number/index.js\n'
    result = execute(sdk, name, [*npm, 'install', '--no-save', '--no-package-lock', '--prefix', '/tmp/missing', MISSING_PACKAGE + '@0.0.0'], remote, timeout=120)
    expect_completed(result, 1, 'E404')
    assert '404 Not Found - GET https://registry.npmjs.org/' + MISSING_PACKAGE in result.stderr
    assert 'policy_denied' not in result.stdout + result.stderr and 'UNABLE_TO_VERIFY_LEAF_SIGNATURE' not in result.stdout + result.stderr and 'SELF_SIGNED' not in result.stdout + result.stderr
    record['dependency_diagnostics'] = {'cold_install': 'is-number@7.0.0 lockfile SHA-512, npm ci from registry.npmjs.org, actual require',
                                        'missing_package': 'permitted registry 404 through npm (E404), not a policy denial'}


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
    """One image's gate, into its own evidence subdirectory; `--toolchain <dir>` (`TOOLCHAINS=<dir>`) selects one image."""
    assert not (kube.evidence / 'toolchain.json').exists(), 'Another toolchain gate already wrote this evidence; run one image per run'
    sources = ['tests/qualification/test_toolchains.py', 'tests/qualification/prepare_toolchains.py', 'tests/qualification/test_policy.py', 'tests/qualification/test_lifecycle.py', 'tests/qualification/gateway.py', 'tests/qualification/support.py', 'src/corsair/adapters/maven_runner.py', 'src/corsair/reports/junit_listing.py', 'policies/openshell/identity.yaml', 'deploy/runtime-lock.yaml', 'pyproject.toml', 'uv.lock']
    (kube.evidence / 'toolchain-source-hashes.json').write_text(json.dumps(dict(source_hashes(), **{p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}), indent=2))
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
                elif language in NODES:
                    node_offline(sdk, name, remote, record, language)
                    node_dependencies(kube, gateway['cli'], sdk, name, remote, record, language)
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
def test_native_java8_toolchain(kube, toolchain_gateway):
    toolchain_gate(kube, toolchain_gateway, 'java8')


@pytest.mark.toolchain('java')
def test_native_java_toolchain(kube, toolchain_gateway):
    toolchain_gate(kube, toolchain_gateway, 'java')


@pytest.mark.toolchain('node8')
def test_native_node8_toolchain(kube, toolchain_gateway):
    toolchain_gate(kube, toolchain_gateway, 'node8')


@pytest.mark.toolchain('python37')
def test_native_python37_toolchain(kube, toolchain_gateway):
    toolchain_gate(kube, toolchain_gateway, 'python37')


@pytest.mark.toolchain('python')
def test_native_python_toolchain(kube, toolchain_gateway):
    toolchain_gate(kube, toolchain_gateway, 'python')
