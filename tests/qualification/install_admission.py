"""Explicit operator prerequisite installation into the owned local kind cluster."""
import json
import os
import uuid

import yaml

from deploy.openshell.artifacts import CACHE, verify, storage_manifest, agent_sandbox_kustomization
from tests.qualification.support import Kubectl, ROOT, LOCK, require_owned_cluster, require_platform


def main():
    os.umask(0o077)
    evidence = ROOT / '.runs/admission-install' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    (evidence / 'runtime-lock.yaml').write_text((ROOT / 'deploy/runtime-lock.yaml').read_text())
    kube = Kubectl(ROOT / '.state/kind/kubeconfig', 'kind-corsair', evidence)
    try:
        verify(ROOT / '.tools' / LOCK['platform'] / 'kubectl', LOCK['kubectl']['sha256'])
        verify(CACHE / 'sandbox.yaml', LOCK['agent_sandbox']['sha256'])
        verify(CACHE / 'kind-storage.go', LOCK['storage']['sha256'])
        # Regenerate/check the render inputs; a cache edit cannot select other images.
        if (CACHE / 'storage.yaml').read_text() != storage_manifest():
            raise RuntimeError('Storage render differs from pinned upstream source')
        if yaml.safe_load((CACHE / 'kustomization.yaml').read_text()) != yaml.safe_load(agent_sandbox_kustomization()):
            raise RuntimeError('Agent Sandbox render configuration differs from selected core manifest')
        rendered = kube.run('kustomize', CACHE).stdout
        documents = yaml.safe_load_all(rendered)
        deployment = next(d for d in documents if d['kind'] == 'Deployment')
        if deployment['spec']['template']['spec']['containers'][0]['image'] != LOCK['agent_sandbox']['controller_image']:
            raise RuntimeError('Agent Sandbox render differs from pinned image')
        node = require_owned_cluster(kube)
        require_platform(kube)
        (evidence / 'scope.json').write_text(json.dumps({'node_uid': node['metadata']['uid'], 'gateway_installed': False}))
        # No upgrade/adoption of an existing Agent Sandbox installation.
        existing = kube.run('get', 'crd', 'sandboxes.agents.x-k8s.io', '--ignore-not-found', '-o', 'json').stdout
        namespace = kube.run('get', 'namespace', 'agent-sandbox-system', '--ignore-not-found', '-o', 'json').stdout
        if existing.strip() or namespace.strip():
            raise RuntimeError('Agent Sandbox already exists; inspect prior receipts before retrying')
        # kind initially owns these through client-side apply. Use that same
        # native path for image pinning; do not seize SSA ownership by force.
        kube.run('apply', '-f', CACHE / 'storage.yaml')
        kube.run('rollout', 'status', 'deployment/local-path-provisioner', '-n', 'local-path-storage', '--timeout=180s', timeout=200)
        kube.run('apply', '--server-side', '--field-manager=corsair-admission', '-k', CACHE)
        kube.run('wait', '--for=condition=Established', 'crd/sandboxes.agents.x-k8s.io', '--timeout=60s')
        kube.run('rollout', 'status', 'deployment/agent-sandbox-controller', '-n', 'agent-sandbox-system', '--timeout=180s', timeout=200)
        for args in [('deployment', 'agent-sandbox-controller', '-n', 'agent-sandbox-system'), ('crd', 'sandboxes.agents.x-k8s.io'), ('storageclass', 'standard')]:
            kube.get(*args)
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'runtime_admitted': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        kube.run('get', 'pods', '-n', 'agent-sandbox-system', '-o', 'json', check=False)
        kube.run('get', 'events', '-n', 'agent-sandbox-system', '-o', 'json', check=False)
        raise
    finally:
        print(f'Prerequisite installation evidence: {evidence}')


if __name__ == '__main__':
    main()
