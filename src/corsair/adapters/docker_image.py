"""Image-only Docker route: a prepared toolchain image under plain Docker standing in for the sandbox workspace and
execution ports, capabilities dropped, offline except for an explicitly networked setup container. Image evidence,
not sandbox qualification (SPEC-0062 lighter path); OpenShell remains the qualified route.
"""
import hashlib
import json
import os
import subprocess
import time

from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import PreparedWorkspace

DOCKER = ['docker', '--host=unix:///var/run/docker.sock']


class SetupMismatch(ValueError):
    """A dependency directory without a successful setup receipt for this image, commit and lockfiles."""


WORK = '/tmp/work'
HARDENED = ('--cap-drop=ALL', '--security-opt=no-new-privileges')


def docker(*args, stdin=None, timeout=900):
    return subprocess.run([*DOCKER, *args], input=stdin, capture_output=True, timeout=timeout, check=False)


def user():
    return f'{os.getuid()}:{os.getgid()}'


def commit_tree(checkout, destination, commit='HEAD'):
    """Write `commit`'s blobs exactly as committed (regular files, executables, symlinks) into `destination`.

    The receipt names a commit, so the container gets that commit's blobs, never the worktree's bytes (which local
    edits, untracked files or checkout filters such as EOL conversion and `ident` can change).
    """
    git = ['git', '-C', str(checkout)]
    listing = subprocess.run([*git, 'ls-tree', '-r', '-z', commit], capture_output=True, check=True).stdout
    entries = [line.split(b'\t', 1) for line in listing.split(b'\0') if line]
    entries = [(*meta.split(b' '), os.fsdecode(path)) for meta, path in entries]
    unsupported = [path for mode, kind, _, path in entries if kind != b'blob']
    if unsupported:
        raise ValueError(f'{checkout}: submodules are not supported: {unsupported[:5]}')
    batch = subprocess.run([*git, 'cat-file', '--batch'], input=b''.join(sha + b'\n' for _, _, sha, _ in entries),
                           capture_output=True, check=True).stdout
    offset = 0
    for mode, _, sha, path in entries:
        header_end = batch.index(b'\n', offset)
        name, _, size = batch[offset:header_end].split(b' ')
        if name != sha:
            raise RuntimeError(f'cat-file returned {name!r} for {sha!r}')
        start = header_end + 1
        data, offset = batch[start:start + int(size)], start + int(size) + 1
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == b'120000':
            target.symlink_to(os.fsdecode(data))
        else:
            target.write_bytes(data)
            target.chmod(0o755 if mode == b'100755' else 0o644)
    return destination


# Written by a language's setup phase into its dependency directory; `run` checks it before anything runs.
SETUP_RECEIPT = 'corsair-setup.json'


