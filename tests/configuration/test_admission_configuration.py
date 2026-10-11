"""Admission profile guards; no claim about live kernel or storage behavior."""
import re

import yaml

from tests.qualification.support import ROOT, LOCK


def test_admission_artifacts_and_chart_keep_immutable_security_defaults():
    for name in ('helm', 'agent_sandbox', 'storage'):
        assert re.fullmatch(r'[0-9a-f]{64}', LOCK[name]['sha256'])
        assert LOCK[name]['version'] in LOCK[name]['url']
    assert re.fullmatch(r'[0-9a-f]{64}', LOCK['helm']['binary_sha256'])
    assert LOCK['helm']['version'].startswith('v3.')
    for image in [LOCK['agent_sandbox']['controller_image'], LOCK['storage']['provisioner_image'], LOCK['storage']['helper_image'], *LOCK['openshell']['images'].values()]:
        assert re.fullmatch(r'[^@]+@sha256:[0-9a-f]{64}', image)
    chart = LOCK['openshell']['chart']
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', chart['manifest_digest'])
    assert re.fullmatch(r'[0-9a-f]{64}', chart['sha256'])
    assert chart['version'] == LOCK['openshell']['version'].removeprefix('v')
    values = yaml.safe_load((ROOT / 'deploy/openshell/values.yaml').read_text())
    assert values['agentSandbox']['preflight']['enabled'] is True
    assert values['server']['disableTls'] is False
    assert not values['server'].get('auth', {}).get('allowUnauthenticatedUsers')
    for field, key in [('gateway', 'gateway'), ('supervisor', 'supervisor'), ('sandboxRuntime', 'runtime')]:
        assert values[field]['image']['digest'] == LOCK['openshell']['images'][key].split('@')[1]
    assert values['sandbox']['image']['repository'] + '@' + values['sandbox']['image']['digest'] == LOCK['openshell']['images']['workload']


def test_native_admission_fixture_has_no_credentials_or_host_access():
    docs = list(yaml.safe_load_all((ROOT / 'deploy/qualification/admission.yaml').read_text()))
    policy, sandbox = docs
    assert policy['spec'] == {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'], 'ingress': [], 'egress': []}
    assert sandbox['apiVersion'] == LOCK['agent_sandbox']['api_version']
    pod = sandbox['spec']['podTemplate']['spec']
    assert pod['automountServiceAccountToken'] is False
    assert all(pod[key] is False for key in ('hostNetwork', 'hostPID', 'hostIPC', 'shareProcessNamespace'))
    assert pod['securityContext']['seccompProfile'] == {'type': 'RuntimeDefault'}
    assert pod['securityContext']['runAsNonRoot'] is True
    for container in pod['initContainers'] + pod['containers']:
        assert container['securityContext']['capabilities'] == {'drop': ['ALL']}
        assert container['securityContext']['allowPrivilegeEscalation'] is False
        assert not container.get('env') and not container.get('envFrom')
        assert not container['securityContext'].get('privileged')
    assert pod['initContainers'][0]['command'][1] == 'copy-self'
    assert pod['volumes'] == [{'name': 'runtime', 'emptyDir': {'medium': 'Memory'}}]
    assert sandbox['spec']['volumeClaimTemplates'][0]['spec']['storageClassName'] == LOCK['storage']['storage_class']
