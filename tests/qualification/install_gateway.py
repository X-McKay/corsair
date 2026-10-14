"""Explicit official-chart install, gated by this owned node's native admission."""
import argparse
import json
import os
from pathlib import Path
import uuid

from deploy.openshell.artifacts import CACHE, TOOLS, verify
from tests.qualification.support import ROOT, LOCK, Kubectl, require_owned_cluster, require_platform

STATE = ROOT / '.state/openshell'


def require_admission(kube, path):
    node = require_owned_cluster(kube)
    require_platform(kube)
    prior = Path(path).resolve()
    assert prior.is_relative_to(ROOT / '.runs'), 'Admission evidence must be host-owned'
    scope = json.loads((prior / 'scope.json').read_text())
    report = json.loads((prior / 'admission/admission.json').read_text())
    cleanup = json.loads((prior / 'admission/cleanup.json').read_text())
    assert scope['node_uid'] == node['metadata']['uid'], 'Admission belongs to a different node'
    assert report['storage'] == report['kernel'] == 'passed'
    assert report['native_report']['qualified'] is True
    assert cleanup['confirmed'] and cleanup['pv_confirmed']
    assert (prior / 'runtime-lock.yaml').read_text() == (ROOT / 'deploy/runtime-lock.yaml').read_text(), 'Admission tuple differs'
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission-evidence', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    evidence = ROOT / '.runs/gateway-install' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    kube = Kubectl(ROOT / '.state/kind/kubeconfig', 'kind-corsair', evidence)
    try:
        verify(TOOLS / 'kubectl', LOCK['kubectl']['sha256'])
        verify(TOOLS / 'helm', LOCK['helm']['binary_sha256'])
        verify(TOOLS / 'openshell', LOCK['openshell']['cli']['binary_sha256'])
        verify(CACHE / 'helm-chart.tgz', LOCK['openshell']['chart']['sha256'])
        node = require_admission(kube, args.admission_evidence)
        if STATE.exists() or kube.run('get', 'namespace', 'openshell', '--ignore-not-found', '-o', 'json').stdout.strip():
            raise RuntimeError('Gateway namespace/private ownership already exists; inspect before retry')
        kube.run('create', 'namespace', 'openshell')
        namespace = kube.get('namespace', 'openshell')
        STATE.mkdir(parents=True)
        owner = {'namespace': 'openshell', 'namespace_uid': namespace['metadata']['uid'], 'node_uid': node['metadata']['uid'], 'admission_evidence': str(Path(args.admission_evidence).resolve()), 'evidence': str(evidence)}
        (STATE / 'owner.json').write_text(json.dumps(owner, indent=2))
        (evidence / 'owner.json').write_text(json.dumps(owner, indent=2))
        # Verified archive is the native OCI artifact; avoid floating version resolution.
        # No offline preflight override, atomic rollback or automatic adoption/retry.
        kube.native([str(TOOLS / 'helm'), '--kubeconfig', str(ROOT / '.state/kind/kubeconfig'), '--kube-context', 'kind-corsair', 'install', 'openshell', str(CACHE / 'helm-chart.tgz'), '--namespace', 'openshell', '--values', str(ROOT / 'deploy/openshell/values.yaml'), '--wait', '--timeout', '180s'], timeout=210)
        kube.run('rollout', 'status', 'statefulset/openshell', '-n', 'openshell', '--timeout=120s', timeout=140)
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'identity_qualified': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        # No Secrets, environment exports or Helm release dumps in run evidence.
        for resource in ('pods', 'events', 'pvc'):
            kube.run('get', resource, '-n', 'openshell', '-o', 'json', check=False)
        raise
    finally:
        print(f'Gateway installation evidence: {evidence}')


if __name__ == '__main__':
    main()
