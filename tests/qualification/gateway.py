"""Bounded native gateway/identity probes; no Corsair sandbox adapter."""
import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
import uuid

import pytest
import yaml

from deploy.openshell.artifacts import TOOLS, verify
from tests.qualification.install_gateway import STATE, require_admission
from tests.qualification.support import ROOT, LOCK


def export_client(kube, mtls):
    """Private native Secret export; receipts never contain credential bytes."""
    mtls.mkdir(parents=True)
    for key, filename in [('ca.crt', 'ca.crt'), ('tls.crt', 'tls.crt'), ('tls.key', 'tls.key')]:
        argv = kube.argv + ['get', 'secret', 'openshell-client-tls', '-n', 'openshell', '-o', 'jsonpath={.data.' + key.replace('.', '\\.') + '}']
        receipt = {'argv': argv, 'credential_output_withheld': True, 'completion': 'unknown'}
        started = time.monotonic()
        try:
            result = subprocess.run(argv, capture_output=True, timeout=30)
            receipt.update(exit_code=result.returncode, completion='completed')
            assert result.returncode == 0, 'Private credential export failed; output withheld'
            data = base64.b64decode(result.stdout, validate=True)
            assert data, 'Empty transport credential'
            target = mtls / filename
            target.write_bytes(data)
            target.chmod(0o600)
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - started
            (kube.evidence / ('private-export-' + filename + '.json')).write_text(json.dumps(receipt, indent=2))


def wait_pair(kube):
    deadline = time.monotonic() + 120
    while True:
        pods = kube.get('pods', '-n', 'openshell')['items']
        selected = [p for p in pods if p['metadata'].get('labels', {}).get('openshell.ai/boundary-role') in ('workload', 'supervisor')]
        assert len(selected) <= 2, 'Ambiguous native workload/supervisor pair'
        pair = {p['metadata']['labels']['openshell.ai/boundary-role']: p for p in selected}
        if len(pair) == 2 and all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in p.get('status', {}).get('conditions', [])) for p in pair.values()):
            return pair
        assert time.monotonic() < deadline, 'Generated pair readiness unavailable'
        time.sleep(2)


