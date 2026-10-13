"""Image-only run of the Minitest runner on a real benchmark checkout: the prepared toolchain image under Docker, no OpenShell.

Two phases, each its own container. `setup` resolves the project's own gems with Bundler into a case bundle directory
with network (no test runs) and keeps the resolved `Gemfile.lock` there. `run` starts one `--network=none`,
capability-dropped container from the same image and drives `MinitestRunner` through a Docker-exec workspace and
execution port: a fresh copy of the checkout plus that lockfile per run, the overlay test file as the patch, listing
and execution exactly as SPEC-0063 builds them. This is image evidence, not sandbox qualification.
"""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.minitest_runner import MinitestRunner, MinitestRunnerConfig
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PreparedWorkspace, RubyTestId
from tests.qualification.prepare_toolchains import DOCKER

WORK, GEMS = '/tmp/work', '/bundle/gems'
BUNDLE = '/usr/local/bin/bundle'


def docker(*args, stdin=None, timeout=900):
    return subprocess.run([*DOCKER, *args], input=stdin, capture_output=True, timeout=timeout, check=False)


def user():
    return f'{os.getuid()}:{os.getgid()}'


def setup(image, checkout, bundle, evidence, docker_args):
    # The project's default groups, as `bundle install` resolves them; optional groups stay out.
    script = (f'cp -R /src {WORK}; cd {WORK}; BUNDLE_PATH={GEMS} {BUNDLE} install --jobs 4; '
              f'cp {WORK}/Gemfile.lock /bundle/Gemfile.lock')
    result = docker('run', '--rm', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(), '-e', 'HOME=/tmp',
                    *docker_args, '-v', f'{checkout}:/src:ro', '-v', f'{bundle}:/bundle', image, '/bin/sh', '-ec', script,
                    timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


class DockerCase:
    """One offline container; each prepare is a fresh copy of the read-only checkout, the setup lockfile and the patch."""

    def __init__(self, image, checkout, bundle, commit, timeout):
        self.image, self.checkout, self.bundle, self.commit, self.timeout = image, checkout, bundle, commit, timeout
        self.container = None

    def __enter__(self):
        result = docker('run', '-d', '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(),
                        '-e', 'HOME=/tmp', '-v', f'{self.checkout}:/src:ro', '-v', f'{self.bundle}:/bundle:ro', self.image,
                        '/bin/sleep', 'infinity')
        assert result.returncode == 0, result.stderr
        self.container = result.stdout.decode().strip()
        return self

    def __exit__(self, *exc):
        docker('rm', '--force', self.container)
        absent = docker('inspect', self.container)
        self.cleanup = 'confirmed' if absent.returncode != 0 and b'no such object' in absent.stderr.lower() else 'unconfirmed'

    def handle(self, operation):
        return SandboxHandle(self.container, 'ruby-image-case', 'docker', 'corsair', str(operation))

    def prepare(self, patch, operation):
        copy = docker('exec', self.container, '/bin/sh', '-ec', f'rm -rf {WORK}; cp -R /src {WORK}; cp /bundle/Gemfile.lock {WORK}/')
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
        # A hang is a terminal-unknown failure, never retried; the container is removed with everything in it on exit.
        try:
            result = docker('exec', '-w', WORK, self.container, *argv, timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                    elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                    completion='unknown', reason='timeout', stdout=error.stdout or b'',
                                    stderr=error.stderr or b'', native_exit=None, worker_cleanup='unconfirmed')
        return ExecutionReceipt(operation=str(operation), handle=handle, started_at=started,
                                elapsed_seconds=round(time.monotonic() - clock, 3), delivery='acknowledged',
                                completion='terminal_observed', reason='terminal', stdout=result.stdout,
                                stderr=result.stderr, native_exit=result.returncode, worker_cleanup='confirmed')


def plain(value):
    if dataclasses.is_dataclass(value):
        return {k: plain(v) for k, v in dataclasses.asdict(value).items()}
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, bytes):
        text = value.decode('utf-8', 'replace')
        return {'sha256': hashlib.sha256(value).hexdigest(), 'size': len(value), 'tail': text[-4000:]}
    return value


def run(image, checkout, bundle, commit, ids, evidence, tests_from, includes, timeout):
    path = RubyTestId.parse(ids[0]).path
    patch = ApprovedPatch((PatchFile(path, (Path(tests_from) / path).read_bytes()),), (path,))
    config = MinitestRunnerConfig(command=('/usr/bin/env', 'BUNDLE_FROZEN=true', f'BUNDLE_PATH={GEMS}', BUNDLE, 'exec',
                                           '/usr/local/bin/ruby', *(f'-I{item}' for item in includes)),
                                  workspace_root=WORK)
    # LocalArtifacts opens an existing root and never creates it.
    (evidence / 'objects').mkdir(mode=0o700)
    with DockerCase(image, checkout, bundle, commit, timeout) as case, LocalArtifacts(evidence / 'objects', max_bytes=8 << 20) as store:
        clock = time.monotonic()
        result = MinitestRunner(case, case, store, config).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                                               discovery_command=config.command, operation=uuid4())
        elapsed = round(time.monotonic() - clock, 3)
    summary = {'image': image, 'commit': commit, 'ids': ids, 'tests_from': str(tests_from), 'patch_sha256': patch.sha256,
               'elapsed_seconds': elapsed, 'container_cleanup': case.cleanup, 'failure_layer': result.failure_layer,
               'detail': result.detail, 'cleanup': result.cleanup,
               'discovery': result.discovery and {'status': result.discovery.status, 'test_ids': result.discovery.test_ids},
               'cases': result.execution and [(c.test_id, c.outcome) for c in result.execution.cases],
               'run': plain(result)}
    (evidence / 'run.json').write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared ruby31 image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Clean checkout of the case at one commit')
    parser.add_argument('--bundle', required=True, type=Path, help='Case bundle directory filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--tests-from', type=Path, help='Committed directory supplying the test file (default: --checkout)')
    parser.add_argument('--include', action='append', default=[], help='Repository-relative `-I` directory (repeatable)')
    parser.add_argument('--setup-docker-arg', action='append', default=[], help='Extra `docker run` argument for setup only')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `path.rb::Class#test_method`')
    args = parser.parse_args()
    # Both phases must name the same content, so a tag that could move between them is refused (as #74 does for Java).
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        parser.error('--image must be an image config id (sha256:<64 hex>), not a tag')
    # The receipt names a commit, so the bytes copied into the container must be exactly what is committed; the
    # pathspec scopes the check to the directory, which for --tests-from may be an overlay inside this repository.
    for directory in {args.checkout, args.tests_from or args.checkout}:
        dirty = subprocess.run(['git', '-C', str(directory), 'status', '--porcelain', '--untracked-files=all', '--ignored', '--', '.'],
                               capture_output=True, text=True, check=True).stdout
        if dirty:
            parser.error(f'{directory} is not clean at its HEAD commit:\n{dirty[:2000]}')
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(['git', '-C', str(args.checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True).stdout.strip()
    if args.phase == 'setup':
        args.bundle.mkdir(parents=True, exist_ok=True)
        code = setup(args.image, args.checkout.resolve(), args.bundle.resolve(), args.evidence, args.setup_docker_arg)
        print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
        raise SystemExit(code)
    summary = run(args.image, args.checkout.resolve(), args.bundle.resolve(), commit, tuple(args.id), args.evidence,
                  (args.tests_from or args.checkout).resolve(), args.include, args.timeout)
    print(json.dumps({k: v for k, v in summary.items() if k != 'run'}, indent=2, default=str))


if __name__ == '__main__':
    main()
