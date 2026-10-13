"""Image-only run of the Maven runner on a real benchmark checkout: the prepared toolchain image under Docker, no OpenShell.

Two phases, each its own container. `setup` resolves the project's own dependencies and Surefire provider into a
case Maven repository with network (no test body runs: Surefire selects an absent test). `run` starts one
`--network=none`, capability-dropped container from the same image and drives `MavenRunner` through a Docker-exec
workspace and execution port: a fresh copy of the checkout per run, the unchanged test file as the patch, listing and
execution exactly as SPEC-0041 builds them. This is image evidence for SPEC-0045, not sandbox qualification.
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
from corsair.adapters.maven_runner import MavenRunner, MavenRunnerConfig
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, JavaTestId, PatchFile, PreparedWorkspace
from tests.qualification.prepare_toolchains import DOCKER, LAUNCHER

WORK, M2 = '/tmp/work', '/tmp/m2'
MVN = '/usr/share/maven/bin/mvn'
DEPENDENCY = 'org.apache.maven.plugins:maven-dependency-plugin:3.8.1'


def docker(*args, stdin=None, timeout=900):
    return subprocess.run([*DOCKER, *args], input=stdin, capture_output=True, timeout=timeout, check=False)


def user():
    return f'{os.getuid()}:{os.getgid()}'


def setup(image, checkout, m2, evidence):
    # Surefire resolves its JUnit provider only when it runs a test, so the absent-test run leaves it out; fetch the
    # providers of the project's own Surefire version (read from Maven's execution banner) without running a body.
    script = (f'cp -R /opt/corsair-m2/. /m2/; cp -R /src {WORK}; cd {WORK}; '
              f'{MVN} -B -ntp -C -Dmaven.repo.local=/m2 test-compile {DEPENDENCY}:build-classpath '
              f'-Dmdep.outputFile=target/corsair-setup.classpath -Dmdep.includeScope=test; '
              f'{MVN} -B -ntp -C -Dmaven.repo.local=/m2 test -Dtest=CorsairSetupAbsentTest -DfailIfNoTests=false '
              f'-Dsurefire.failIfNoSpecifiedTests=false > /tmp/absent.log 2>&1 || {{ cat /tmp/absent.log; exit 4; }}; '
              'cat /tmp/absent.log; '
              "version=$(sed -n 's/.*surefire\\(-plugin\\)\\{0,1\\}:\\([0-9][^:]*\\):test .*/\\2/p' /tmp/absent.log | head -1); "
              'test -n "$version" || { echo "no surefire:test execution found" >&2; exit 3; }; echo "surefire version $version"; '
              'resolved=0; for provider in surefire-junit4 surefire-junit47 surefire-junit-platform; do '
              f'if {MVN} -B -ntp -C -Dmaven.repo.local=/m2 {DEPENDENCY}:get -Dartifact=org.apache.maven.surefire:$provider:$version; '
              'then resolved=$((resolved + 1)); else echo "provider $provider:$version not resolved"; fi; done; '
              # Not every provider exists for every version (junit-platform starts at 2.22.0); none at all is a failure.
              'test "$resolved" -gt 0 || { echo "no Surefire provider resolved for $version" >&2; exit 5; }')
    result = docker('run', '--rm', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(), '-e', 'HOME=/tmp', '-v', f'{checkout}:/src:ro', '-v', f'{m2}:/m2',
                    image, '/bin/sh', '-ec', script, timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


class DockerCase:
    """One offline container; each prepare is a fresh copy of the read-only checkout plus the patch."""

    def __init__(self, image, checkout, m2, commit, timeout):
        self.image, self.checkout, self.m2, self.commit, self.timeout = image, checkout, m2, commit, timeout
        self.container = None

    def __enter__(self):
        result = docker('run', '-d', '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user', user(),
                        '-e', 'HOME=/tmp', '-v', f'{self.checkout}:/src:ro', '-v', f'{self.m2}:/m2:ro', self.image,
                        '/bin/sleep', 'infinity')
        assert result.returncode == 0, result.stderr
        self.container = result.stdout.decode().strip()
        return self

    def __exit__(self, *exc):
        docker('rm', '--force', self.container)
        absent = docker('inspect', self.container)
        self.cleanup = 'confirmed' if absent.returncode != 0 and b'no such object' in absent.stderr.lower() else 'unconfirmed'

    def handle(self, operation):
        return SandboxHandle(self.container, 'java-image-case', 'docker', 'corsair', str(operation))

    def prepare(self, patch, operation):
        copy = docker('exec', self.container, '/bin/sh', '-ec', f'rm -rf {WORK} {M2}; cp -R /src {WORK}; cp -R /m2 {M2}')
        assert copy.returncode == 0, copy.stderr
        for item in patch.files:
            written = docker('exec', '-i', self.container, '/bin/sh', '-ec', 'cat > "$1"', 'write', f'{WORK}/{item.path}',
                             stdin=item.content)
            assert written.returncode == 0, written.stderr
        digest = lambda text: ArtifactRef(hashlib.sha256(text.encode()).hexdigest(), len(text))
        return PreparedWorkspace(self.handle(operation), digest(self.commit), digest(patch.sha256), patch.sha256)

    def release(self, workspace, operation):
        return 'confirmed' if docker('exec', self.container, '/bin/rm', '-rf', WORK, M2).returncode == 0 else 'unconfirmed'

    def execute(self, handle, argv, operation):
        started, clock = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), time.monotonic()
        # A hang (for example a vulnerable infinite loop) is a terminal-unknown failure, never retried; the
        # container is removed with everything in it on exit.
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


def run(image, checkout, m2, commit, ids, evidence, tests_from, timeout):
    item = JavaTestId.parse(ids[0])
    path = item.source_path()
    # The test file comes from `tests_from` (for example the fix revision's PoV test applied to the vulnerable one).
    patch = ApprovedPatch((PatchFile(path, (Path(tests_from) / path).read_bytes()),), (path,))
    config = MavenRunnerConfig(command=(MVN, '-B', '-ntp', '-o', f'-Dmaven.repo.local={M2}', f'--file={WORK}/pom.xml'),
                               workspace_root=WORK, java='/opt/java/openjdk/bin/java', console_jar=LAUNCHER)
    # LocalArtifacts opens an existing root and never creates it.
    (evidence / 'objects').mkdir(mode=0o700)
    with DockerCase(image, checkout, m2, commit, timeout) as case, LocalArtifacts(evidence / 'objects', max_bytes=8 << 20) as store:
        clock = time.monotonic()
        result = MavenRunner(case, case, store, config).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                                             discovery_command=config.command, operation=uuid4())
        elapsed = round(time.monotonic() - clock, 3)
    summary = {'image': image, 'commit': commit, 'ids': ids, 'tests_from': str(tests_from), 'patch_sha256': patch.sha256, 'elapsed_seconds': elapsed, 'container_cleanup': case.cleanup,
               'failure_layer': result.failure_layer, 'detail': result.detail, 'cleanup': result.cleanup,
               'discovery': result.discovery and {'status': result.discovery.status, 'test_ids': result.discovery.test_ids},
               'cases': result.execution and [(c.test_id, c.outcome) for c in result.execution.cases],
               'run': plain(result)}
    (evidence / 'run.json').write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared toolchain image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Clean checkout of the case at one commit')
    parser.add_argument('--m2', required=True, type=Path, help='Case Maven repository filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--tests-from', type=Path, help='Checkout supplying the test file (default: --checkout)')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `[module/]pkg.Class#method`')
    args = parser.parse_args()
    # Both phases must name the same content, so a tag that could move between them is refused.
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        parser.error('--image must be an image config id (sha256:<64 hex>), not a tag')
    # The receipt names a commit, so the bytes copied into the container must be exactly that commit.
    for checkout in {args.checkout, args.tests_from or args.checkout}:
        dirty = subprocess.run(['git', '-C', str(checkout), 'status', '--porcelain', '--untracked-files=all', '--ignored'],
                               capture_output=True, text=True, check=True).stdout
        if dirty:
            parser.error(f'{checkout} is not a clean checkout of its HEAD commit:\n{dirty[:2000]}')
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(['git', '-C', str(args.checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True).stdout.strip()
    if args.phase == 'setup':
        args.m2.mkdir(parents=True, exist_ok=True)
        code = setup(args.image, args.checkout.resolve(), args.m2.resolve(), args.evidence)
        print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
        raise SystemExit(code)
    summary = run(args.image, args.checkout.resolve(), args.m2.resolve(), commit, tuple(args.id), args.evidence,
                  (args.tests_from or args.checkout).resolve(), args.timeout)
    print(json.dumps({k: v for k, v in summary.items() if k != 'run'}, indent=2, default=str))


if __name__ == '__main__':
    main()
