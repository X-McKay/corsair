"""Image-only run of the TAP runner on a real benchmark checkout: the prepared Perl image under Docker, no OpenShell.

Two phases, each its own container. `setup` installs the project's declared CPAN dependencies into a case directory
with network (`cpanm --installdeps --notest`; no project test runs). `run` starts one `--network=none`,
capability-dropped container from the same image and drives `TapRunner` through a Docker-exec workspace and
execution port: per run a fresh copy of the checkout, built offline with its own `Makefile.PL` when it has one,
plus the case's test file as the patch, then listing and execution exactly as SPEC-0061 builds them. This is image
evidence for SPEC-0056 and SPEC-0061, not sandbox qualification.
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
from corsair.adapters.tap_runner import TapRunner, TapRunnerConfig
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PerlTestId, PreparedWorkspace
from tests.qualification.prepare_toolchains import DOCKER

WORK, DEPS = '/tmp/work', '/deps'
PERL = '/usr/local/bin/perl'
# Built distributions load from blib; the project's lib covers a tree without a build step.
COMMAND = (PERL, '-Iblib/lib', '-Iblib/arch', '-Ilib')
# The case's dependencies, installed by setup, are found through the environment, as the environment agent's setup
# would leave them; they are not part of the operator's runner prefix.
ENV = ('-e', 'HOME=/tmp', '-e', f'PERL5LIB={DEPS}/lib/perl5', '-e', 'PERL_MM_USE_DEFAULT=1')


def docker(*args, stdin=None, timeout=900):
    return subprocess.run([*DOCKER, *args], input=stdin, capture_output=True, timeout=timeout, check=False)


def user():
    return f'{os.getuid()}:{os.getgid()}'


def setup(image, checkout, deps, evidence):
    # Only declared prerequisites are installed (the project's own tests are not run: --notest).
    script = (f'cp -R /src {WORK}; cd {WORK}; '
              f'if [ -f cpanfile ] || [ -f Makefile.PL ] || [ -f Build.PL ]; then '
              f'cpanm --notest --installdeps --local-lib-contained {DEPS} .; else echo "no build file"; fi; '
              f'cpanm --version')
    result = docker('run', '--rm', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(), *ENV,
                    '-v', f'{checkout}:/src:ro', '-v', f'{deps}:{DEPS}', image, '/bin/sh', '-ec', script, timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


class DockerCase:
    """One offline container; each prepare is a fresh, built copy of the read-only checkout plus the patch."""

    def __init__(self, image, checkout, deps, commit, timeout, evidence):
        self.image, self.checkout, self.deps, self.commit, self.timeout = image, checkout, deps, commit, timeout
        self.evidence, self.container, self.cleanup = evidence, None, 'unconfirmed'

    def __enter__(self):
        result = docker('run', '-d', '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(),
                        *ENV, '-v', f'{self.checkout}:/src:ro', '-v', f'{self.deps}:{DEPS}:ro', self.image,
                        '/bin/sleep', 'infinity')
        assert result.returncode == 0, result.stderr
        self.container = result.stdout.decode().strip()
        return self

    def __exit__(self, *exc):
        docker('rm', '--force', self.container)
        absent = docker('inspect', self.container)
        self.cleanup = 'confirmed' if absent.returncode != 0 and b'no such object' in absent.stderr.lower() else 'unconfirmed'

    def handle(self, operation):
        return SandboxHandle(self.container, 'perl-image-case', 'docker', 'corsair', str(operation))

    def prepare(self, patch, operation):
        # The build is setup, not a test: a distribution's own Makefile.PL and make, offline, before the patch lands.
        build = docker('exec', self.container, '/bin/sh', '-ec',
                       f'rm -rf {WORK}; cp -R /src {WORK}; cd {WORK}; '
                       f'if [ -f Makefile.PL ]; then {PERL} Makefile.PL && make; fi')
        (self.evidence / f'prepare-{operation}.log').write_bytes(build.stdout + build.stderr)
        assert build.returncode == 0, build.stderr[-2000:]
        for item in patch.files:
            written = docker('exec', '-i', self.container, '/bin/sh', '-ec', 'mkdir -p "$(dirname "$1")"; cat > "$1"',
                             'write', f'{WORK}/{item.path}', stdin=item.content)
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


def run(image, checkout, deps, commit, ids, evidence, test_file, timeout):
    path = PerlTestId.parse(ids[0]).path
    patch = ApprovedPatch((PatchFile(path, Path(test_file).read_bytes()),), (path,))
    config = TapRunnerConfig(command=COMMAND, workspace_root=WORK)
    (evidence / 'objects').mkdir(mode=0o700)
    with DockerCase(image, checkout, deps, commit, timeout, evidence) as case, \
            LocalArtifacts(evidence / 'objects', max_bytes=8 << 20) as store:
        clock = time.monotonic()
        result = TapRunner(case, case, store, config).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                                           discovery_command=config.command, operation=uuid4())
        elapsed = round(time.monotonic() - clock, 3)
    summary = {'image': image, 'commit': commit, 'ids': ids, 'test_file': str(test_file), 'patch_sha256': patch.sha256,
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
    parser.add_argument('--image', required=True, help='Prepared perl526 image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Clean checkout of the case at one commit')
    parser.add_argument('--deps', required=True, type=Path, help='Case dependency directory filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--test-file', type=Path, help='The case test file placed at the ids\' path')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `path/to/file.t#subtest`')
    args = parser.parse_args()
    # Both phases must name the same content, so a tag that could move between them is refused.
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        parser.error('--image must be an image config id (sha256:<64 hex>), not a tag')
    # The receipt names a commit, so the bytes copied into the container must be exactly that commit.
    dirty = subprocess.run(['git', '-C', str(args.checkout), 'status', '--porcelain', '--untracked-files=all', '--ignored'],
                           capture_output=True, text=True, check=True).stdout
    if dirty:
        parser.error(f'{args.checkout} is not a clean checkout of its HEAD commit:\n{dirty[:2000]}')
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(['git', '-C', str(args.checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True).stdout.strip()
    if args.phase == 'setup':
        args.deps.mkdir(parents=True, exist_ok=True)
        code = setup(args.image, args.checkout.resolve(), args.deps.resolve(), args.evidence)
        print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
        raise SystemExit(code)
    summary = run(args.image, args.checkout.resolve(), args.deps.resolve(), commit, tuple(args.id), args.evidence,
                  args.test_file.resolve(), args.timeout)
    print(json.dumps({k: v for k, v in summary.items() if k != 'run'}, indent=2, default=str))


if __name__ == '__main__':
    main()
