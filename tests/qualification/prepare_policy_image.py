"""Explicit native preparation of the tiny local 1D canary image; no registry push."""
import argparse
import hashlib
import json
import os
import uuid

from tests.qualification.support import ROOT, LOCK, Kubectl, require_owned_cluster

DOCKERFILE = ROOT / 'deploy/qualification/policy-image/Dockerfile'
CACHE = ROOT / '.cache/policy-image'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
CLIENT = LOCK['fixtures']['qualification-probe']['image'] + '@' + LOCK['fixtures']['qualification-probe']['digest']


def image_receipt():
    receipt = json.loads((CACHE / 'image.json').read_text())
    assert receipt['dockerfile_sha256'] == hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()
    assert receipt['base'] == LOCK['openshell']['images']['workload']
    assert receipt['client'] == CLIENT
    assert receipt['image'].endswith('@' + receipt['manifest_digest'])
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'load'])
    args = parser.parse_args()
    os.umask(0o077)
    evidence = ROOT / '.runs/policy-image' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    kube = Kubectl(ROOT / '.state/kind/kubeconfig', 'kind-corsair', evidence)
    try:
        if args.action == 'build':
            assert not CACHE.exists(), 'Existing artifact: inspect its receipt rather than rebuilding silently'
            CACHE.mkdir(parents=True)
            source_hash = hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()
            tag = 'docker.io/library/corsair-policy:' + source_hash[:16]
            kube.native(DOCKER + ['pull', LOCK['openshell']['images']['workload']], timeout=180)
            kube.native(DOCKER + ['pull', CLIENT], timeout=180)
            kube.native(DOCKER + ['build', '--network=none', '--pull=false', '--tag', tag, str(DOCKERFILE.parent)], timeout=180)
            config_id = kube.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', tag]).stdout.strip()
            # Trusted DAC/content control, without host mounts, network or credentials.
            command = 'stat -c "%a %u %g" /opt/corsair-denied/readable /opt/corsair-readonly/writable; cat /opt/corsair-denied/readable; printf "trusted-write\\n" > /opt/corsair-readonly/writable; cat /opt/corsair-readonly/writable; test -x /usr/bin/curl; readlink -f /usr/bin/curl; /usr/bin/curl --version'
            cidfile = evidence / 'control-container.id'
            try:
                control = kube.native(DOCKER + ['run', '--rm', '--cidfile', str(cidfile), '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=10001:10001', config_id, '/bin/sh', '-ec', command])
                assert control.stdout.startswith('444 0 0\n666 0 0\ncorsair-readable-canary\ntrusted-write\n/usr/bin/curl\ncurl 8.14.1 ')
            finally:
                cleanup = {'confirmed': False}
                try:
                    identity = cleanup['container_id'] = cidfile.read_text().strip()
                    current = kube.native(DOCKER + ['inspect', '--format', '{{.Id}} {{.Image}}', identity], check=False)
                    if current.returncode == 0:
                        assert current.stdout.strip() == identity + ' ' + config_id, 'Control identity differs; refusing cleanup'
                        kube.native(DOCKER + ['rm', '--force', identity])
                    absent = kube.native(DOCKER + ['inspect', '--format', '{{.Id}}', identity], check=False)
                    assert absent.returncode != 0 and 'no such object' in absent.stderr.lower(), 'Control container cleanup unconfirmed'
                    cleanup['confirmed'] = True
                finally:
                    (evidence / 'control-cleanup.json').write_text(json.dumps(cleanup, indent=2))
            (CACHE / 'build.json').write_text(json.dumps({'tag': tag, 'config_id': config_id, 'base': LOCK['openshell']['images']['workload'], 'client': CLIENT, 'dockerfile_sha256': source_hash, 'evidence': str(evidence)}, indent=2))
        else:
            node = require_owned_cluster(kube)
            build = json.loads((CACHE / 'build.json').read_text())
            assert build['dockerfile_sha256'] == hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest()
            assert build['base'] == LOCK['openshell']['images']['workload']
            assert build['client'] == CLIENT
            assert kube.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', build['tag']]).stdout.strip() == build['config_id']
            env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ}
            env['KIND_EXPERIMENTAL_PROVIDER'] = 'docker'
            kube.native([str(ROOT / '.tools/linux-amd64/kind'), 'load', 'docker-image', build['tag'], '--name', 'corsair'], env=env, timeout=120)
            rows = kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'images', 'list']).stdout.splitlines()
            row = [line.split() for line in rows if line.split()[0] == build['tag']]
            assert len(row) == 1 and row[0][2].startswith('sha256:')
            digest = row[0][2]
            manifest_bytes = kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'content', 'get', digest]).stdout.encode()
            assert 'sha256:' + hashlib.sha256(manifest_bytes).hexdigest() == digest
            assert json.loads(manifest_bytes)['config']['digest'] == build['config_id'], 'Loaded artifact config differs from trusted build'
            image = 'docker.io/library/corsair-policy@' + digest
            # Native local image alias is the exact content-addressed manifest.
            kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'images', 'tag', build['tag'], image])
            receipt = dict(build, manifest_digest=digest, image=image)
            if (CACHE / 'image.json').exists():
                assert receipt == image_receipt(), 'Fresh cluster loaded a different artifact'
            else:
                (CACHE / 'image.json').write_text(json.dumps(receipt, indent=2))
            (evidence / 'load.json').write_text(json.dumps(dict(receipt, node_uid=node['metadata']['uid']), indent=2))
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'runtime_qualified': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        raise
    finally:
        print(f'Policy artifact evidence: {evidence}')


if __name__ == '__main__':
    main()
