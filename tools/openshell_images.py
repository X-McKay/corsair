"""Prepare the installed OpenShell gateway for the v2 OpenShell sandbox backend (docs/runbooks/openshell-v2.md).

    make openshell-images-load   # load runtime-matrix images into the owned kind node; .state/openshell/images.json
    make openshell-config        # client mTLS, loopback port-forward, CLI check; .state/openshell/config.json
    make openshell-forward-stop  # stop the recorded port-forward

All three run after `make openshell-install` on the owned `corsair` cluster. Every native command's receipt lands under
.runs/openshell-images/<id>/, .runs/openshell-config/<id>/ or .runs/openshell-forward/<id>/. Credential bytes stay in
private .state/openshell/ files; receipts and evidence carry only their paths.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import uuid

import yaml

from deploy.openshell.artifacts import TOOLS, verify
from tests.qualification.gateway import export_client
from tests.qualification.install_gateway import STATE, require_admission
from tests.qualification.support import LOCK, ROOT, Kubectl

MATRIX = ROOT / 'deploy/v2/runtime-matrix.yaml'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
NODE = 'corsair-control-plane'
IMAGES = STATE / 'images.json'
CONFIG = STATE / 'config.json'
FORWARD = STATE / 'port-forward.json'
CLI_HOME = STATE / 'cli'
GATEWAY = 'corsair'
WORKSPACE = 'default'
POLICIES = ROOT / 'policies/openshell/v2'
LIMITS = {'ready_seconds': 300, 'delete_seconds': 120}


def matrix_images(path=MATRIX):
    """Distinct `image` values of the runtime matrix, in row order."""
    rows = yaml.safe_load(path.read_text())['rows']
    return list(dict.fromkeys(row['image'] for row in rows))


def reference(tag):
    """Docker's normalized repository and tag for a local image tag (`corsair-java:abc` ->
    (`docker.io/library/corsair-java`, `abc`)); the name kind's containerd import gives it."""
    if '@' in tag:
        raise ValueError(f'Expected a local tag, not a digest reference: {tag}')
    slash, colon = tag.rfind('/'), tag.rfind(':')
    repository, version = (tag[:colon], tag[colon + 1:]) if colon > slash else (tag, 'latest')
    first = repository.split('/')[0]
    if '/' not in repository:
        repository = 'docker.io/library/' + repository
    elif not ('.' in first or ':' in first or first == 'localhost'):
        repository = 'docker.io/' + repository
    return repository, version


def ctr_rows(kube):
    rows = kube.native(DOCKER + ['exec', NODE, 'ctr', '-n', 'k8s.io', 'images', 'list']).stdout.splitlines()
    return [row.split() for row in rows[1:] if row.split()]


def require_gateway(kube):
    """The gateway this checkout installed, on this owned node, from this checkout's own admission evidence."""
    if not (STATE / 'owner.json').is_file():
        raise RuntimeError('No gateway ownership in .state/openshell; run make openshell-install first')
    owner = json.loads((STATE / 'owner.json').read_text())
    node = require_admission(kube, owner['admission_evidence'])
    if kube.get('namespace', 'openshell')['metadata']['uid'] != owner['namespace_uid']:
        raise RuntimeError('Gateway namespace replaced; refusing to use it')
    return node, owner


