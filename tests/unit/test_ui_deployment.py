"""Deployment wiring refuses implicit storage and uses the current operator matrix."""
import os
import subprocess
import sys

import pytest
import yaml

from deploy.ui.render import ROOT, manifests


def rendered(**overrides):
    return manifests(**({'image': 'registry.example/corsair-ui:review',
                         'results_claim': 'retained-results', 'namespace': 'corsair',
                         'public_origin': 'https://corsair.example'} | overrides))


def test_renderer_connects_existing_producer_storage_and_real_matrix():
    config, deployment, service = rendered()
    assert yaml.safe_load(config['data']['runtime-matrix.yaml']) == yaml.safe_load(
        (ROOT / 'deploy/runtime-matrix.yaml').read_text())
    pod = deployment['spec']['template']['spec']
    container = pod['containers'][0]
    volumes = {item['name']: item for item in pod['volumes']}
    mounts = {item['name']: item for item in container['volumeMounts']}
    assert volumes['results']['persistentVolumeClaim'] == {'claimName': 'retained-results', 'readOnly': True}
    assert mounts['results'] == {'name': 'results', 'mountPath': '/data', 'readOnly': True}
    assert container['env'] == [{'name': 'CORSAIR_UI_PUBLIC_ORIGIN', 'value': 'https://corsair.example'}]
    assert container['readinessProbe']['httpGet'] == {
        'path': '/api/ready', 'port': 'http', 'httpHeaders': [{'name': 'Host', 'value': 'corsair.example'}]}
    assert service['spec']['type'] == 'ClusterIP'
    assert container['securityContext']['readOnlyRootFilesystem'] is True
    assert pod['automountServiceAccountToken'] is False
    assert pod['securityContext']['runAsNonRoot'] is True


@pytest.mark.parametrize('argument,value', [
    ('results_claim', ''), ('namespace', '../default'), ('image', 'corsair-ui'),
    ('public_origin', 'https://user:secret@example.com'),
    ('public_origin', 'https://example.com/path'),
    ('public_origin', 'https://example.com:wrong'),
    ('public_origin', 'https://example.com\n'),
])
def test_renderer_refuses_missing_or_unusable_operator_configuration(argument, value):
    with pytest.raises(ValueError):
        rendered(**{argument: value})


def test_renderer_refuses_invalid_runtime_catalog(tmp_path):
    invalid = tmp_path / 'runtime-matrix.yaml'
    invalid.write_text('schema_version: 99\nimages: []\n')
    with pytest.raises(ValueError):
        rendered(runtime_matrix=invalid)


def test_renderer_requires_real_storage_selection():
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/ui/render.py'),
                             '--image', 'corsair-ui:review'], cwd=ROOT,
                            capture_output=True, text=True,
                            env={**os.environ, 'PYTHONPATH': f'{ROOT / "src"}:{ROOT}'})
    assert result.returncode == 2
    assert '--results-claim' in result.stderr
    assert not result.stdout


def test_services_use_operator_addresses_and_existing_tls_secrets():
    _, deployment, _ = rendered(temporal_address='temporal-frontend:7233', temporal_namespace='corsair',
                                temporal_tls_secret='temporal-ui-reader',
                                openshell_endpoint='openshell:8080',
                                openshell_tls_secret='openshell-ui-reader')
    pod = deployment['spec']['template']['spec']
    env = {item['name']: item['value'] for item in pod['containers'][0]['env']}
    volumes = {item['name']: item for item in pod['volumes']}
    assert env['CORSAIR_UI_TEMPORAL_ADDRESS'] == 'temporal-frontend:7233'
    assert env['CORSAIR_UI_TEMPORAL_NAMESPACE'] == 'corsair'
    assert env['CORSAIR_UI_OPENSHELL_ENDPOINT'] == 'openshell:8080'
    assert env['CORSAIR_UI_OPENSHELL_TLS_KEY'] == '/connections/openshell/tls.key'
    assert volumes['openshell-tls']['secret'] == {
        'secretName': 'openshell-ui-reader', 'defaultMode': 0o444,
        'items': [{'key': key, 'path': key} for key in ('ca.crt', 'tls.crt', 'tls.key')]}
    assert 'fsGroup' not in pod['securityContext']  # Never chown the producer's retained results.


@pytest.mark.parametrize('settings', [
    {'openshell_endpoint': 'https://openshell:8080'}, {'openshell_tls_secret': 'reader'},
    {'temporal_tls_secret': 'reader'},
    {'openshell_endpoint': 'https://openshell:8080', 'openshell_tls_secret': 'reader'},
    {'openshell_endpoint': 'openshell', 'openshell_tls_secret': 'reader'}, {'temporal_address': 'service\n:7233'},
    {'temporal_address': 'service:7233', 'temporal_tls_secret': '../reader'},
])
def test_renderer_refuses_partial_service_configuration(settings):
    with pytest.raises(ValueError):
        rendered(**settings)
