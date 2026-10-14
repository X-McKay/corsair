"""Storage and native OpenShell primitives only; no gateway or runtime adapter."""
import json
import shutil
import time
import uuid

import pytest
import yaml

from tests.qualification.support import ROOT, LOCK, require_platform


def wait_pod(kube, namespace):
    deadline = time.monotonic() + 180
    while True:
        pods = kube.get('pods', '-n', namespace)['items']
        if len(pods) == 1 and not pods[0]['metadata'].get('deletionTimestamp'):
            pod = pods[0]
            if any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod.get('status', {}).get('conditions', [])):
                return pod
            assert pod.get('status', {}).get('phase') not in ('Failed', 'Succeeded'), 'Unexpected admission pod termination'
        assert time.monotonic() < deadline, 'Controller/storage/image/pod readiness timeout; inspect retained events'
        time.sleep(2)


def assert_profile(pod):
    spec = pod['spec']
    assert spec['automountServiceAccountToken'] is False
    assert all(not spec.get(key, False) for key in ('hostNetwork', 'hostPID', 'hostIPC', 'shareProcessNamespace'))
    security = spec['securityContext']
    assert security['runAsUser'] == security['runAsGroup'] == security['fsGroup'] == 10001
    assert security['runAsNonRoot'] is True and security['supplementalGroupsPolicy'] == 'Strict'
    assert security['seccompProfile'] == {'type': 'RuntimeDefault'}
    assert security['sysctls'] == [{'name': 'net.ipv4.ip_unprivileged_port_start', 'value': '0'}]
    assert not security.get('supplementalGroups')
    for container in spec['initContainers'] + spec['containers']:
        context = container['securityContext']
        assert context['allowPrivilegeEscalation'] is False
        assert context['capabilities'] == {'drop': ['ALL']}
        assert not context.get('privileged')
    assert spec['initContainers'][0]['image'] == LOCK['openshell']['images']['runtime']
    assert spec['containers'][0]['image'] == LOCK['openshell']['images']['workload']
    assert all(not any(key in volume for key in ('hostPath', 'secret', 'projected')) for volume in spec['volumes'])


