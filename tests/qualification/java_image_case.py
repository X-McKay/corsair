"""Image-only run of the Maven runner on a real benchmark checkout: the prepared toolchain image under Docker, no OpenShell.

Two phases, each its own container. `setup` resolves the project's own dependencies and Surefire provider into a
case Maven repository with network (no test body runs: Surefire selects an absent test). `run` starts one
`--network=none`, capability-dropped container from the same image and drives `MavenRunner` through a Docker-exec
workspace and execution port: a fresh copy of the checkout per run, the unchanged test file as the patch, listing and
execution exactly as SPEC-0041 builds them. This is image evidence for SPEC-0045, not sandbox qualification.
"""
import argparse
import json
from pathlib import Path
import tempfile

from corsair.adapters.maven_runner import MavenRunner, MavenRunnerConfig
from corsair.ports.test_runner import JavaTestId
from tests.qualification.image_case import (WORK, DockerCase, commit_tree, docker, drive, head, print_summary,
                                            require_image_id, tests_patch, user)
from tests.qualification.prepare_toolchains import LAUNCHER

M2 = '/tmp/m2'
MVN = '/usr/share/maven/bin/mvn'
DEPENDENCY = 'org.apache.maven.plugins:maven-dependency-plugin:3.8.1'


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


def run(image, checkout, m2, commit, ids, evidence, tests_from, timeout, tests_label=None):
    path = JavaTestId.parse(ids[0]).source_path()
    # The test file comes from `tests_from` (for example the fix revision's PoV test applied to the vulnerable one).
    patch = tests_patch(path, tests_from)
    config = MavenRunnerConfig(command=(MVN, '-B', '-ntp', '-o', f'-Dmaven.repo.local={M2}', f'--file={WORK}/pom.xml'),
                               workspace_root=WORK, java='/opt/java/openjdk/bin/java', console_jar=LAUNCHER)
    case = DockerCase(image, checkout, commit, timeout, kind='java-image-case', docker=docker, mounts=((m2, '/m2'),),
                      env=('HOME=/tmp',), copies=f'cp -R /m2 {M2};', scratch=(M2,))
    return drive(MavenRunner, case, config, patch, ids, evidence,
                 {'image': image, 'commit': commit, 'tests_from': tests_label or str(tests_from)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared toolchain image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Checkout of the case; its HEAD commit is what runs')
    parser.add_argument('--m2', required=True, type=Path, help='Case Maven repository filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--tests-from', type=Path, help='Checkout whose HEAD supplies the test file (default: --checkout)')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `[module/]pkg.Class#method`')
    args = parser.parse_args()
    require_image_id(parser, args.image)
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = head(args.checkout)
    with tempfile.TemporaryDirectory(dir=args.evidence) as scratch:
        scratch = Path(scratch).resolve()
        tree = commit_tree(args.checkout, scratch / 'checkout')
        tests = commit_tree(args.tests_from, scratch / 'tests') if args.tests_from else tree
        if args.phase == 'setup':
            args.m2.mkdir(parents=True, exist_ok=True)
            code = setup(args.image, tree, args.m2.resolve(), args.evidence)
            print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
            raise SystemExit(code)
        tests_commit = head(args.tests_from or args.checkout)
        summary = run(args.image, tree, args.m2.resolve(), commit, tuple(args.id), args.evidence, tests, args.timeout,
                      tests_label=f'{(args.tests_from or args.checkout).resolve()}@{tests_commit}')
    print_summary(summary)


if __name__ == '__main__':
    main()