def sha256(path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_setup(directory, record: dict) -> None:
    """Record what a dependency directory was set up for (image, commit, lockfile digest, exit)."""
    (directory / SETUP_RECEIPT).write_text(json.dumps(record, indent=2))


def require_setup(directory, expected: dict) -> dict:
    """The dependencies must be the ones a successful setup produced for this image, commit and lockfile, never
    another's: every expected field, recomputed now, must equal the receipt's."""
    try:
        receipt = json.loads((directory / SETUP_RECEIPT).read_text())
    except (OSError, ValueError) as error:
        raise SetupMismatch(f'{directory}: no successful setup receipt ({error})')
    if receipt.get('exit') != 0 or any(receipt.get(key) != value for key, value in expected.items()):
        raise SetupMismatch(f'{directory}: set up for {receipt}, not for {expected}')
    return receipt


class DockerCase:
    """One offline container; each prepare is a fresh copy of the read-only checkout, the offline build, then the patch.

    `mounts` are (host, container) read-only pairs besides the checkout at /src; `build` is the language's offline
    build script run in the copy before the patch lands (setup, not a test); `scratch` are container paths `prepare`
    recreates and `release` removes besides the workspace. `network` is `none` for every test run; only a setup
    sandbox (the environment stage's) is given registry access.
    """

    def __init__(self, image, checkout, commit, timeout, *, kind, docker, mounts=(), env=(), build='', copies='',
                 scratch=(), evidence=None, network='none'):
        self.image, self.checkout, self.commit, self.timeout, self.kind = image, checkout, commit, timeout, kind
        self.network = network
        self.docker, self.mounts, self.env, self.build, self.copies = docker, mounts, env, build, copies
        self.scratch, self.evidence, self.container, self.cleanup = scratch, evidence, None, 'unconfirmed'

    def __enter__(self):
        volumes = [arg for host, target in ((self.checkout, '/src'), *self.mounts) for arg in ('-v', f'{host}:{target}:ro')]
        environment = [arg for pair in self.env for arg in ('-e', pair)]
        result = self.docker('run', '-d', f'--network={self.network}', *HARDENED, '--user', user(), *environment, *volumes,
                             self.image, '/bin/sleep', 'infinity')
        if result.returncode != 0:
            raise RuntimeError(f'docker run failed: {result.stderr[-2000:]!r}')
        self.container = result.stdout.decode().strip()
        return self

    def __exit__(self, *exc):
        self.docker('rm', '--force', self.container)
        absent = self.docker('inspect', self.container)
        self.cleanup = 'confirmed' if absent.returncode != 0 and b'no such object' in absent.stderr.lower() else 'unconfirmed'

    def handle(self, operation):
        return SandboxHandle(self.container, self.kind, 'docker', 'corsair', str(operation))

    def prepare(self, patch, operation):
        script = f'rm -rf {WORK} {" ".join(self.scratch)}; cp -R /src {WORK}; {self.copies}'
        if self.build:
            script += f'cd {WORK}; {self.build}'
        built = self.docker('exec', self.container, '/bin/sh', '-ec', script)
        if self.evidence is not None:
            (self.evidence / f'prepare-{operation}.log').write_bytes(built.stdout + built.stderr)
        if built.returncode != 0:
            raise RuntimeError(f'workspace preparation failed: {built.stderr[-2000:]!r}')
        for item in patch.files:
            written = self.docker('exec', '-i', self.container, '/bin/sh', '-ec', 'mkdir -p "$(dirname "$1")"; cat > "$1"',
                                  'write', f'{WORK}/{item.path}', stdin=item.content)
            if written.returncode != 0:
                raise RuntimeError(f'patch write failed for {item.path}: {written.stderr[-2000:]!r}')
        digest = lambda text: ArtifactRef(hashlib.sha256(text.encode()).hexdigest(), len(text))
        return PreparedWorkspace(self.handle(operation), digest(self.commit), digest(patch.sha256), patch.sha256)

    def release(self, workspace, operation):
        removed = self.docker('exec', self.container, '/bin/rm', '-rf', WORK, *self.scratch)
        return 'confirmed' if removed.returncode == 0 else 'unconfirmed'

    def stop_workers(self):
        """After a timed-out exec: killing the docker client leaves its process running in the container, so kill every
        process but PID 1 (`sleep infinity`), then confirm only PID 1 is left. Never retried."""
        try:
            self.docker('exec', self.container, '/bin/sh', '-c', 'kill -9 -1', timeout=30)
            listed = self.docker('top', self.container, '-o', 'pid', timeout=30)
        except subprocess.TimeoutExpired:
            return 'unconfirmed'
        pids = listed.stdout.decode(errors='replace').split()[1:] if listed.returncode == 0 else None
        return 'confirmed' if pids is not None and len(pids) == 1 else 'unconfirmed'

    def execute(self, handle, argv, operation):
        started, clock = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), time.monotonic()
        # A hang (for example a vulnerable infinite loop) is a terminal-unknown failure, never retried; its processes
        # are killed before the container is reused, and the container is removed with everything in it on exit.
        try:
            result = self.docker('exec', '-w', WORK, self.container, *argv, timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                    elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                    completion='unknown', reason='timeout', stdout=error.stdout or b'',
                                    stderr=error.stderr or b'', native_exit=None, worker_cleanup=self.stop_workers())
        return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                completion='terminal_observed', reason='terminal', stdout=result.stdout,
                                stderr=result.stderr, native_exit=result.returncode, worker_cleanup='confirmed')
