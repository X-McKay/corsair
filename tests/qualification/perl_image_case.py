"""Image-only run of the TAP runner on a real benchmark checkout: the prepared Perl image under Docker, no OpenShell.

Two phases, each its own container (`image_case`). `setup` installs the project's declared CPAN dependencies into a
case directory with network (`cpanm --installdeps --notest`; no project test runs). `run` drives `TapRunner` in one
offline container: per run a fresh copy of the commit, built offline with its own `Makefile.PL` when it has one, plus
the case's test file as the patch, then listing and execution exactly as SPEC-0061 builds them. This is image
evidence for SPEC-0056 and SPEC-0061, not sandbox qualification.
"""
import argparse
import json
from pathlib import Path
import tempfile

from corsair.adapters.tap_runner import TapRunner, TapRunnerConfig
from corsair.ports.test_runner import PerlTestId
from tests.qualification.image_case import (HARDENED, WORK, DockerCase, commit_tree, docker, drive, head, print_summary,
                                            require_image_id, tests_patch, user)

DEPS = '/deps'
PERL = '/usr/local/bin/perl'
# Built distributions load from blib; the project's lib covers a tree without a build step.
COMMAND = (PERL, '-Iblib/lib', '-Iblib/arch', '-Ilib')
# The case's dependencies, installed by setup, are found through the environment, as the environment agent's setup
# would leave them; they are not part of the operator's runner prefix.
ENV = ('HOME=/tmp', f'PERL5LIB={DEPS}/lib/perl5', 'PERL_MM_USE_DEFAULT=1')
# The build is setup, not a test: a distribution's own Makefile.PL and make, offline, before the patch lands.
BUILD = f'if [ -f Makefile.PL ]; then {PERL} Makefile.PL && make; fi'


def setup(image, checkout, deps, evidence):
    # Only declared prerequisites are installed (the project's own tests are not run: --notest).
    script = (f'cp -R /src {WORK}; cd {WORK}; '
              f'if [ -f cpanfile ] || [ -f Makefile.PL ] || [ -f Build.PL ]; then '
              f'cpanm --notest --installdeps --local-lib-contained {DEPS} .; else echo "no build file"; fi; '
              f'cpanm --version')
    environment = [arg for pair in ENV for arg in ('-e', pair)]
    result = docker('run', '--rm', *HARDENED, '--user', user(), *environment,
                    '-v', f'{checkout}:/src:ro', '-v', f'{deps}:{DEPS}', image, '/bin/sh', '-ec', script, timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


def run(image, checkout, deps, commit, ids, evidence, test_file, timeout):
    path = PerlTestId.parse(ids[0]).path
    staged = evidence / 'patch'
    (staged / path).parent.mkdir(parents=True)
    (staged / path).write_bytes(Path(test_file).read_bytes())
    case = DockerCase(image, checkout, commit, timeout, kind='perl-image-case', docker=docker, mounts=((deps, DEPS),),
                      env=ENV, build=BUILD, evidence=evidence)
    return drive(TapRunner, case, TapRunnerConfig(command=COMMAND, workspace_root=WORK), tests_patch(path, staged), ids,
                 evidence, {'image': image, 'commit': commit, 'test_file': str(test_file)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared perl526 image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Checkout of the case; its HEAD commit is what runs')
    parser.add_argument('--deps', required=True, type=Path, help='Case dependency directory filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--test-file', type=Path, help='The case test file placed at the ids\' path')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `path/to/file.t#subtest`')
    args = parser.parse_args()
    require_image_id(parser, args.image)
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = head(args.checkout)
    with tempfile.TemporaryDirectory(dir=args.evidence) as scratch:
        tree = commit_tree(args.checkout, Path(scratch).resolve() / 'checkout')
        if args.phase == 'setup':
            args.deps.mkdir(parents=True, exist_ok=True)
            code = setup(args.image, tree, args.deps.resolve(), args.evidence)
            print(json.dumps({'phase': 'setup', 'commit': commit, 'exit': code}))
            raise SystemExit(code)
        summary = run(args.image, tree, args.deps.resolve(), commit, tuple(args.id), args.evidence,
                      args.test_file.resolve(), args.timeout)
    print_summary(summary)


if __name__ == '__main__':
    main()
