"""Offline evidence failure guards; no enforcement qualification claims."""
import copy
import json
from types import SimpleNamespace

import pytest

from tests.qualification.support import ROOT, LOCK
from tests.qualification.test_policy import (fixture_policy, assert_effective, expect_permission_denied,
                                             expect_http_control, expect_method_denial, expect_endpoint_denial,
                                             require_network, observe_policy, policy_denial_events, global_policy_observation, owned_sandbox,
                                             logging_activation_observed, workload_fence)


@pytest.mark.parametrize('change', ['audit', 'wildcard', 'provider', 'filesystem'])
def test_effective_policy_rejects_expanded_or_weakened_authority(change):
    expected = fixture_policy(False, 'echo.fixture.svc.cluster.local', '10.96.1.2')
    actual = copy.deepcopy(expected)
    endpoint = actual['network_policies']['fixture']['endpoints'][0]
    if change == 'audit':
        endpoint['enforcement'] = 'audit'
    elif change == 'wildcard':
        endpoint['host'] = '*.svc.cluster.local'
    elif change == 'provider':
        actual['network_policies']['_provider_extra'] = actual['network_policies']['fixture']
    else:
        actual['filesystem_policy']['read_write'].append('/opt/corsair-denied')
    with pytest.raises(AssertionError):
        assert_effective(actual, expected)


@pytest.mark.parametrize('check,result', [
    (expect_permission_denied, SimpleNamespace(exit_code=1, stdout='', stderr='No such file or directory')),
    (expect_http_control, SimpleNamespace(exit_code=7, stdout='\nSTATUS:000', stderr='Connection refused')),
    (expect_http_control, SimpleNamespace(exit_code=127, stdout='', stderr='/usr/bin/curl: No such file or directory')),
    (expect_method_denial, SimpleNamespace(exit_code=0, stdout='{"error":"upstream_unavailable"}\nSTATUS:403', stderr='')),
    (expect_endpoint_denial, SimpleNamespace(exit_code=28, stdout='\nSTATUS:000', stderr='Timeout')),
])
def test_arbitrary_failure_cannot_pass_a_control_or_policy_denial(check, result):
    with pytest.raises(AssertionError):
        check(result)


@pytest.mark.parametrize('fault', ['node', 'junit', 'cleanup'])
def test_policy_requires_successful_exact_node_cni(tmp_path, monkeypatch, fault):
    monkeypatch.setattr('tests.qualification.test_policy.ROOT', tmp_path)
    monkeypatch.setattr('tests.qualification.test_policy.require_owned_cluster', lambda kube: {'metadata': {'uid': 'current'}})
    prior = tmp_path / '.runs/network'
    prior.mkdir(parents=True)
    deploy = tmp_path / 'deploy'
    deploy.mkdir()
    (deploy / 'runtime-lock.yaml').write_bytes((ROOT / 'deploy/runtime-lock.yaml').read_bytes())
    (prior / 'runtime-lock.yaml').write_bytes((deploy / 'runtime-lock.yaml').read_bytes())
    (prior / 'scope.json').write_text(json.dumps({'node_uid': 'old' if fault == 'node' else 'current'}))
    (prior / 'junit.xml').write_text('<testsuites><testsuite tests="3" failures="' + ('1' if fault == 'junit' else '0') + '" errors="0" skipped="0"/></testsuites>')
    for scenario in ('test_ingress_selection_and_rollback', 'test_egress_denial_and_narrow_allow'):
        path = prior / scenario
        path.mkdir()
        (path / 'cleanup.json').write_text(json.dumps({'confirmed': fault != 'cleanup'}))
        (path / 'service-readiness.json').write_text(json.dumps({'ready': True}))
    with pytest.raises(AssertionError):
        require_network(None, prior)


def test_policy_update_must_be_loaded_not_merely_effective():
    policy = fixture_policy(False)
    admission = {'state': 'accepted', 'policy_hash': 'hash'}
    full = {'policy': policy, 'hash': 'hash', 'version': 2}
    def cli(*args):
        if args[:2] == ('sandbox', 'get'):
            value = {'id': 'original', 'policy_source': 'sandbox', 'configuration_admission': admission, 'policy': policy}
        elif args[:3] == ('sandbox', 'provider', 'list'):
            value = {'providers': []}
        elif '--rev' in args:
            value = dict(full, status='pending')
        else:
            value = full
        return SimpleNamespace(stdout=json.dumps(value))
    with pytest.raises(AssertionError):
        observe_policy(cli, 'fixture', policy, {'sandbox_id': 'original'})