def inspect_identity(kube, actual, summary, expected_image=None):
    pair = wait_pair(kube)
    crs = kube.get('sandboxes', '-n', 'openshell')['items']
    assert len(crs) == 1
    cr = crs[0]
    summary['sandbox_uid'] = cr['metadata']['uid']
    assert actual['phase'] == 'Ready' and actual['configuration_admission']['state'] == 'accepted'
    assert actual['annotations']['internal.openshell.ai/compute-runtime-identity'] == f"kubernetes://openshell/{cr['metadata']['uid']}/{pair['supervisor']['metadata']['uid']}"
    summary['configuration_admission'] = actual['configuration_admission']
    for pod in pair.values():
        assert any(o['uid'] == cr['metadata']['uid'] and o['kind'] == 'Sandbox' for o in pod['metadata']['ownerReferences'])
    for role, pod in pair.items():
        spec = pod['spec']
        assert spec['automountServiceAccountToken'] is False
        assert all(not spec.get(key) for key in ('hostPID', 'hostIPC', 'hostNetwork', 'shareProcessNamespace'))
        assert spec['securityContext']['seccompProfile']['type'] == 'RuntimeDefault'
        assert not any('hostPath' in v for v in spec['volumes'])
        for container in spec.get('initContainers', []) + spec['containers']:
            security = container['securityContext']
            assert security.get('runAsUser', spec['securityContext'].get('runAsUser')) == 10001
            assert security.get('runAsGroup', spec['securityContext'].get('runAsGroup')) == 10001
            assert security.get('runAsNonRoot', spec['securityContext'].get('runAsNonRoot')) is True
            assert not security.get('privileged')
            assert security.get('seccompProfile', spec['securityContext']['seccompProfile']) == {'type': 'RuntimeDefault'}
            assert container['securityContext']['allowPrivilegeEscalation'] is False
            assert container['securityContext']['capabilities'] == {'drop': ['ALL']}
        summary[role + '_pod_uid'] = pod['metadata']['uid']
    workload, supervisor = pair['workload']['spec'], pair['supervisor']['spec']
    assert workload['containers'][0]['image'] == (expected_image or LOCK['openshell']['images']['workload'])
    assert supervisor['containers'][0]['image'] == LOCK['openshell']['images']['supervisor']
    tokens = [s['serviceAccountToken'] for v in supervisor['volumes'] for s in v.get('projected', {}).get('sources', []) if 'serviceAccountToken' in s]
    assert len(tokens) == 1 and tokens[0]['audience'] == 'openshell-gateway'
    assert not any('serviceAccountToken' in s for v in workload['volumes'] for s in v.get('projected', {}).get('sources', []))
    workload_volumes = {v['name']: v for v in workload['volumes']}
    assert workload['securityContext']['supplementalGroupsPolicy'] == 'Strict'
    assert all(c['image'] in (LOCK['openshell']['images']['runtime'], expected_image or LOCK['openshell']['images']['workload']) for c in workload['initContainers'])
    assert workload_volumes['openshell-runtime']['emptyDir']['medium'] == 'Memory'
    assert workload_volumes['openshell-runtime-state']['emptyDir']['medium'] == 'Memory'
    assert all('secret' not in workload_volumes[m['name']] for c in workload['containers'] for m in c.get('volumeMounts', [])), 'Workload container has Secret mount'
    assert not any(c.get('envFrom') or any('secretKeyRef' in e.get('valueFrom', {}) for e in c.get('env', [])) for c in workload['containers'])
    tls_volume = next(v['secret'] for v in supervisor['volumes'] if v.get('secret', {}).get('secretName') == 'openshell-client-tls')
    assert tls_volume['items'] == [{'key': 'ca.crt', 'path': 'ca.crt'}]
    kube.run('exec', '-n', 'openshell', pair['workload']['metadata']['name'], '-c', 'agent', '--', '/bin/sh', '-ec', 'test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token; test ! -e /var/run/secrets/openshell/token; test ! -e /.openshell/bootstrap-input')
    return pair


def wait_resource_absent(kube, resource, name, uid, namespace='openshell'):
    deadline = time.monotonic() + 120
    while True:
        scope = ['-n', namespace] if namespace else []
        remaining = kube.run('get', resource, name, *scope, '--ignore-not-found', '-o', 'json').stdout
        if not remaining.strip():
            return
        assert json.loads(remaining)['metadata']['uid'] == uid, 'Resource identity replaced; refusing cleanup claim'
        assert time.monotonic() < deadline, 'Native resource deletion unconfirmed'
        time.sleep(1)



def workspace_storage(kube, pair, sandbox_uid):
    claim_name = next(v['persistentVolumeClaim']['claimName'] for v in pair['workload']['spec']['volumes'] if v['name'] == 'workspace')
    claim = kube.get('pvc', claim_name, '-n', 'openshell')
    assert any(o['uid'] == sandbox_uid for o in claim['metadata']['ownerReferences'])
    assert claim['spec']['storageClassName'] == LOCK['storage']['storage_class']
    pv = kube.get('pv', claim['spec']['volumeName'])
    assert pv['spec']['claimRef']['uid'] == claim['metadata']['uid']
    assert pv['spec']['persistentVolumeReclaimPolicy'] == 'Delete'
    return {'pvc': {'name': claim_name, 'uid': claim['metadata']['uid']}, 'pv': {'name': pv['metadata']['name'], 'uid': pv['metadata']['uid']}}


