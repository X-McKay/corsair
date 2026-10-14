"""Fetch checksum-locked prerequisites and render the official chart; no install."""
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import tarfile
import time
import uuid

import yaml

from deploy.kind.bootstrap import ROOT, LOCK, TOOLS, download

CACHE = ROOT / '.cache/openshell-admission'


def verify(path, checksum):
    if not path.is_file():
        raise RuntimeError(f'Required artifact missing: {path}')
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise RuntimeError(f'Artifact checksum mismatch: {path}')


def reviewed_render(text):
    """Keep offline chart evidence without generated Secret material."""
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        raise RuntimeError('Offline chart YAML could not be safely parsed; output withheld') from None
    for document in documents:
        if document and document.get('kind') == 'Secret':
            for field in ('data', 'stringData'):
                if field in document:
                    document[field] = {key: '<redacted>' for key in document[field]}
    return yaml.safe_dump_all(documents)


def storage_manifest():
    verify(CACHE / 'kind-storage.go', LOCK['storage']['sha256'])
    storage = (CACHE / 'kind-storage.go').read_text().split('const defaultStorageManifest = `\n', 1)[1].rsplit('`', 1)[0]
    storage = storage.replace('` + storageProvisionerImage + `', LOCK['storage']['provisioner_image'])
    storage = storage.replace('` + storageHelperImage + `', LOCK['storage']['helper_image'])
    if '`' in storage:
        raise RuntimeError('Unexpected kind storage source format')
    return storage


def agent_sandbox_kustomization():
    return yaml.safe_dump({
        'apiVersion': 'kustomize.config.k8s.io/v1beta1',
        'kind': 'Kustomization', 'resources': ['sandbox.yaml'],
        'images': [{'name': 'registry.k8s.io/agent-sandbox/agent-sandbox-controller',
                    'newName': 'registry.k8s.io/agent-sandbox/agent-sandbox-controller',
                    'digest': LOCK['agent_sandbox']['controller_image'].split('@')[1]}],
    })


def helm_command(args, evidence, name, redact=False):
    argv = [str(TOOLS / 'helm'), '--registry-config', str(ROOT / '.state/helm/registry.json'), *args]
    receipt = {'argv': argv, 'started_at': datetime.now(timezone.utc).isoformat(), 'secret_fields_redacted': redact}
    started = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        receipt.update(exit_code=result.returncode, stderr=result.stderr,
                       stdout=reviewed_render(result.stdout) if redact and result.returncode == 0 else ('' if redact else result.stdout))
    except subprocess.TimeoutExpired as error:
        # Incomplete render YAML cannot safely be parsed for Secret redaction.
        receipt.update(timed_out=True, completion='unknown',
                       stdout='' if redact else (error.stdout or b'').decode(),
                       stderr=(error.stderr or b'').decode())
        raise RuntimeError('Native Helm timed out; completion unknown; inspect receipt') from error
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - started
        (evidence / f'{name}.json').write_text(json.dumps(receipt, indent=2))
    if result.returncode:
        raise RuntimeError(f'Native Helm failed ({result.returncode}): {result.stderr}')
    return result


def main():
    os.umask(0o077)
    CACHE.mkdir(parents=True, exist_ok=True)
    evidence = ROOT / '.runs/artifacts' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    (evidence / 'runtime-lock.yaml').write_text((ROOT / 'deploy/runtime-lock.yaml').read_text())
    try:
        download(LOCK['helm'], CACHE / 'helm.tar.gz')
        with tarfile.open(CACHE / 'helm.tar.gz') as archive:
            binary = archive.extractfile('linux-amd64/helm').read()
        if hashlib.sha256(binary).hexdigest() != LOCK['helm']['binary_sha256']:
            raise RuntimeError('Helm binary checksum mismatch')
        TOOLS.mkdir(parents=True, exist_ok=True)
        (TOOLS / 'helm').write_bytes(binary)
        (TOOLS / 'helm').chmod(0o755)
        download(LOCK['openshell']['cli'], CACHE / 'cli.tar.gz')
        with tarfile.open(CACHE / 'cli.tar.gz') as archive:
            cli = archive.extractfile('openshell').read()
        if hashlib.sha256(cli).hexdigest() != LOCK['openshell']['cli']['binary_sha256']:
            raise RuntimeError('OpenShell CLI binary checksum mismatch')
        (TOOLS / 'openshell').write_bytes(cli)
        (TOOLS / 'openshell').chmod(0o755)
        download(LOCK['agent_sandbox'], CACHE / 'sandbox.yaml')
        download(LOCK['storage'], CACHE / 'kind-storage.go')
        # Render kind's own native storage constant, replacing only image pins.
        (CACHE / 'storage.yaml').write_text(storage_manifest())
        (CACHE / 'kustomization.yaml').write_text(agent_sandbox_kustomization())
        chart = LOCK['openshell']['chart']
        package = CACHE / 'helm-chart.tgz'
        if not package.exists() or hashlib.sha256(package.read_bytes()).hexdigest() != chart['sha256']:
            reference = f"oci://{chart['registry']}/{chart['repository']}@{chart['manifest_digest']}"
            destination = CACHE / ('chart-pull-' + uuid.uuid4().hex)
            destination.mkdir()
            result = helm_command(['pull', reference, '--destination', str(destination)], evidence, 'pull')
            if 'Digest: ' + chart['manifest_digest'] not in result.stderr + result.stdout:
                raise RuntimeError('Native Helm pull did not report the selected OCI digest')
            # Digest pulls use a digest-derived filename. Accept exactly one
            # native output in this new directory and verify its bytes.
            pulled = list(destination.glob('*.tgz'))
            if len(pulled) != 1:
                raise RuntimeError('Expected one native Helm chart archive')
            verify(pulled[0], chart['sha256'])
            pulled[0].replace(package)
            destination.rmdir()
        verify(package, chart['sha256'])
        result = helm_command(['template', 'openshell', str(package), '--namespace', 'openshell', '--values', str(ROOT / 'deploy/openshell/values.yaml'), '--set', 'agentSandbox.preflight.enabled=false'], evidence, 'render', redact=True)
        rendered = reviewed_render(result.stdout)
        (CACHE / 'rendered.yaml').write_text(rendered)
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'live_qualification': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        raise
    finally:
        print(f'Artifact/render evidence: {evidence}')


if __name__ == '__main__':
    main()
