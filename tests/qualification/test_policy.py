"""Bounded native 1D policy matrix, using operator canaries and a controlled endpoint."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
import xml.etree.ElementTree as ET

from openshell import SandboxClient, TlsConfig, DeletionOutcome
from openshell._proto import openshell_pb2
import pytest
import yaml

from tests.qualification.gateway import gateway, inspect_identity, workspace_storage, wait_resource_absent
from tests.qualification.prepare_policy_image import image_receipt
from tests.qualification.support import ROOT, NetworkFixture, require_owned_cluster
from tests.qualification.test_lifecycle import SdkReceipts


def require_network(kube, path):
    assert path, 'Policy qualification requires explicit successful CNI evidence'
    prior = Path(path).resolve()
    assert prior.is_relative_to(ROOT / '.runs')
    assert json.loads((prior / 'scope.json').read_text())['node_uid'] == require_owned_cluster(kube)['metadata']['uid']
    assert (prior / 'runtime-lock.yaml').read_bytes() == (ROOT / 'deploy/runtime-lock.yaml').read_bytes()
    suite = ET.parse(prior / 'junit.xml').getroot().find('testsuite')
    assert suite is not None and suite.attrib['tests'] == '3'
    assert all(suite.attrib[k] == '0' for k in ('errors', 'failures', 'skipped'))
    for scenario in ('test_ingress_selection_and_rollback', 'test_egress_denial_and_narrow_allow'):
        assert json.loads((prior / scenario / 'cleanup.json').read_text())['confirmed'] is True
        assert json.loads((prior / scenario / 'service-readiness.json').read_text())['ready'] is True


@pytest.fixture
def policy_gateway(kube, request):
    require_network(kube, request.config.getoption('--network-evidence'))
    return request.getfixturevalue('gateway')


def fixture_policy(control, hostname=None, address=None, methods=('GET', 'POST')):
    policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    policy['filesystem_policy']['read_only'].append('/opt/corsair-curl')
    if control:
        policy['filesystem_policy']['read_write'] += ['/opt/corsair-denied', '/opt/corsair-readonly']
    else:
        policy['filesystem_policy']['read_only'] += ['/opt/corsair-readonly']
    if hostname:
        policy['network_policies'] = {'fixture': {
            'name': 'corsair-fixture', 'binaries': [{'path': '/usr/bin/curl'}],
            'endpoints': [{'host': hostname, 'port': 5678, 'allowed_ips': [address + '/32'],
                           'protocol': 'rest', 'enforcement': 'enforce',
                           'rules': [{'allow': {'method': m, 'path': '/**'}} for m in methods]}]}}
    return policy


def assert_effective(actual, expected):
    assert actual['landlock'] == expected['landlock'] == {'compatibility': 'hard_requirement'}
    assert actual['filesystem_policy'] == expected['filesystem_policy']
    assert actual.get('network_policies', {}) == expected['network_policies'], 'Effective network authority differs'
    assert set(actual) <= {'version', 'landlock', 'filesystem_policy', 'process', 'network_policies'}
    assert actual['version'] == expected['version'] == 1


def global_policy_observation(result):
    if result.returncode == 0:
        return {'state': 'present', 'native': json.loads(result.stdout)}
    normalized = ' '.join(result.stderr.replace('│', ' ').split())
    assert result.returncode == 1 and 'Some requested entity was not found' in normalized
    assert 'no global policy revision found' in normalized and not result.stdout.strip()
    return {'state': 'absent', 'native_error': result.stderr, 'exit_code': result.returncode}


def observe_policy(cli, name, policy, record):
    actual = json.loads(cli('sandbox', 'get', name, '-o', 'json').stdout)
    full = json.loads(cli('policy', 'get', name, '--full', '-o', 'json').stdout)
    base = json.loads(cli('policy', 'get', name, '--base', '-o', 'json').stdout)
    assert actual['id'] == record['sandbox_id'] and actual['policy_source'] == 'sandbox'
    assert actual['configuration_admission']['state'] == 'accepted'
    assert_effective(actual['policy'], policy)
    assert_effective(full['policy'], policy)
    assert base['policy'] == full['policy'] and base['hash'] == full['hash']
    assert full['hash'] == actual['configuration_admission']['policy_hash']
    assert not json.loads(cli('sandbox', 'provider', 'list', name, '-o', 'json').stdout)['providers']
    revision = json.loads(cli('policy', 'get', name, '--rev', str(full['version']), '--full', '-o', 'json').stdout)
    assert revision['status'] == 'loaded' and revision['hash'] == full['hash']
    record.setdefault('policy_observations', []).append({'actual': actual['configuration_admission'], 'full': full, 'revision': revision})
    return actual


@contextmanager
def owned_sandbox(kube, cli, sdk, image, policy, record):
    name = record['name'] = 'policy-' + uuid.uuid4().hex[:11]
    record.update(outcome='failed', cleanup_confirmed=False, create_delivery='unknown')
    policy_file = kube.evidence / (name + '.yaml')
    policy_file.write_text(yaml.safe_dump(policy))
    resources = []
    sandbox_id = None
    started = time.monotonic()
    try:
        result = cli('sandbox', 'create', '--name', name, '--from', image['image'], '--policy', str(policy_file), '--cpu', '1', '--memory', '512Mi', '--no-auto-providers', '--detach', '--no-tty', '-o', 'json', '--', '/bin/sleep', '600', check=False, timeout=180)
        record.update(create_delivery='completed', create_exit=result.returncode)
        assert result.returncode == 0, result.stderr
        sandbox_id = record['sandbox_id'] = json.loads(result.stdout)['id']
        actual = json.loads(cli('sandbox', 'get', name, '-o', 'json').stdout)
        assert actual['id'] == sandbox_id, 'Original native create identity changed'
        ready = sdk.call('wait_ready', name, workspace='default', timeout_seconds=120)
        assert ready.id == sandbox_id and ready.phase == openshell_pb2.SANDBOX_PHASE_READY
        pair = inspect_identity(kube, actual, record, expected_image=image['image'])
        cr = kube.get('sandboxes', '-n', 'openshell')['items'][0]
        resources = [('sandbox', cr['metadata']['name'], cr['metadata']['uid'])] + [('pod', p['metadata']['name'], p['metadata']['uid']) for p in pair.values()]
        record['resources'] = resources
        record['workspace_storage'] = workspace_storage(kube, pair, record['sandbox_uid'])
        agent = next(c for c in pair['workload']['status']['containerStatuses'] if c['name'] == 'agent')
        assert agent['imageID'].endswith(image['manifest_digest']), 'Running workload artifact differs'
        record['image_id'] = agent['imageID']
        observe_policy(cli, name, policy, record)
        yield name, pair
        record['outcome'] = 'passed'
    finally:
        try:
            if sandbox_id:
                assert sdk.call('get', name, workspace='default').id == sandbox_id, 'Replacement: refusing delete'
                deletion = sdk.call('delete', name, workspace='default')
                assert deletion.sandbox_id == sandbox_id and deletion.outcome in (DeletionOutcome.COMPLETED, DeletionOutcome.ACCEPTED)
                sdk.call('wait_deleted', name, workspace='default', expected_sandbox_id=sandbox_id, timeout_seconds=90)
                assert sdk.call('list_all', workspace='default') == []
                for resource, resource_name, uid in resources:
                    wait_resource_absent(kube, resource, resource_name, uid)
                for resource, identity in record.get('workspace_storage', {}).items():
                    wait_resource_absent(kube, resource, identity['name'], identity['uid'], namespace=None if resource == 'pv' else 'openshell')
                record['cleanup_confirmed'] = len(resources) == 3 and bool(record.get('workspace_storage'))
        finally:
            record['elapsed_seconds'] = time.monotonic() - started
            (kube.evidence / (name + '.json')).write_text(json.dumps(record, indent=2))


def run_exec(sdk, name, argv):
    return sdk.call('exec', name, argv, workspace='default', no_login_shell=True, timeout_seconds=20)


def expect_permission_denied(result):
    assert result.exit_code in (1, 2) and result.stdout == ''
    assert 'Permission denied' in result.stderr and 'No such file' not in result.stderr


def request(sdk, name, address, method, direct=False):
    marker = 'policy-' + uuid.uuid4().hex
    args = ['/usr/bin/curl', '--silent', '--show-error', '--connect-timeout', '2', '--max-time', '5', '--request', method, '--write-out', '\nSTATUS:%{http_code}']
    if direct:
        args += ['--noproxy', '*']
    result = run_exec(sdk, name, args + [f'http://{address}:5678/{marker}'])
    return result, marker


def expect_http_control(result):
    assert (result.exit_code, result.stdout, result.stderr) == (0, 'corsair-network-ok\n\nSTATUS:200', '')


def expect_method_denial(result):
    assert result.exit_code == 0 and result.stderr == '' and result.stdout.endswith('\nSTATUS:403')
    body = json.loads(result.stdout.removesuffix('\nSTATUS:403'))
    assert body['error'] == 'policy_denied', body


def expect_endpoint_denial(result):
    # Kubernetes native transparent mediation returns EACCES to connect(),
    # rather than exposing an explicit CONNECT proxy's HTTP response.
    # This client result is provisional until a new matching OCSF policy event.
    assert result.exit_code == 7 and result.stdout == '\nSTATUS:000'
    assert 'Failed to connect' in result.stderr


def policy_denial_events(logs, address):
    events = []
    for line in logs.splitlines():
        if 'OCSF-JSON ' not in line:
            continue
        event = json.loads(line.split('OCSF-JSON ', 1)[1])
        destination = event.get('dst_endpoint', {})
        if (event.get('action_id') == 2 and event.get('status_detail') == 'transparent_tcp_policy_denied'
                and destination.get('port') == 5678 and address in (destination.get('domain'), destination.get('ip'))
                and event.get('actor', {}).get('process', {}).get('name') == '/usr/bin/curl'):
            events.append(event)
    return events


def workload_fence(policies):
    selected = [p for p in policies if p['spec']['podSelector'].get('matchLabels', {}).get('openshell.ai/boundary-role') == 'workload']
    assert len(selected) == 1
    spec = selected[0]['spec']
    # Kubernetes omits empty arrays; Egress isolation with no rules denies all.
    assert spec.get('egress', []) == [] and set(spec['policyTypes']) == {'Ingress', 'Egress'}
    return selected[0]


def logging_activation_observed(logs):
    change = re.search(r'Setting changed \[key:ocsf_json_enabled old:[^\]\n]+ new:true\]', logs)
    return change is not None and 'OCSF JSONL logging toggled' in logs[change.end():]


def wait_logging_activation(kube, supervisor):
    # settings set acknowledges storage; the native supervisor polls settings.
    # Admission observes its atomic logger toggle before sending probe traffic.
    started = time.monotonic()
    deadline = started + 30
    receipt = {'supervisor_uid': supervisor['metadata']['uid'], 'ready': False, 'budget_seconds': 30, 'attempts': []}
    try:
        while time.monotonic() < deadline:
            logs = kube.run('logs', '-n', 'openshell', supervisor['metadata']['name'], '-c', supervisor['spec']['containers'][0]['name'], timeout=min(10, deadline - time.monotonic())).stdout
            receipt['attempts'].append(f'command-{kube.counter:04d}.json')
            if logging_activation_observed(logs):
                receipt['ready'] = True
                return
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        raise AssertionError('Native JSON logging activation unconfirmed; policy probes not admitted')
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - started
        (kube.evidence / 'logging-readiness.json').write_text(json.dumps(receipt, indent=2))


@pytest.mark.policy
def test_native_policy_boundaries(kube, policy_gateway):
    image = image_receipt()
    source_paths = ['tests/qualification/test_policy.py', 'tests/qualification/prepare_policy_image.py', 'tests/qualification/gateway.py', 'tests/qualification/support.py', 'deploy/qualification/policy-image/Dockerfile', 'policies/openshell/identity.yaml', 'deploy/runtime-lock.yaml']
    (kube.evidence / 'policy-source-hashes.json').write_text(json.dumps({p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}, indent=2))
    summary = {'outcome': 'failed', 'image': image, 'sandboxes': [], 'requests': [], 'internal_retry_counts': 'unknown'}
    cli = policy_gateway['cli']
    endpoint = NetworkFixture(kube, 'policy-endpoint')
    mtls = policy_gateway['mtls']
    with SandboxClient(policy_gateway['endpoint'], tls=TlsConfig(ca_path=mtls / 'ca.crt', cert_path=mtls / 'tls.crt', key_path=mtls / 'tls.key'), timeout=60) as client:
        sdk = SdkReceipts(client, kube.evidence)
        fixture_attempted = False
        try:
            summary['global_policy'] = global_policy_observation(cli('policy', 'get', '--global', '--full', '-o', 'json', check=False))
            fixture_attempted = True
            endpoint.setup()
            endpoint.allowed('probe-allowed')
            hostname = f'echo.{endpoint.namespace}.svc.cluster.local'
            control = {}
            summary['sandboxes'].append(control)
            with owned_sandbox(kube, cli, sdk, image, fixture_policy(True), control) as (name, pair):
                result = run_exec(sdk, name, ['/bin/sh', '-ec', 'cat /opt/corsair-denied/readable; cat /opt/corsair-readonly/writable; printf "policy-control-write\\n" > /opt/corsair-readonly/writable; cat /opt/corsair-readonly/writable; stat -c "%a %u %g" /opt/corsair-denied/readable /opt/corsair-readonly/writable; test -x /usr/bin/curl; readlink -f /usr/bin/curl'])
                assert (result.exit_code, result.stdout, result.stderr) == (0, 'corsair-readable-canary\ncorsair-writable-canary\npolicy-control-write\n444 0 0\n666 0 0\n/usr/bin/curl\n', '')
            restricted = {}
            summary['sandboxes'].append(restricted)
            policy = fixture_policy(False, hostname, endpoint.endpoints['service'])
            with owned_sandbox(kube, cli, sdk, image, policy, restricted) as (name, pair):
                cli('settings', 'set', name, '--key', 'ocsf_json_enabled', '--value', 'true')
                wait_logging_activation(kube, pair['supervisor'])
                result = run_exec(sdk, name, ['/bin/sh', '-ec', 'printf "scratch-ok\\n" > /tmp/policy-scratch; cat /tmp/policy-scratch; cat /opt/corsair-readonly/writable; ln -s /opt/corsair-denied/readable /tmp/policy-symlink'])
                assert (result.exit_code, result.stdout, result.stderr) == (0, 'scratch-ok\ncorsair-writable-canary\n', '')
                for command in (['/bin/cat', '/opt/corsair-denied/readable'], ['/bin/cat', '/tmp/policy-symlink'], ['/bin/sh', '-c', 'printf "blocked\\n" > /opt/corsair-readonly/writable']):
                    expect_permission_denied(run_exec(sdk, name, command))
                result = run_exec(sdk, name, ['/bin/cat', '/opt/corsair-readonly/writable'])
                assert (result.exit_code, result.stdout, result.stderr) == (0, 'corsair-writable-canary\n', '')
                positive, negative = [], []
                supervisor = pair['supervisor']
                def native_logs():
                    return kube.run('logs', '-n', 'openshell', supervisor['metadata']['name'], '-c', supervisor['spec']['containers'][0]['name']).stdout
                def attempt(address, method, expected, direct=False):
                    before = len(policy_denial_events(native_logs(), address)) if expected is expect_endpoint_denial else 0
                    result, marker = request(sdk, name, address, method, direct)
                    observation = {'marker': marker, 'address': address, 'method': method, 'direct': direct, 'sdk_receipt': f'sdk-{sdk.counter:04d}.json', 'expected': expected.__name__}
                    summary['requests'].append(observation)
                    expected(result)
                    if expected is expect_endpoint_denial:
                        deadline = time.monotonic() + 10
                        while True:
                            events = policy_denial_events(native_logs(), address)
                            if len(events) > before:
                                observation['native_policy_denials'] = events[before:]
                                break
                            assert time.monotonic() < deadline, 'Client failure lacks a new matching native policy denial'
                            time.sleep(0.2)
                    (positive if expected is expect_http_control else negative).append(marker)
                for method in ('GET', 'POST'):
                    attempt(hostname, method, expect_http_control)
                assert all(m in endpoint.logs() for m in positive), 'Initial policy control log coverage missing'
                # IP authority differs from the admitted DNS hostname; direct socket mediation stays native.
                attempt(endpoint.endpoints['service'], 'GET', expect_endpoint_denial)
                attempt(endpoint.endpoints['service'], 'GET', expect_endpoint_denial, direct=True)
                narrowed = fixture_policy(False, hostname, endpoint.endpoints['service'], methods=('GET',))
                path = kube.evidence / 'policy-get-only.yaml'
                path.write_text(yaml.safe_dump(narrowed))
                cli('policy', 'set', name, '--policy', str(path), '--wait', '--timeout', '30')
                observe_policy(cli, name, narrowed, restricted)
                for _ in range(3):
                    endpoint.allowed('probe-allowed')
                    attempt(hostname, 'GET', expect_http_control)
                    attempt(hostname, 'POST', expect_method_denial)
                absent = fixture_policy(False)
                path = kube.evidence / 'policy-no-endpoint.yaml'
                path.write_text(yaml.safe_dump(absent))
                cli('policy', 'set', name, '--policy', str(path), '--wait', '--timeout', '30')
                observe_policy(cli, name, absent, restricted)
                for _ in range(3):
                    endpoint.allowed('probe-allowed')
                    attempt(hostname, 'GET', expect_endpoint_denial)
                policies = kube.get('networkpolicies', '-n', 'openshell')['items']
                restricted['workload_networkpolicy'] = workload_fence(policies)
                # Trusted operator diagnostic independently probes outer CNI; never a workload exec fallback.
                for address in endpoint.endpoints.values():
                    endpoint.allowed('probe-allowed')
                    marker = 'direct-' + uuid.uuid4().hex
                    direct = kube.run('exec', '-n', 'openshell', pair['workload']['metadata']['name'], '-c', 'agent', '--', '/usr/bin/curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '3', f'http://{address}:5678/{marker}', check=False)
                    assert direct.returncode == 28 and direct.stdout == ''
                    negative.append(marker)
                endpoint.allowed('probe-allowed')
                logs = endpoint.logs()
                assert all(m in logs for m in positive) and not any(m in logs for m in negative), 'Denied marker reached upstream or positive coverage missing'
                restricted.update(positive_markers=positive, denied_markers=negative)
                cli('logs', name, '--source', 'sandbox', '-n', '1000')
            assert all(r['outcome'] == 'passed' and r['cleanup_confirmed'] for r in summary['sandboxes'])
            summary['outcome'] = 'passed'
        finally:
            try:
                if fixture_attempted:
                    endpoint.cleanup()
            finally:
                summary['observed_sdk_calls'] = sdk.counter
                (kube.evidence / 'policy.json').write_text(json.dumps(summary, indent=2))