def load(kube, evidence):
    node, _ = require_gateway(kube)
    verify(TOOLS / 'kind', LOCK['kind']['sha256'])
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ}
    env['KIND_EXPERIMENTAL_PROVIDER'] = 'docker'
    mapping, loaded, missing = {}, [], []
    for tag in matrix_images():
        found = kube.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', tag], check=False)
        if found.returncode:
            if 'no such' not in found.stderr.lower():
                raise RuntimeError(f'Cannot establish local image {tag}: {found.stderr[-500:]}')
            missing.append(tag)
            continue
        local_id = found.stdout.strip()
        repository, version = reference(tag)
        kube.native([str(TOOLS / 'kind'), 'load', 'docker-image', tag, '--name', 'corsair'], env=env, timeout=600)
        rows = ctr_rows(kube)
        row = [r for r in rows if r[0] == f'{repository}:{version}']
        if len(row) != 1:
            raise RuntimeError(f'Loaded image {tag} not listed once in the node containerd')
        digest = row[0][2]
        data = kube.native(DOCKER + ['exec', NODE, 'ctr', '-n', 'k8s.io', 'content', 'get', digest]).stdout.encode()
        if 'sha256:' + hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f'Node content for {tag} does not hash to its manifest digest')
        manifest = json.loads(data)
        # The Docker image ID is the config digest (classic store) or the manifest/index digest (containerd store).
        if local_id not in (manifest.get('config', {}).get('digest'), digest):
            raise RuntimeError(f'Node image {tag} differs from the local Docker image {local_id}')
        pinned = f'{repository}@{digest}'
        if not any(r[0] == pinned for r in rows):
            kube.native(DOCKER + ['exec', NODE, 'ctr', '-n', 'k8s.io', 'images', 'tag', f'{repository}:{version}', pinned])
        if [r[2] for r in ctr_rows(kube) if r[0] == pinned] != [digest]:
            raise RuntimeError(f'Digest reference {pinned} not resolvable in the node')
        mapping[tag] = pinned
        loaded.append({'tag': tag, 'local_id': local_id, 'manifest_digest': digest, 'image': pinned})
    if not mapping:
        raise RuntimeError(f'No runtime-matrix image is present in local Docker (missing: {missing}); '
                           'run make toolchain-images first')
    IMAGES.write_text(json.dumps(mapping, indent=2) + '\n')
    IMAGES.chmod(0o600)
    (evidence / 'images.json').write_text(json.dumps(mapping, indent=2) + '\n')
    (evidence / 'load.json').write_text(json.dumps({'node_uid': node['metadata']['uid'], 'loaded': loaded,
                                                    'missing_locally': missing}, indent=2))
    for tag in missing:
        print(f'Not in local Docker, not loaded: {tag}')
    return mapping


def process_argv(pid):
    try:
        return Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    except FileNotFoundError:
        return None


def stop_forward(evidence):
    """Stop the recorded port-forward only when its pid still runs the exact recorded argv."""
    if not FORWARD.is_file():
        return {'recorded': False}
    record = json.loads(FORWARD.read_text())
    receipt = {'recorded': True, 'pid': record['pid'], 'confirmed': False}
    try:
        current = process_argv(record['pid'])
        if current is None:
            receipt['already_exited'] = True
        elif current != record['argv']:
            raise RuntimeError('Recorded port-forward pid now runs another command; refusing to signal it')
        else:
            os.kill(record['pid'], 15)
            deadline = time.monotonic() + 10
            while process_argv(record['pid']) == record['argv']:
                if time.monotonic() > deadline:
                    raise RuntimeError('Port-forward did not exit within 10 seconds')
                time.sleep(.2)
        FORWARD.unlink()
        receipt['confirmed'] = True
        return receipt
    finally:
        (evidence / 'forward-stop.json').write_text(json.dumps(receipt, indent=2))


def start_forward(kube, port):
    """A detached loopback-only port-forward to the gateway service; it outlives this command."""
    if not port:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
    argv =kube.argv + ['port-forward', '-n', 'openshell', 'svc/openshell', '--address=127.0.0.1', f'{port}:8080']
    log_path = STATE / 'port-forward.log'
    with log_path.open('w') as log:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    deadline = time.monotonic() + 15
    while True:
        if process.poll() is not None:
            raise RuntimeError(f'Port-forward exited ({process.returncode}); see {log_path}')
        if f'Forwarding from 127.0.0.1:{port}' in log_path.read_text():
            break
        if time.monotonic() > deadline:
            process.terminate()
            raise RuntimeError('Port-forward readiness unknown after 15 seconds; terminated')
        time.sleep(.2)
    record = {'pid': process.pid, 'argv': argv, 'port': port, 'started_at': datetime.now(timezone.utc).isoformat()}
    FORWARD.write_text(json.dumps(record, indent=2))
    return record


