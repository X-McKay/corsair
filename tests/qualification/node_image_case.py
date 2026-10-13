"""Image-only run of the Jest runner on a real benchmark checkout: the prepared node8 image under Docker, no OpenShell.

Two phases, each its own container. `setup` installs the project's own dependencies from its lockfile with network
(`npm ci --ignore-scripts`; no test runs) into a case directory. `run` starts one `--network=none`,
capability-dropped container from the same image and drives `JestRunner` through a Docker-exec workspace and
execution port: a fresh copy of the checkout and its installed dependencies per run, the test file as the patch,
listing and execution exactly as SPEC-0057 builds them. This is image evidence for SPEC-0055/SPEC-0057, not
sandbox qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from uuid import uuid4

from corsair.adapters.jest_runner import JestRunner, JestRunnerConfig
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, JsTestId, PatchFile, PreparedWorkspace
from tests.qualification.java_image_case import commit_tree, docker, plain, user
from tests.qualification.prepare_toolchains import NPM

WORK = '/tmp/work'
JEST = ('/usr/local/bin/node', 'node_modules/jest/bin/jest.js', '--ci')
# Passed through to setup only when the host needs them to reach the registry (a proxy and its CA file).
SETUP_ENV = ('HTTPS_PROXY', 'https_proxy', 'NODE_EXTRA_CA_CERTS')


def setup(image, checkout, modules, evidence):
    npm = ' '.join(NPM)
    script = f'cp -R /src {WORK}; cd {WORK}; {npm} --cache /tmp/npm ci; cp -R {WORK}/node_modules /modules/'
    env = [arg for key in SETUP_ENV if os.environ.get(key) for arg in ('-e', f'{key}={os.environ[key]}')]
    ca = os.environ.get('NODE_EXTRA_CA_CERTS')
    mounts = ['-v', f'{ca}:{ca}:ro'] if ca else []
    result = docker('run', '--rm', '--network=host' if env else '--network=bridge', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--user', user(), '-e', 'HOME=/tmp', *env, *mounts,
                    '-v', f'{checkout}:/src:ro', '-v', f'{modules}:/modules', image, '/bin/sh', '-ec', script, timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


class DockerCase:
    """One offline container; each prepare is a fresh copy of the read-only checkout, its dependencies and the patch."""

    def __init__(self, image, checkout, modules, commit, timeout):
        self.image, self.checkout, self.modules, self.commit, self.timeout = image, checkout, modules, commit, timeout
        self.container = None

    def __enter__(self):
        result = docker('run', '-d', '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(),
                        '-e', 'HOME=/tmp', '-v', f'{self.checkout}:/src:ro', '-v', f'{self.modules}:/modules:ro', self.image,
                        '/bin/sleep', 'infinity')
        assert result.returncode == 0, result.stderr
        self.container = result.stdout.decode().strip()
        return self

    def __exit__(self, *exc):
        docker('rm', '--force', self.container)
        absent = docker('inspect', self.container)
        self.cleanup = 'confirmed' if absent.returncode != 0 and b'no such object' in absent.stderr.lower() else 'unconfirmed'

    def handle(self, operation):
        return SandboxHandle(self.container, 'node-image-case', 'docker', 'corsair', str(operation))

    def prepare(self, patch, operation):
        copy = docker('exec', self.container, '/bin/sh', '-ec', f'rm -rf {WORK}; cp -R /src {WORK}; cp -R /modules/node_modules {WORK}/')
        assert copy.returncode == 0, copy.stderr
        for item in patch.files:
            written = docker('exec', '-i', self.container, '/bin/sh', '-ec', 'cat > "$1"', 'write', f'{WORK}/{item.path}',
                             stdin=item.content)
            assert written.returncode == 0, written.stderr
        digest = lambda text: ArtifactRef(hashlib.sha256(text.encode()).hexdigest(), len(text))
        return PreparedWorkspace(self.handle(operation), digest(self.commit), digest(patch.sha256), patch.sha256)

    def release(self, workspace, operation):
        return 'confirmed' if docker('exec', self.container, '/bin/rm', '-rf', WORK).returncode == 0 else 'unconfirmed'

    def execute(self, handle, argv, operation):
        started, clock = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), time.monotonic()
        try:
            result = docker('exec', '-w', WORK, self.container, *argv, timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            # Terminal-unknown, never retried; the container is removed with everything in it on exit.
            return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                    elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                    completion='unknown', reason='timeout', stdout=error.stdout or b'',
                                    stderr=error.stderr or b'', native_exit=None, worker_cleanup='unconfirmed')
        return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                completion='terminal_observed', reason='terminal', stdout=result.stdout,
                                stderr=result.stderr, native_exit=result.returncode, worker_cleanup='confirmed')


RECEIPT = 'corsair-setup.json'


def setup_identity(image, checkout, commit):
    """What a dependency directory was installed for: the commit, the image and the lockfile it installed."""
    lock = checkout / 'package-lock.json'
    return {'commit': commit, 'image': image,
            'package_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None}


def run(image, checkout, modules, commit, ids, evidence, test_file, timeout):
    # The dependencies must be the ones setup installed for this commit's lockfile in this image, never another's.
    try:
        receipt = json.loads((modules / RECEIPT).read_text())
    except (OSError, ValueError) as error:
        raise SystemExit(f'{modules}: no successful setup receipt ({error})')
    if receipt != dict(setup_identity(image, checkout, commit), exit=0):
        raise SystemExit(f'{modules}: set up for {receipt}, not for this commit, image and lockfile')
    path = JsTestId.parse(ids[0]).path
    patch = ApprovedPatch((PatchFile(path, Path(test_file).read_bytes()),), (path,))
    config = JestRunnerConfig(command=JEST, workspace_root=WORK, report_path='/tmp/corsair-jest.json')
    (evidence / 'objects').mkdir(mode=0o700)
    with DockerCase(image, checkout, modules, commit, timeout) as case, LocalArtifacts(evidence / 'objects', max_bytes=8 << 20) as store:
        clock = time.monotonic()
        result = JestRunner(case, case, store, config).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                                           discovery_command=config.command, operation=uuid4())
        elapsed = round(time.monotonic() - clock, 3)
    summary = {'image': image, 'commit': commit, 'setup_receipt': receipt, 'ids': ids, 'test_file': str(test_file), 'patch_sha256': patch.sha256,
               'elapsed_seconds': elapsed, 'container_cleanup': case.cleanup, 'failure_layer': result.failure_layer,
               'detail': result.detail, 'cleanup': result.cleanup,
               'discovery': result.discovery and {'status': result.discovery.status, 'test_ids': result.discovery.test_ids},
               'cases': result.execution and [(c.test_id, c.outcome, c.failure and plain(c.failure)) for c in result.execution.cases],
               'run': plain(result)}
    (evidence / 'run.json').write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared node8 image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Checkout of the case; its HEAD commit is what runs')
    parser.add_argument('--modules', required=True, type=Path, help='Case dependency directory; setup creates it and refuses an existing one')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--test-file', type=Path, help='Test file placed at the ids\' path as the patch')
    parser.add_argument('--timeout', type=int, default=600, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `path::[suite::]name`')
    args = parser.parse_args()
    # Both phases must name the same content, so a tag that could move between them is refused.
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        parser.error('--image must be an image config id (sha256:<64 hex>), not a tag')
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(['git', '-C', str(args.checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True).stdout.strip()
    # The receipt names a commit, so the container gets that commit's blobs, never the worktree's bytes (as #74 does
    # for the Java harness).
    with tempfile.TemporaryDirectory(dir=args.evidence) as scratch:
        tree = commit_tree(args.checkout, Path(scratch).resolve() / 'checkout')
        if args.phase == 'setup':
            # A fresh directory per setup: copying into an existing tree would mix two commits' dependency closures.
            args.modules.mkdir(parents=True, exist_ok=False)
            code = setup(args.image, tree, args.modules.resolve(), args.evidence)
            if code == 0:
                identity = dict(setup_identity(args.image, tree, commit), exit=0)
                (args.modules / RECEIPT).write_text(json.dumps(identity, indent=2))
            print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
            raise SystemExit(code)
        summary = run(args.image, tree, args.modules.resolve(), commit, tuple(args.id), args.evidence,
                      args.test_file.resolve(), args.timeout)
    print(json.dumps({k: v for k, v in summary.items() if k != 'run'}, indent=2, default=str))


if __name__ == '__main__':
    main()