@pytest.fixture
def gateway(kube):
    os.umask(0o077)
    sources = ['tests/qualification/gateway.py', 'tests/qualification/install_gateway.py', 'tests/qualification/support.py', 'deploy/openshell/values.yaml', 'policies/openshell/identity.yaml']
    (kube.evidence / 'source-hashes.json').write_text(json.dumps({path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}, indent=2))
    owner = json.loads((STATE / 'owner.json').read_text())
    require_admission(kube, owner['admission_evidence'])
    assert kube.get('namespace', 'openshell')['metadata']['uid'] == owner['namespace_uid']
    verify(TOOLS / 'openshell', LOCK['openshell']['cli']['binary_sha256'])
    summary = {'gateway': 'blocked', 'tls': 'unrun', 'caller_auth': 'unrun', 'identity': 'unrun', 'access_isolation': 'unrun'}
    cleanup = {'namespace_uid': owner['namespace_uid'], 'confirmed': False, 'pv_confirmed': False}
    port_forward = None
    port_forwards = []
    sandbox_id = None
    name = 'identity-' + uuid.uuid4().hex[:10]
    private = STATE / name
    private.mkdir()
    mtls = private / 'openshell/gateways/qualification/mtls'
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ}
    env['XDG_CONFIG_HOME'] = str(private)

    def cli(*args, check=True, timeout=60):
        return kube.native([str(TOOLS / 'openshell'), '--gateway', 'qualification', '--workspace', 'default', *args], check=check, timeout=timeout, env=env)

    pvs = []
    try:
        gateway = kube.get('statefulset', 'openshell', '-n', 'openshell')
        assert gateway['status']['readyReplicas'] == 1
        assert gateway['spec']['template']['spec']['containers'][0]['image'] == LOCK['openshell']['images']['gateway']
        export_client(kube, mtls)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        forward_log = (kube.evidence / 'port-forward.log').open('w')
        port_forward = subprocess.Popen(kube.argv + ['port-forward', '-n', 'openshell', 'svc/openshell', '--address=127.0.0.1', f'{port}:8080'], stdout=forward_log, stderr=subprocess.STDOUT)
        port_forwards.append((port_forward, forward_log))
        deadline = time.monotonic() + 15
        while True:
            assert port_forward.poll() is None, 'Port-forward exited'
            if f'Forwarding from 127.0.0.1:{port}' in (kube.evidence / 'port-forward.log').read_text():
                break
            assert time.monotonic() < deadline, 'Port-forward delivery unknown'
            time.sleep(.2)
        url = f'https://127.0.0.1:{port}'
        kube.native([str(TOOLS / 'openshell'), 'gateway', 'add', url, '--local', '--name', 'qualification'], env=env)
        status = json.loads(cli('status', '-o', 'json').stdout)
        (kube.evidence / 'native-status.json').write_text(json.dumps(status, indent=2))
        health_args = ['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '5', '--cacert', str(mtls / 'ca.crt')]
        assert status['status'] == 'connected' and status['version'] == LOCK['openshell']['version'].removeprefix('v')
        assert status['authentication']['status'] == 'authenticated'
        # HTTP health is on the chart's separate health port. Probe this
        # gRPC listener through its native protected user method instead.
        user_probe = ['--http2', '-i', '-X', 'POST', '-H', 'content-type: application/grpc', url + '/openshell.v1.OpenShell/ListSandboxes']
        health = kube.native(health_args + user_probe)
        assert 'grpc-status: 16' in health.stdout.lower(), 'Native auth rejection control missing'
        # Same reachable endpoint; public trust must reject this private CA.
        untrusted = kube.native(['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '5', url + '/health'], check=False)
        assert untrusted.returncode == 60, 'Wrong trust was not rejected'
        wrong_name = kube.native(health_args + ['--resolve', f'wrong.invalid:{port}:127.0.0.1', f'https://wrong.invalid:{port}/health'], check=False)
        assert wrong_name.returncode == 60 and 'subject' in wrong_name.stderr.lower(), 'Hostname mismatch was not rejected'
        summary.update(gateway='passed', tls='passed')
        # Native user API acceptance with the generated client identity.
        cli('sandbox', 'list', '-o', 'json')
        # Probe the native gRPC user method without a client identity. The auth
        # router rejects it before deserialization; no custom protocol/client.
        denial = kube.native(health_args + ['--http2', '-i', '-X', 'POST', '-H', 'content-type: application/grpc', url + '/openshell.v1.OpenShell/ListSandboxes'])
        assert 'grpc-status: 16' in denial.stdout.lower(), 'Unauthenticated user request was not rejected'
        summary['caller_auth'] = 'passed'
        summary['native_create_completion'] = 'unknown'
        created = cli('sandbox', 'create', '--name', name, '--from', LOCK['openshell']['images']['workload'], '--policy', str(ROOT / 'policies/openshell/identity.yaml'), '--cpu', '1', '--memory', '512Mi', '--no-auto-providers', '--detach', '--no-tty', '-o', 'json', '--', '/bin/sleep', '600', timeout=180, check=False)
        summary.update(native_create_completion='completed', native_create_exit=created.returncode)
        assert created.returncode == 0, created.stderr
        (kube.evidence / 'create.json').write_text(created.stdout)
        actual = json.loads(cli('sandbox', 'get', name, '-o', 'json').stdout)
        sandbox_id = actual['id']
        assert actual['policy']['landlock']['compatibility'] == 'hard_requirement'
        assert actual['policy_source'] == 'sandbox'
        assert not json.loads(cli('sandbox', 'provider', 'list', name, '-o', 'json').stdout)['providers']
        summary['sandbox_id'] = sandbox_id
        summary['policy'] = actual['policy']
        pair = inspect_identity(kube, actual, summary)
        cr_name = kube.get('sandboxes', '-n', 'openshell')['items'][0]['metadata']['name']
        summary['workspace_storage'] = workspace_storage(kube, pair, summary['sandbox_uid'])
        summary['identity'] = 'passed'
        # Direct operator process in the actual workload pod independently
        # probes the outer CNI fence, avoiding a runtime policy-denial proxy.
        service = kube.get('service', 'openshell', '-n', 'openshell')['spec']['clusterIP']
        gateway_pod = kube.get('pod', 'openshell-0', '-n', 'openshell')['status']['podIP']
        kube.run('create', 'configmap', 'qualification-public-ca', '-n', 'openshell', '--from-file=ca.crt=' + str(mtls / 'ca.crt'))
        image = LOCK['fixtures']['qualification-probe']
        probe = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'qualification-probe'}, 'spec': {'automountServiceAccountToken': False, 'restartPolicy': 'Never', 'containers': [{'name': 'curl', 'image': image['image'] + '@' + image['digest'], 'command': ['/bin/sh', '-c', 'sleep 600'], 'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}, 'volumeMounts': [{'name': 'ca', 'mountPath': '/qualification-ca', 'readOnly': True}]}], 'volumes': [{'name': 'ca', 'configMap': {'name': 'qualification-public-ca'}}]}}
        probe_path = kube.evidence / 'trusted-probe.yaml'
        probe_path.write_text(yaml.safe_dump(probe))
        kube.run('apply', '-n', 'openshell', '-f', probe_path)
        kube.run('wait', '-n', 'openshell', '--for=condition=Ready', 'pod/qualification-probe', '--timeout=90s')
        for _ in range(3):
            for destination in (service, gateway_pod):
                control = kube.run('exec', '-n', 'openshell', 'qualification-probe', '--', 'curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '5', '--cacert', '/qualification-ca/ca.crt', '--resolve', f'localhost:8080:{destination}', '--http2', '-i', '-X', 'POST', '-H', 'content-type: application/grpc', 'https://localhost:8080/openshell.v1.OpenShell/ListSandboxes')
                assert 'grpc-status: 16' in control.stdout.lower(), 'Gateway network control failed'
                direct = kube.run('exec', '-n', 'openshell', pair['workload']['metadata']['name'], '-c', 'agent', '--', '/bin/bash', '-c', f'timeout 3 bash -c "echo > /dev/tcp/{destination}/8080"', check=False)
                assert direct.returncode == 124, 'Direct workload gateway access was not fenced'
        summary['access_isolation'] = 'passed'
        assert json.loads(cli('sandbox', 'get', name, '-o', 'json').stdout)['id'] == sandbox_id
        cli('sandbox', 'delete', name)
        assert not json.loads(cli('sandbox', 'list', '-o', 'json').stdout)['sandboxes']
        wait_resource_absent(kube, 'sandbox', cr_name, summary['sandbox_uid'])
        for pod in pair.values():
            wait_resource_absent(kube, 'pod', pod['metadata']['name'], pod['metadata']['uid'])
        for resource, identity in summary['workspace_storage'].items():
            wait_resource_absent(kube, resource, identity['name'], identity['uid'], namespace=None if resource == 'pv' else 'openshell')
        sandbox_id = None
        yield {'endpoint': f'127.0.0.1:{port}', 'mtls': mtls, 'cli': cli, 'port_forwards': port_forwards}
    finally:
        (kube.evidence / 'gateway.json').write_text(json.dumps(summary, indent=2))
        try:
            # Actual namespace and volume identities, no Secret payloads/raw vendor exports.
            for resource in ('pods', 'sandboxes', 'pvc', 'networkpolicies', 'events'):
                kube.run('get', resource, '-n', 'openshell', '-o', 'json', check=False)
            claims = kube.get('pvc', '-n', 'openshell')['items']
            for claim in claims:
                if claim['spec'].get('volumeName'):
                    pvs.append(kube.get('pv', claim['spec']['volumeName']))
            cleanup['pvs'] = [{'name': pv['metadata']['name'], 'uid': pv['metadata']['uid']} for pv in pvs]
            if sandbox_id:
                current = json.loads(cli('sandbox', 'get', name, '-o', 'json').stdout)
                assert current['id'] == sandbox_id, 'Native sandbox identity replaced; refusing delete'
                cli('sandbox', 'delete', name)
                assert not json.loads(cli('sandbox', 'list', '-o', 'json').stdout)['sandboxes'], 'Native deletion not confirmed'
            assert kube.get('namespace', 'openshell')['metadata']['uid'] == owner['namespace_uid'], 'Namespace replaced; refusing delete'
            kube.native([str(TOOLS / 'helm'), '--kubeconfig', str(ROOT / '.state/kind/kubeconfig'), '--kube-context', 'kind-corsair', 'uninstall', 'openshell', '-n', 'openshell', '--wait', '--timeout', '90s'])
            kube.run('delete', 'namespace', 'openshell', '--wait=true', '--timeout=120s', timeout=140)
            assert not kube.run('get', 'namespace', 'openshell', '--ignore-not-found', '-o', 'json').stdout.strip()
            cleanup['confirmed'] = True
            deadline = time.monotonic() + 90
            for pv in pvs:
                while True:
                    remaining = kube.run('get', 'pv', pv['metadata']['name'], '--ignore-not-found', '-o', 'json').stdout
                    if not remaining.strip():
                        break
                    assert json.loads(remaining)['metadata']['uid'] == pv['metadata']['uid'], 'PV replaced'
                    assert time.monotonic() < deadline, 'PV reclamation unconfirmed'
                    time.sleep(2)
            cleanup['pv_confirmed'] = True
            shutil.rmtree(STATE)
            cleanup['private_state_absent'] = not STATE.exists()
        finally:
            try:
                if port_forward is not None:
                    for process, log in port_forwards:
                        if process.poll() is None:
                            process.terminate()
                        process.wait(timeout=10)
                        log.close()
                    cleanup['port_forward_exit'] = port_forward.returncode
                    cleanup['port_forwards'] = [{'pid': p.pid, 'exit': p.returncode} for p, _ in port_forwards]
                    cleanup['port_forward_confirmed'] = all(p.poll() is not None for p, _ in port_forwards)
            finally:
                (kube.evidence / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
                summary['outcome'] = 'passed' if all(summary[key] == 'passed' for key in ('gateway', 'tls', 'caller_auth', 'identity', 'access_isolation')) and all(cleanup.get(key) is True for key in ('confirmed', 'pv_confirmed', 'private_state_absent', 'port_forward_confirmed')) else 'failed'
                (kube.evidence / 'gateway.json').write_text(json.dumps(summary, indent=2))