def configure(kube, evidence, port):
    node, owner = require_gateway(kube)
    cli = TOOLS / 'openshell'
    verify(cli, LOCK['openshell']['cli']['binary_sha256'])
    gateway = kube.get('statefulset', 'openshell', '-n', 'openshell')
    if gateway['status'].get('readyReplicas') != 1:
        raise RuntimeError('Gateway statefulset is not Ready')
    if gateway['spec']['template']['spec']['containers'][0]['image'] != LOCK['openshell']['images']['gateway']:
        raise RuntimeError('Gateway image differs from the runtime lock')
    if not IMAGES.is_file():
        raise RuntimeError('No .state/openshell/images.json; run make openshell-images-load first')
    stop_forward(evidence)
    # Fresh private CLI state each time: the CLI reads the client identity from <XDG_CONFIG_HOME>/openshell/gateways.
    if CLI_HOME.exists():
        shutil.rmtree(CLI_HOME)
    mtls = CLI_HOME / 'openshell/gateways' / GATEWAY / 'mtls'
    export_client(kube, mtls)
    forward = start_forward(kube, port)
    endpoint = f"127.0.0.1:{forward['port']}"
    cli_env = {'XDG_CONFIG_HOME': str(CLI_HOME)}
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ} | cli_env
    kube.native([str(cli), 'gateway', 'add', 'https://' + endpoint, '--local', '--name', GATEWAY], env=env)
    status = json.loads(kube.native([str(cli), '--gateway', GATEWAY, '--workspace', WORKSPACE, 'status', '-o', 'json'],
                                    env=env).stdout)
    (evidence / 'native-status.json').write_text(json.dumps(status, indent=2))
    if status.get('status') != 'connected' or status.get('authentication', {}).get('status') != 'authenticated':
        raise RuntimeError('Pinned CLI did not connect and authenticate through the port-forward')
    if status.get('version') != LOCK['openshell']['version'].removeprefix('v'):
        raise RuntimeError('Gateway version differs from the runtime lock')
    state_dir = STATE / 'environments'
    state_dir.mkdir(mode=0o700, exist_ok=True)
    config = {
        'endpoint': endpoint,
        'ca': str(mtls / 'ca.crt'), 'cert': str(mtls / 'tls.crt'), 'key': str(mtls / 'tls.key'),
        'workspace': WORKSPACE,
        'gateway': GATEWAY,
        'cli': {'path': str(cli), 'sha256': LOCK['openshell']['cli']['binary_sha256']},
        'cli_env': cli_env,
        'images': str(IMAGES),
        'policies': {name: str(POLICIES / f'{name}.yaml') for name in ('none', 'build')},
        'state_dir': str(state_dir),
        'limits': LIMITS,
    }
    CONFIG.write_text(json.dumps(config, indent=2) + '\n')
    CONFIG.chmod(0o600)
    (evidence / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (evidence / 'port-forward.json').write_text(json.dumps(forward, indent=2))
    (evidence / 'scope.json').write_text(json.dumps({
        'node_uid': node['metadata']['uid'], 'gateway_namespace_uid': owner['namespace_uid'],
        'admission_evidence': owner['admission_evidence'],
        'policies_present': {name: Path(path).is_file() for name, path in config['policies'].items()},
        'backend_qualified': False}, indent=2))
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('load', 'config', 'stop'))
    parser.add_argument('--port', type=int, default=0, help='Local port-forward port (config; default: a free one)')
    args = parser.parse_args()
    os.umask(0o077)
    names = {'load': 'openshell-images', 'config': 'openshell-config', 'stop': 'openshell-forward'}
    evidence = ROOT / '.runs' / names[args.action] / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    kube = Kubectl(ROOT / '.state/kind/kubeconfig', 'kind-corsair', evidence)
    try:
        if args.action == 'load':
            load(kube, evidence)
        elif args.action == 'config':
            configure(kube, evidence, args.port)
        else:
            stop_forward(evidence)
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'backend_qualified': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        raise
    finally:
        print(f'{names[args.action]} evidence: {evidence}')


if __name__ == '__main__':
    main()
