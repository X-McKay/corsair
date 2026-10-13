"""Live SPEC-0036 storage stage: corsair-workspace volumes bound bytes and inodes for a non-root writer.

Plain pods on the quota class only; the OpenShell sandbox stage (workspace policy, gateway overlay) is separate.
Requires `make workspace-storage` on this owned node. Each run creates and deletes its own namespace.
"""
import json
import time
from uuid import uuid4

import pytest
import yaml

from tests.qualification.support import require_platform

NODE = 'corsair-control-plane'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
SIZE_MIB = 64
INODES = SIZE_MIB * 1024 * 1024 // 16384
QUOTA_ERRORS = ('Disk quota exceeded', 'No space left on device')
# Provisioner and helper writes on the node are tiny; anything larger means bytes escaped the backing image.
NODE_DRIFT_KIB = 8192


def node(kube, *argv):
    return kube.native(DOCKER + ['exec', NODE, *argv]).stdout


def manifests(namespace):
    claim = lambda name: {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
                          'metadata': {'name': name, 'namespace': namespace},
                          'spec': {'storageClassName': 'corsair-workspace', 'accessModes': ['ReadWriteOnce'],
                                   'resources': {'requests': {'storage': f'{SIZE_MIB}Mi'}}}}
    pod = lambda name: {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace},
                        'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                                 'securityContext': {'runAsUser': 10001, 'runAsGroup': 10001, 'runAsNonRoot': True},
                                 'containers': [{'name': 'writer', 'image': 'corsair-workspace-helper:local',
                                                 'imagePullPolicy': 'Never', 'command': ['sleep', '900'],
                                                 'securityContext': {'allowPrivilegeEscalation': False,
                                                                     'readOnlyRootFilesystem': True,
                                                                     'capabilities': {'drop': ['ALL']}},
                                                 'resources': {'limits': {'cpu': '500m', 'memory': '256Mi'}},
                                                 'volumeMounts': [{'name': 'w', 'mountPath': '/w'}]}],
                                 'volumes': [{'name': 'w', 'persistentVolumeClaim': {'claimName': name}}]}}
    return [claim('a'), claim('b'), pod('a'), pod('b')]


def shell(kube, namespace, pod, script, timeout=300):
    """Run as the non-root writer; exit status and errors are data, not a gate failure."""
    result = kube.run('exec', '-n', namespace, pod, '--', 'sh', '-c', script, check=False, timeout=timeout)
    return dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)


@pytest.mark.workspace_quota
def test_quota_class_bounds_bytes_and_inodes_and_contains_exhaustion(kube):
    require_platform(kube)
    record = dict(scope='SPEC-0036 storage stage: plain pods on corsair-workspace', outcome='failed',
                  size_mib=SIZE_MIB, inode_limit=INODES)
    evidence = kube.evidence / 'workspace-quota'
    evidence.mkdir(mode=0o700)
    assert node(kube, 'stat', '-f', '-c', '%T', '/var/corsair-workspaces').strip() == 'xfs', 'run make workspace-storage'
    assert kube.get('storageclass', 'corsair-workspace')['provisioner'] == 'corsair.local/workspace-quota'
    namespace = f'corsair-quota-{uuid4().hex[:8]}'
    record['namespace'] = namespace
    path = evidence / 'manifests.yaml'
    path.write_text(yaml.safe_dump_all(manifests(namespace)))
    image_kib = lambda: int(node(kube, 'du', '-k', '--apparent-size', '/var/corsair-workspaces.img').split()[0])
    var_used = lambda: int(node(kube, 'df', '-k', '--output=used', '/var').split()[-1])
    uid = None
    try:
        record['before'] = dict(image_kib=image_kib(), node_var_used_kib=var_used())
        # `create` refuses an existing name; the UID binds cleanup to the namespace this run made.
        kube.run('create', 'namespace', namespace)
        uid = record['namespace_uid'] = kube.get('namespace', namespace)['metadata']['uid']
        kube.run('apply', '-f', path)
        for pod in ('a', 'b'):
            kube.run('wait', '-n', namespace, '--for=condition=Ready', f'pod/{pod}', '--timeout=180s', timeout=200)
        record['statfs'] = shell(kube, namespace, 'a', 'df -k /w; df -i /w')
        record['bytes'] = shell(kube, namespace, 'a',
                                f'dd if=/dev/zero of=/w/big bs=1M count={SIZE_MIB * 2} 2>&1; echo rc=$?; '
                                'stat -c %s /w/big; rm -f /w/big')
        # Empty files: the inode limit must stop creation long before the byte limit could.
        record['inodes'] = shell(kube, namespace, 'a',
                                 f'mkdir /w/f && i=0; while : > /w/f/$i; do i=$((i+1)); '
                                 f'[ $i -ge {INODES * 2} ] && break; done; echo created=$i', timeout=600)
        record['neighbour'] = shell(kube, namespace, 'b',
                                    'dd if=/dev/zero of=/w/ok bs=1M count=8 2>&1; echo rc=$?; '
                                    'mkdir /w/f && i=0; while [ $i -lt 100 ] && : > /w/f/$i; do i=$((i+1)); done; '
                                    'echo created=$i')
        record['after'] = dict(image_kib=image_kib(), node_var_used_kib=var_used())
        (evidence / 'record.json').write_text(json.dumps(record, indent=2))

        written = int(record['bytes']['stdout'].strip().splitlines()[-1])
        assert 'rc=0' not in record['bytes']['stdout'] and any(e in record['bytes']['stdout'] for e in QUOTA_ERRORS)
        assert written <= SIZE_MIB * 1024 * 1024
        created = int(record['inodes']['stdout'].split('created=')[-1])
        assert created < INODES and any(e in record['inodes']['stdout'] + record['inodes']['stderr'] for e in QUOTA_ERRORS)
        assert 'rc=0' in record['neighbour']['stdout'] and 'created=100' in record['neighbour']['stdout']
        assert record['after']['image_kib'] == record['before']['image_kib']
        assert abs(record['after']['node_var_used_kib'] - record['before']['node_var_used_kib']) < NODE_DRIFT_KIB
        record['outcome'] = 'passed'
    finally:
        cleanup = dict(namespace_deleted=False)
        current = kube.run('get', 'namespace', namespace, '--ignore-not-found', '-o', 'json', check=False).stdout.strip()
        if uid is None:
            cleanup['refused'] = 'namespace ownership unknown; no automatic deletion'
        elif current and json.loads(current)['metadata']['uid'] != uid:
            cleanup['refused'] = 'namespace identity changed; replacement not deleted'
        elif current:
            kube.run('delete', 'namespace', namespace, '--wait=true', '--timeout=180s', check=False, timeout=200)
        if uid is not None and 'refused' not in cleanup:
            cleanup['namespace_deleted'] = not kube.run('get', 'namespace', namespace, '--ignore-not-found', '-o',
                                                        'json', check=False).stdout.strip()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            left = [pv['metadata']['name'] for pv in kube.get('pv')['items']
                    if pv['spec'].get('claimRef', {}).get('namespace') == namespace]
            if not left:
                break
            time.sleep(2)
        cleanup['volumes_left'] = left
        cleanup['volume_dirs_left'] = [d for d in node(kube, 'ls', '/var/corsair-workspaces').split() if namespace in d]
        cleanup['confirmed'] = cleanup['namespace_deleted'] and not left and not cleanup['volume_dirs_left']
        record['cleanup'] = cleanup
        (evidence / 'record.json').write_text(json.dumps(record, indent=2))
    assert cleanup['confirmed'], cleanup
