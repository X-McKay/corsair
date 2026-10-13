"""Offline guards for the proposed SPEC-0036 workspace quota class; live enforcement is unqualified."""
import os
import subprocess

import pytest
import yaml

from tests.qualification.support import ROOT

STORAGE = ROOT / 'deploy/storage'
GiB = 1024 ** 3


def documents(name):
    return {(d['kind'], d['metadata']['name']): d for d in yaml.safe_load_all((STORAGE / name).read_text())}


def quantity(value):
    return int(value[:-2]) * GiB if value.endswith('Gi') else int(value)


def test_quota_class_names_agree_and_leave_standard_unchanged():
    provisioner = documents('provisioner.yaml')
    storage_class = provisioner[('StorageClass', 'corsair-workspace')]
    assert storage_class['provisioner'] == 'corsair.local/workspace-quota'
    assert storage_class['allowVolumeExpansion'] is False and storage_class['reclaimPolicy'] == 'Delete'
    command = provisioner[('Deployment', 'corsair-workspace-provisioner')]['spec']['template']['spec']['containers'][0]
    flags = dict(zip(command['command'][3::2], command['command'][4::2]))
    assert flags['--provisioner-name'] == storage_class['provisioner']
    assert flags['--configmap-name'] == 'corsair-workspace-config'
    lock = yaml.safe_load((ROOT / 'deploy/runtime-lock.yaml').read_text())['storage']
    assert command['image'] == 'docker.io/kindest/local-path-provisioner@' + lock['provisioner_image'].split('@')[1]
    assert lock['storage_class'] == 'standard'
    kustomization = yaml.safe_load((STORAGE / 'kustomization.yaml').read_text())
    generated = kustomization['configMapGenerator'][0]
    assert generated['name'] == flags['--configmap-name'] and generated['namespace'] == 'corsair-workspace-storage'
    assert sorted(generated['files']) == ['config.json', 'helperPod.yaml', 'setup=setup.sh', 'teardown=teardown.sh']


def test_namespace_guards_bound_requests_by_backing_image_and_require_the_class():
    guards = documents('sandbox-namespace.yaml')
    overlay = yaml.safe_load((ROOT / 'deploy/openshell/values-workspace-quota.yaml').read_text())['server']
    assert overlay == {'sandboxNamespace': 'openshell-sandboxes', 'workspaceStorageClass': 'corsair-workspace',
                       'workspaceDefaultStorageSize': '8Gi'}
    hard = guards[('ResourceQuota', 'corsair-workspace')]['spec']['hard']
    per_class = quantity(hard['corsair-workspace.storageclass.storage.k8s.io/requests.storage'])
    claims = int(hard['corsair-workspace.storageclass.storage.k8s.io/persistentvolumeclaims'])
    assert per_class == claims * quantity(overlay['workspaceDefaultStorageSize'])
    source = (ROOT / 'deploy/kind/bootstrap.py').read_text()
    image = int(source.split('WORKSPACE_IMAGE_SIZE = "')[1].split('G"')[0]) * GiB
    assert per_class < image
    policy = guards[('ValidatingAdmissionPolicy', 'corsair-workspace-guard')]
    expressions = ' '.join(v['expression'] for v in policy['spec']['validations'])
    assert "'corsair-workspace'" in expressions and "quantity('8Gi')" in expressions and 'ephemeral-storage' in expressions
    assert policy['spec']['failurePolicy'] == 'Fail'
    binding = guards[('ValidatingAdmissionPolicyBinding', 'corsair-workspace-guard')]['spec']
    assert binding['validationActions'] == ['Deny']
    assert binding['matchResources']['namespaceSelector']['matchLabels'] == {'kubernetes.io/metadata.name': 'openshell-sandboxes'}
    assert 'ephemeral-storage' in guards[('LimitRange', 'corsair-ephemeral-storage')]['spec']['limits'][0]['default']


def test_workspace_policy_is_identity_without_tmp():
    identity = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    workspace = yaml.safe_load((ROOT / 'policies/openshell/workspace.yaml').read_text())
    assert workspace['filesystem_policy']['read_write'] == ['/dev/null']
    assert workspace['filesystem_policy']['include_workdir'] is True
    identity['filesystem_policy']['read_write'] = ['/dev/null']
    assert workspace == identity


