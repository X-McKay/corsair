"""Render a read-only UI deployment against explicitly selected existing storage.

No cluster mutations, storage provisioning, fixture insertion or public ingress.
Run with the repository environment and PYTHONPATH=src:.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import yaml

from corsair.nodes.runtime.matrix import Matrix

ROOT = Path(__file__).resolve().parents[2]


def manifests(*, image: str, results_claim: str, namespace: str, public_origin: str,
              runtime_matrix: Path = ROOT / 'deploy/runtime-matrix.yaml',
              temporal_address: str | None = None, temporal_namespace: str = 'default',
              temporal_tls_secret: str | None = None, openshell_endpoint: str | None = None,
              openshell_tls_secret: str | None = None) -> list[dict]:
    for label, value in (('namespace', namespace), ('results claim', results_claim)):
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
            raise ValueError(f'{label} must be a Kubernetes DNS label')
    if not image or re.search(r'\s', image) or not (':' in image.rsplit('/', 1)[-1] or '@sha256:' in image):
        raise ValueError('image must include an explicit tag or digest')
    if any(ord(char) < 33 or ord(char) > 126 for char in public_origin):
        raise ValueError('public origin must contain only visible ASCII characters')
    origin = urlsplit(public_origin)
    if (origin.scheme not in ('http', 'https') or not origin.hostname or origin.username
            or origin.password or origin.path or origin.query or origin.fragment):
        raise ValueError('public origin must be an http(s) origin without credentials, path, query or fragment')
    # Trigger validation of an invalid port before emitting an unusable manifest.
    _ = origin.port
    if bool(openshell_endpoint) != bool(openshell_tls_secret):
        raise ValueError('OpenShell endpoint and TLS secret must be configured together')
    if temporal_tls_secret and not temporal_address:
        raise ValueError('Temporal TLS secret requires a Temporal address')
    service_env, service_volumes, service_mounts = [], [], []
    for service, address, secret in (('temporal', temporal_address, temporal_tls_secret),
                                     ('openshell', openshell_endpoint, openshell_tls_secret)):
        if not address:
            continue
        if any(ord(char) < 33 or ord(char) > 126 for char in address):
            raise ValueError('Service addresses must contain only visible ASCII characters')
        target = urlsplit('//' + address)
        if (not target.hostname or target.username or target.password or target.path
                or target.query or target.fragment or target.port is None or target.port == 0):
            raise ValueError('Native service addresses must be host:port, without a URL scheme or credentials')
        setting = 'ADDRESS' if service == 'temporal' else 'ENDPOINT'
        service_env.append({'name': f'CORSAIR_UI_{service.upper()}_{setting}', 'value': address})
        if service == 'temporal':
            if not temporal_namespace or any(ord(char) < 32 for char in temporal_namespace):
                raise ValueError('Temporal namespace must be nonempty without control characters')
            service_env.append({'name': 'CORSAIR_UI_TEMPORAL_NAMESPACE', 'value': temporal_namespace})
        if secret:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', secret):
                raise ValueError('TLS secret must be a Kubernetes DNS subdomain')
            mount = f'/connections/{service}'
            name = f'{service}-tls'
            service_volumes.append({'name': name, 'secret': {'secretName': secret, 'defaultMode': 0o444,
                'items': [{'key': key, 'path': key} for key in ('ca.crt', 'tls.crt', 'tls.key')]}})
            service_mounts.append({'name': name, 'mountPath': mount, 'readOnly': True})
            service_env.extend({'name': f'CORSAIR_UI_{service.upper()}_TLS_{setting}',
                                'value': f'{mount}/{filename}'}
                               for setting, filename in (('CA', 'ca.crt'), ('CERT', 'tls.crt'), ('KEY', 'tls.key')))
    matrix_text = runtime_matrix.read_text(encoding='utf-8')
    Matrix.model_validate(yaml.safe_load(matrix_text))
    digest = hashlib.sha256(matrix_text.encode()).hexdigest()
    labels = {'app.kubernetes.io/name': 'corsair-ui'}
    metadata = {'name': 'corsair-ui', 'namespace': namespace, 'labels': labels}
    probe = lambda path: {'httpGet': {'path': path, 'port': 'http', 'httpHeaders': [
        {'name': 'Host', 'value': origin.netloc}]}, 'timeoutSeconds': 5, 'periodSeconds': 10}
    return [
        {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': metadata,
         'data': {'runtime-matrix.yaml': matrix_text}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': metadata,
         'spec': {'replicas': 1, 'selector': {'matchLabels': labels},
                  'template': {'metadata': {'labels': labels, 'annotations': {
                      'corsair.dev/runtime-matrix-sha256': digest}}, 'spec': {
                      'automountServiceAccountToken': False,
                      'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001,
                                          'runAsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
                      'containers': [{
                          'name': 'ui', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                          'ports': [{'name': 'http', 'containerPort': 8765}],
                          'env': [{'name': 'CORSAIR_UI_PUBLIC_ORIGIN', 'value': public_origin}, *service_env],
                          'securityContext': {'allowPrivilegeEscalation': False,
                                              'readOnlyRootFilesystem': True,
                                              'capabilities': {'drop': ['ALL']}},
                          'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                                        'limits': {'cpu': '1', 'memory': '512Mi'}},
                          'startupProbe': {**probe('/api/live'), 'failureThreshold': 12},
                          'livenessProbe': probe('/api/live'),
                          'readinessProbe': probe('/api/ready'),
                          'volumeMounts': [
                              {'name': 'results', 'mountPath': '/data', 'readOnly': True},
                              {'name': 'runtime-matrix', 'mountPath': '/config', 'readOnly': True},
                              {'name': 'tmp', 'mountPath': '/tmp'}, *service_mounts],
                      }],
                      'volumes': [
                          {'name': 'results', 'persistentVolumeClaim': {
                              'claimName': results_claim, 'readOnly': True}},
                          {'name': 'runtime-matrix', 'configMap': {'name': 'corsair-ui'}},
                          {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '32Mi'}}, *service_volumes],
                  }}}},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': metadata,
         'spec': {'type': 'ClusterIP', 'selector': labels,
                  'ports': [{'name': 'http', 'port': 8765, 'targetPort': 'http'}]}},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Built UI image tag or immutable digest available to the cluster')
    parser.add_argument('--results-claim', required=True, help='Existing producer PVC containing evals/<agent>/<run>')
    parser.add_argument('--namespace', required=True, help='Existing namespace containing the results PVC')
    parser.add_argument('--public-origin', required=True, help='Exact browser origin, e.g. http://localhost:8765 for port-forward')
    parser.add_argument('--runtime-matrix', type=Path, default=ROOT / 'deploy/runtime-matrix.yaml')
    parser.add_argument('--temporal-address', help='Native Temporal address, e.g. temporal-frontend:7233')
    parser.add_argument('--temporal-namespace', default='default')
    parser.add_argument('--temporal-tls-secret', help='Existing Secret with ca.crt, tls.crt and tls.key')
    parser.add_argument('--openshell-endpoint', help='Native OpenShell gateway host:port (TLS is required), e.g. openshell:8080')
    parser.add_argument('--openshell-tls-secret', help='Existing Secret with ca.crt, tls.crt and tls.key')
    args = parser.parse_args()
    try:
        documents = manifests(**vars(args))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    yaml.safe_dump_all(documents, sys.stdout, sort_keys=False)


if __name__ == '__main__':
    main()