@pytest.mark.admission
def test_storage_and_native_kernel_admission(kube):
    require_platform(kube)
    crd = kube.get('crd', 'sandboxes.agents.x-k8s.io')
    assert [v['name'] for v in crd['spec']['versions'] if v['served']] == ['v1beta1']
    controller = kube.get('deployment', 'agent-sandbox-controller', '-n', 'agent-sandbox-system')
    assert controller['status'].get('availableReplicas') == 1
    assert controller['spec']['template']['spec']['containers'][0]['image'] == LOCK['agent_sandbox']['controller_image']
    storage = kube.get('storageclass', LOCK['storage']['storage_class'])
    assert storage['provisioner'] == 'rancher.io/local-path' and storage['reclaimPolicy'] == 'Delete'
    assert storage['volumeBindingMode'] == 'WaitForFirstConsumer'
    provisioner = kube.get('deployment', 'local-path-provisioner', '-n', 'local-path-storage')
    container = provisioner['spec']['template']['spec']['containers'][0]
    assert container['image'] == LOCK['storage']['provisioner_image']
    assert LOCK['storage']['helper_image'] in container['command']
    namespace = 'corsair-admission-' + uuid.uuid4().hex[:12]
    evidence = kube.evidence / 'admission'
    evidence.mkdir()
    namespace_uid = None
    pv = None
    summary = {'storage': 'unrun', 'kernel': 'unrun', 'gateway': 'unrun'}
    cleanup = {'namespace': namespace, 'confirmed': False, 'pv_confirmed': False}
    try:
        kube.run('create', 'namespace', namespace)
        namespace_uid = kube.get('namespace', namespace)['metadata']['uid']
        cleanup['namespace_uid'] = namespace_uid
        (evidence / 'owner.json').write_text(json.dumps(cleanup, indent=2))
        manifests = evidence / 'manifests'
        manifests.mkdir()
        shutil.copyfile(ROOT / 'deploy/qualification/admission.yaml', manifests / 'admission.yaml')
        shutil.copyfile(ROOT / 'deploy/qualification/admission-kustomize.yaml', manifests / 'configuration.yaml')
        # Native Kustomize handles images in the custom-resource podTemplate.
        (manifests / 'kustomization.yaml').write_text(yaml.safe_dump({'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization', 'resources': ['admission.yaml'], 'configurations': ['configuration.yaml'], 'images': [{'name': alias, 'newName': image.split('@')[0], 'digest': image.split('@')[1]} for alias, image in [('admission-runtime', LOCK['openshell']['images']['runtime']), ('admission-workload', LOCK['openshell']['images']['workload'])]]}))
        rendered = kube.run('kustomize', manifests).stdout
        (evidence / 'rendered.yaml').write_text(rendered)
        # Check custom-resource image substitution before creating anything.
        sandbox = next(d for d in yaml.safe_load_all(rendered) if d['kind'] == 'Sandbox')
        assert_profile({'spec': sandbox['spec']['podTemplate']['spec']})
        kube.run('apply', '-n', namespace, '-k', manifests)
        pod = wait_pod(kube, namespace)
        assert_profile(pod)
        sandbox = kube.get('sandboxes', 'admission', '-n', namespace)
        sandbox_uid = sandbox['metadata']['uid']
        assert any(o['uid'] == sandbox_uid and o.get('controller') for o in pod['metadata']['ownerReferences'])
        claim = kube.get('pvc', '-n', namespace)['items']
        assert len(claim) == 1 and claim[0]['status']['phase'] == 'Bound'
        pvc = claim[0]
        assert pvc['spec']['storageClassName'] == LOCK['storage']['storage_class']
        pv = kube.get('pv', pvc['spec']['volumeName'])
        assert pv['spec']['claimRef']['uid'] == pvc['metadata']['uid']
        cleanup.update(pv_name=pv['metadata']['name'], pv_uid=pv['metadata']['uid'])
        marker = uuid.uuid4().hex
        kube.run('exec', '-n', namespace, pod['metadata']['name'], '-c', 'agent', '--', '/bin/sh', '-ec', f"printf '%s' '{marker}' > /sandbox/marker; sync")
        first_uid = pod['metadata']['uid']
        # Refuse a replaced pod before the intentional storage remount.
        assert kube.get('pod', pod['metadata']['name'], '-n', namespace)['metadata']['uid'] == first_uid
        kube.run('delete', 'pod', pod['metadata']['name'], '-n', namespace, '--wait=true', '--timeout=90s')
        replacement = wait_pod(kube, namespace)
        assert replacement['metadata']['uid'] != first_uid
        assert_profile(replacement)
        assert any(o['uid'] == sandbox_uid and o.get('controller') for o in replacement['metadata']['ownerReferences'])
        remounted = kube.get('pvc', pvc['metadata']['name'], '-n', namespace)
        assert remounted['metadata']['uid'] == pvc['metadata']['uid']
        assert remounted['spec']['volumeName'] == pv['metadata']['name']
        read = kube.run('exec', '-n', namespace, replacement['metadata']['name'], '-c', 'agent', '--', '/bin/cat', '/sandbox/marker')
        assert read.stdout == marker
        summary.update(storage='passed', sandbox_uid=sandbox_uid, pvc_uid=pvc['metadata']['uid'], pv_uid=pv['metadata']['uid'], pod_uids=[first_uid, replacement['metadata']['uid']])
        # Native probe tests a nondumpable broker and executed dumpable child,
        # hard Landlock allow/deny and non-TSYNC listener inheritance itself.
        # A delivery timeout blocks qualification and cannot establish the
        # remote probe's outcome. The native receipt retains partial output.
        summary['kernel'] = 'blocked'
        summary['kernel_command'] = 'unknown'
        result = kube.run('exec', '-n', namespace, replacement['metadata']['name'], '-c', 'agent', '--', '/runtime/openshell-sandbox', 'capability-probe', check=False, timeout=90)
        summary.update(kernel='failed', kernel_command='completed', kernel_exit_code=result.returncode)
        assert result.returncode == 0, f'Native OpenShell runtime admission failed: {result.stdout} {result.stderr}'
        report = json.loads(result.stdout)
        required = ['qualified', 'capabilities_zero', 'no_new_privileges', 'child_dumpable', 'child_core_limit_zero', 'same_uid_self_protection', 'landlock_allow_deny', 'seccomp_notification', 'seccomp_addfd_send', 'task_memory_copy', 'connected_send_fast_path', 'socket_virtualization', 'socket_loopback_confinement', 'dns_relay_bind', 'udp_dns_round_trip', 'tcp_dns_round_trip', 'tcp_allow_round_trip', 'tcp_deny_round_trip']
        assert all(report.get(key) is True for key in required), report
        assert report['uid'] == report['gid'] == 10001 and report['supplementary_groups'] == [10001]
        assert report['landlock_abi'] >= 3 and report['sandbox_dumpable'] is False
        summary.update(kernel='passed', native_report=report)
    finally:
        (evidence / 'admission.json').write_text(json.dumps(summary, indent=2))
        try:
            if namespace_uid is None:
                raise RuntimeError('Namespace ownership unknown; cleanup unconfirmed')
            for resource in ('pods', 'sandboxes', 'pvc', 'events'):
                kube.run('get', resource, '-n', namespace, '-o', 'json', check=False)
            kube.run('logs', '-n', 'agent-sandbox-system', 'deployment/agent-sandbox-controller', '--tail=100', '--timestamps=true', check=False)
            kube.run('logs', '-n', 'local-path-storage', 'deployment/local-path-provisioner', '--tail=100', '--timestamps=true', check=False)
            assert kube.get('namespace', namespace)['metadata']['uid'] == namespace_uid, 'Namespace identity changed; refusing replacement deletion'
            kube.run('delete', 'namespace', namespace, '--wait=true', '--timeout=120s', timeout=140)
            assert not kube.run('get', 'namespace', namespace, '--ignore-not-found', '-o', 'json').stdout.strip(), 'Namespace cleanup unconfirmed'
            cleanup['confirmed'] = True
            if pv:
                deadline = time.monotonic() + 90
                while True:
                    remaining = kube.run('get', 'pv', pv['metadata']['name'], '--ignore-not-found', '-o', 'json').stdout
                    if not remaining.strip():
                        cleanup['pv_confirmed'] = True
                        break
                    assert json.loads(remaining)['metadata']['uid'] == pv['metadata']['uid'], 'PV replaced; refusing unrelated cleanup'
                    assert time.monotonic() < deadline, 'PV reclamation unconfirmed'
                    time.sleep(2)
        finally:
            (evidence / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