SHIMS = {
    'stat': 'echo "${FAKE_FSTYPE:-xfs}"',
    'flock': 'exit 0',
    'xfs_io': 'echo "projid = $(cat "$FAKE/project.$(basename "$3")" 2>/dev/null || echo 0)"',
    'xfs_quota': r'''
echo "$*" >> "$FAKE/calls"
case "$3" in
  state) printf 'User quota state on /x\n  Accounting: OFF\n  Enforcement: OFF\nProject quota state on /x\n  Accounting: %s\n  Enforcement: %s\n' "${FAKE_ACCOUNTING:-ON}" "${FAKE_ENFORCEMENT:-ON}";;
  "project -s -p "*) set -- $3; echo "$5" > "$FAKE/project.$(basename "$4")";;
  "limit -p "*) set -- $3; echo "${3#bhard=}" | tr -d k > "$FAKE/bhard"; echo "${4#ihard=}" > "$FAKE/ihard"; [ -z "${FAKE_LIMIT_FAILS:-}" ];;
  "report -p -b -n -N") echo "#$(cat "$FAKE"/project.*) 0 0 $(cat "$FAKE/bhard")${FAKE_SKEW:-} 00 [--------]";;
  "report -p -i -n -N") echo "#$(cat "$FAKE"/project.*) 0 0 $(cat "$FAKE/ihard") 00 [--------]";;
esac''',
}


def run_script(name, tmp_path, size=8 * GiB, **fake):
    bin_dir, state, root = tmp_path / 'bin', tmp_path / 'fake', tmp_path / 'workspaces'
    for directory in (bin_dir, state, root):
        directory.mkdir(exist_ok=True)
    for command, body in SHIMS.items():
        (bin_dir / command).write_text('#!/bin/sh\n' + body + '\n')
        (bin_dir / command).chmod(0o755)
    environment = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'FAKE': str(state),
                   'VOL_DIR': str(root / 'pvc-1_ns_workspace-a'), 'VOL_MODE': 'Filesystem',
                   'VOL_SIZE_BYTES': str(size), **fake}
    result = subprocess.run(['sh', str(STORAGE / name)], env=environment, capture_output=True, text=True, timeout=30)
    return result, root / 'pvc-1_ns_workspace-a', state


def test_setup_sets_byte_and_inode_limits_and_reads_them_back(tmp_path):
    result, volume, state = run_script('setup.sh', tmp_path)
    assert result.returncode == 0, result.stderr
    assert volume.is_dir()
    assert (state / 'bhard').read_text().strip() == str(8 * GiB // 1024)
    assert (state / 'ihard').read_text().strip() == str(8 * GiB // 16384)
    assert 'project=1001' in result.stdout


@pytest.mark.parametrize('fake, reason', [
    ({'FAKE_FSTYPE': 'ext2/ext3'}, 'is not xfs'),
    ({'FAKE_ENFORCEMENT': 'OFF'}, 'not both on'),
    ({'FAKE_ACCOUNTING': 'OFF'}, 'not both on'),
    ({'FAKE_LIMIT_FAILS': '1'}, 'limits for project'),
    ({'FAKE_SKEW': '1'}, 'byte limit not read back'),
    ({'VOL_MODE': 'Block'}, 'volume mode'),
])
def test_setup_fails_closed_and_leaves_no_volume(tmp_path, fake, reason):
    result, volume, _ = run_script('setup.sh', tmp_path, **fake)
    assert result.returncode != 0 and reason in result.stderr
    assert not volume.exists()


@pytest.mark.parametrize('size', [0, 1024, 17 * GiB])
def test_setup_refuses_sizes_outside_operator_bounds(tmp_path, size):
    result, volume, _ = run_script('setup.sh', tmp_path, size=size)
    assert result.returncode != 0 and 'outside bounds' in result.stderr and not volume.exists()


def test_teardown_removes_volume_and_clears_its_project(tmp_path):
    assert run_script('setup.sh', tmp_path)[0].returncode == 0
    result, volume, state = run_script('teardown.sh', tmp_path)
    assert result.returncode == 0, result.stderr
    assert not volume.exists()
    assert (state / 'calls').read_text().splitlines()[-1].startswith('-x -c limit -p bhard=0 ihard=0 1001')
