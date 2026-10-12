"""Fail-closed setup observations; mocks never qualify a Service route."""
import json
from types import SimpleNamespace

import pytest

from tests.qualification import support


@pytest.fixture
def setup_observation(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(support.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(support.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    endpoint = {'addresses': ['192.0.2.1'], 'targetRef': {'uid': 'pod'}, 'conditions': {'ready': True}}
    item = {'metadata': {'ownerReferences': [{'kind': 'Service', 'uid': 'service'}]},
            'ports': [{'name': '', 'protocol': 'TCP', 'port': 5678}], 'endpoints': [endpoint]}
    client = SimpleNamespace(evidence=tmp_path, counter=0)
    markers, requests = [], []
    responses = []
    def get(resource, *args, **kwargs):
        client.counter += 1
        return {'items': [] if resource == 'networkpolicies' else [item]}
    def run(*args, **kwargs):
        client.counter += 1
        return SimpleNamespace(stdout=' '.join(markers))
    client.get, client.run = get, run
    f = support.NetworkFixture(client, 'setup')
    f.uid = 'namespace'
    f.endpoints = {'pod': '192.0.2.1', 'service': '198.51.100.1'}
    def request(probe, address, method, **kwargs):
        requests.append(probe)
        client.counter += 1
        marker = f'marker-{len(requests)}'
        markers.append(marker)
        code, output = responses.pop(0) if responses else (0, 'corsair-network-ok\n\nSTATUS:200')
        return SimpleNamespace(returncode=code, stdout=output, stderr='native failure'), marker
    f.request = request
    return f, endpoint, item, responses, requests


def receipt(fixture):
    return json.loads((fixture.evidence / 'service-readiness.json').read_text())


def test_setup_transients_are_retained_and_never_relax_fresh_controls(setup_observation):
    f, _, _, responses, requests = setup_observation
    responses.extend([(7, '\nSTATUS:000'), (28, '\nSTATUS:000')])
    f.wait_service('pod', 'service')
    r = receipt(f)
    assert r['ready'] and [a['requests'][0]['exit_code'] for a in r['attempts']] == [7, 28, 0]
    assert requests[-2:] == ['probe-allowed', 'probe-denied']
    responses.append((7, '\nSTATUS:000'))
    with pytest.raises(AssertionError, match='Expected reachable control'):
        f.allowed('probe-allowed')
    assert len(requests) == 5  # Strict control fails immediately, no convergence.


@pytest.mark.parametrize('invalid', ['not_ready', 'pod_replaced', 'service_replaced'])
def test_missing_readiness_or_replacement_cannot_admit_requests(setup_observation, invalid):
    f, endpoint, item, _, requests = setup_observation
    if invalid == 'not_ready':
        endpoint['conditions']['ready'] = False
        message = 'did not converge'
    elif invalid == 'pod_replaced':
        endpoint['targetRef']['uid'] = 'replacement'
        message = 'Pod identity changed'
    else:
        item['metadata']['ownerReferences'][0]['uid'] = 'replacement'
        message = 'Service identity changed'
    with pytest.raises(AssertionError, match=message):
        f.wait_service('pod', 'service')
    assert not receipt(f)['ready'] and not requests


@pytest.mark.parametrize('response', [(1, ''), (7, 'exec error'), (0, 'wrong server\nSTATUS:200')])
def test_unexpected_exec_or_http_output_is_not_retried(setup_observation, response):
    f, _, _, responses, requests = setup_observation
    responses.append(response)
    with pytest.raises(AssertionError, match='Unexpected Service setup'):
        f.wait_service('pod', 'service')
    assert not receipt(f)['ready'] and len(requests) == 1


def test_unknown_delivery_stops_setup_and_retains_unready_receipt(setup_observation):
    f, _, _, _, _ = setup_observation
    calls = []
    def unknown(*args, **kwargs):
        calls.append(args)
        raise RuntimeError('Native command timed out; remote completion unknown')
    f.request = unknown
    with pytest.raises(RuntimeError, match='completion unknown'):
        f.wait_service('pod', 'service')
    assert len(calls) == 1 and not receipt(f)['ready']


def test_permanent_connection_failure_exhausts_setup_without_admission(setup_observation):
    f, _, _, responses, requests = setup_observation
    responses.extend([(7, '\nSTATUS:000')] * 121)
    with pytest.raises(AssertionError, match='did not converge'):
        f.wait_service('pod', 'service')
    r = receipt(f)
    assert not r['ready'] and r['elapsed_seconds'] == 30
    assert requests and all(a['requests'][0]['exit_code'] == 7 for a in r['attempts'])


def test_empty_endpoint_slice_cannot_admit_requests(setup_observation):
    f, _, item, _, requests = setup_observation
    item['endpoints'] = None
    item['ports'] = None  # Native controller publishes this empty startup shape.
    with pytest.raises(AssertionError, match='did not converge'):
        f.wait_service('pod', 'service')
    assert not receipt(f)['ready'] and not requests


def test_setup_rejects_existing_policy_before_sending_traffic(setup_observation):
    f, _, _, _, requests = setup_observation
    f.kube.get = lambda *args, **kwargs: {'items': [{'metadata': {'name': 'unexpected-policy'}}]}
    with pytest.raises(AssertionError, match='requires no policies'):
        f.wait_service('pod', 'service')
    assert not receipt(f)['ready'] and not requests


def test_successful_http_without_server_marker_cannot_admit(setup_observation):
    f, _, _, _, requests = setup_observation
    f.kube.run = lambda *args, **kwargs: SimpleNamespace(stdout='uncovered log')
    with pytest.raises(AssertionError, match='log coverage missing'):
        f.wait_service('pod', 'service')
    assert not receipt(f)['ready'] and len(requests) == 2