@pytest.mark.parametrize('fault', ['identity', 'destination', 'binary'])
def test_unrelated_native_failure_cannot_attribute_endpoint_denial(fault):
    event = {'action_id': 2, 'status_detail': 'transparent_tcp_policy_denied',
             'dst_endpoint': {'domain': 'echo.fixture.svc.cluster.local', 'port': 5678},
             'actor': {'process': {'name': '/usr/bin/curl'}}}
    if fault == 'identity':
        event['status_detail'] = 'transparent_tcp_identity_unavailable'
    elif fault == 'destination':
        event['dst_endpoint']['domain'] = 'other.fixture.svc.cluster.local'
    else:
        event['actor']['process']['name'] = '/bin/sh'
    assert policy_denial_events('timestamp OCSF-JSON ' + json.dumps(event), 'echo.fixture.svc.cluster.local') == []


@pytest.mark.parametrize('error', ['Unavailable: transport failed', 'Unauthenticated: identity rejected', 'Some requested entity was not found: sandbox missing'])
def test_global_lookup_failure_is_not_confirmed_absence(error):
    with pytest.raises(AssertionError):
        global_policy_observation(SimpleNamespace(returncode=1, stdout='', stderr=error))


def test_native_global_policy_absence_is_explicit():
    result = SimpleNamespace(returncode=1, stdout='', stderr="Error: code: 'Some requested entity was not found', message: \"no global policy\n │ revision found\"")
    assert global_policy_observation(result)['state'] == 'absent'


def test_policy_probe_image_uses_only_pinned_sources_and_disjoint_library_authority():
    lines = (ROOT / 'deploy/qualification/policy-image/Dockerfile').read_text().splitlines()
    sources = [line.split()[1] for line in lines if line.startswith('FROM ')]
    curl = LOCK['fixtures']['qualification-probe']
    assert sources == [curl['image'] + '@' + curl['digest'], LOCK['openshell']['images']['workload']]
    filesystem = fixture_policy(False)['filesystem_policy']
    assert '/opt/corsair-curl' in filesystem['read_only']
    assert '/opt' not in filesystem['read_only'] + filesystem['read_write']
    assert '/opt/corsair-denied' not in filesystem['read_only'] + filesystem['read_write']


def test_original_create_identity_survives_a_replaced_get_without_deleting_replacement(tmp_path):
    calls = []
    def cli(*args, **kwargs):
        value = {'id': 'original' if args[:2] == ('sandbox', 'create') else 'replacement'}
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')
    def sdk_call(method, *args, **kwargs):
        calls.append(method)
        return SimpleNamespace(id='replacement')
    record = {}
    with pytest.raises(AssertionError, match='Replacement'):
        with owned_sandbox(SimpleNamespace(evidence=tmp_path), cli, SimpleNamespace(call=sdk_call),
                           {'image': 'fixture@sha256:fixed'}, fixture_policy(False), record):
            pytest.fail('Replaced identity must not be admitted')
    assert record['sandbox_id'] == 'original' and record['cleanup_confirmed'] is False
    assert calls == ['get']


@pytest.mark.parametrize('logs', [
    'Set sandbox setting ocsf_json_enabled=true (revision1)',
    'Setting changed [key:ocsf_json_enabled old:<unset> new:false]\nOCSF JSONL logging toggled',
    'OCSF JSONL logging toggled\nSetting changed [key:ocsf_json_enabled old:<unset> new:true]',
])
def test_stored_disabled_or_old_toggle_does_not_admit_json_evidence(logs):
    assert logging_activation_observed(logs) is False


@pytest.mark.parametrize('explicit_empty', [False, True])
def test_native_empty_egress_serializations_have_the_same_isolation(explicit_empty):
    spec = {'podSelector': {'matchLabels': {'openshell.ai/boundary-role': 'workload'}}, 'policyTypes': ['Ingress', 'Egress']}
    if explicit_empty:
        spec['egress'] = []
    assert workload_fence([{'spec': spec}])['spec'] == spec


@pytest.mark.parametrize('fault', ['allow_all', 'unisolated', 'wrong_role', 'null'])
def test_empty_egress_oracle_rejects_grants_and_missing_isolation(fault):
    spec = {'podSelector': {'matchLabels': {'openshell.ai/boundary-role': 'workload'}}, 'policyTypes': ['Ingress', 'Egress']}
    if fault == 'allow_all':
        spec['egress'] = [{}]
    elif fault == 'unisolated':
        spec['policyTypes'] = ['Ingress']
    elif fault == 'wrong_role':
        spec['podSelector']['matchLabels']['openshell.ai/boundary-role'] = 'supervisor'
    else:
        spec['egress'] = None
    with pytest.raises(AssertionError):
        workload_fence([{'spec': spec}])
