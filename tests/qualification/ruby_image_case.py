"""Image-only run of the Minitest runner on a real benchmark checkout: the prepared toolchain image under Docker, no OpenShell.

Two phases, each its own container (`image_case`). `setup` resolves the project's own gems with Bundler into a case
bundle directory with network (no test runs) and keeps the resolved `Gemfile.lock` there. `run` drives
`MinitestRunner` in one offline container from the same image: a fresh copy of the commit plus that lockfile per run,
the test file as the patch, listing and execution exactly as SPEC-0063 builds them. This is image evidence, not
sandbox qualification.
"""
import argparse
import json
from pathlib import Path
import tempfile

from corsair.adapters.minitest_runner import MinitestRunner, MinitestRunnerConfig
from corsair.ports.test_runner import RubyTestId
from tests.qualification.image_case import (HARDENED, WORK, DockerCase, commit_tree, docker, drive, head, print_summary,
                                            require_image_id, require_setup, sha256, tests_patch, user, write_setup)

GEMS = '/bundle/gems'
BUNDLE = '/usr/local/bin/bundle'


def redacted(docker_args):
    """Setup's extra `docker run` flags with environment values hidden (a proxy URL can carry a token)."""
    shown, after_env = [], False
    for arg in docker_args:
        if after_env or arg.startswith(('--env=', '-e=')):
            prefix, _, rest = arg.rpartition('=') if not after_env else ('', '', arg)
            name = rest.split('=', 1)[0] if after_env else arg.split('=', 2)[1] if arg.count('=') > 1 else ''
            shown.append((prefix.split('=', 1)[0] + '=' if prefix else '') + (f'{name}=<redacted>' if name else '<redacted>'))
        else:
            shown.append(arg)
        after_env = arg in ('-e', '--env')
    return shown


def setup(image, checkout, bundle, commit, evidence, docker_args):
    # The project's default groups; optional groups stay out. A committed lock installs exactly as committed
    # (frozen: a lock that would need re-resolving fails setup); without one, Bundler's resolution is the
    # harness's choice and is recorded as such.
    committed = (checkout / 'Gemfile.lock').exists()
    frozen = 'BUNDLE_FROZEN=true ' if committed else ''
    script = (f'cp -R /src {WORK}; cd {WORK}; {frozen}BUNDLE_PATH={GEMS} {BUNDLE} install --jobs 4; '
              f'cp {WORK}/Gemfile.lock /bundle/Gemfile.lock')
    result = docker('run', '--rm', *HARDENED, '--user', user(), '-e', 'HOME=/tmp',
                    *docker_args, '-v', f'{checkout}:/src:ro', '-v', f'{bundle}:/bundle', image, '/bin/sh', '-ec', script,
                    timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    record = {'image': image, 'commit': commit, 'lock': 'committed' if committed else 'resolved',
              'committed_lock_sha256': sha256(checkout / 'Gemfile.lock'), 'installed_lock_sha256': sha256(bundle / 'Gemfile.lock'),
              'setup_docker_args': redacted(docker_args), 'exit': result.returncode}
    if result.returncode == 0 and committed and record['committed_lock_sha256'] != record['installed_lock_sha256']:
        record['exit'], record['detail'] = 1, 'installed Gemfile.lock differs from the committed one'
    (evidence / 'setup.json').write_text(json.dumps(record, indent=2))
    write_setup(bundle, record)
    return record


def run(image, checkout, bundle, commit, ids, evidence, tests_from, includes, timeout, tests_label):
    path = RubyTestId.parse(ids[0]).path
    # The bundle must be exactly what setup produced for this image and commit, and its lockfile unchanged since.
    setup_record = require_setup(bundle, {'image': image, 'commit': commit,
                                          'installed_lock_sha256': sha256(bundle / 'Gemfile.lock')})
    config = MinitestRunnerConfig(command=('/usr/bin/env', 'BUNDLE_FROZEN=true', f'BUNDLE_PATH={GEMS}', BUNDLE, 'exec',
                                           '/usr/local/bin/ruby', *(f'-I{item}' for item in includes)),
                                  workspace_root=WORK)
    case = DockerCase(image, checkout, commit, timeout, kind='ruby-image-case', docker=docker,
                      mounts=((bundle, '/bundle'),), env=('HOME=/tmp',), copies=f'cp /bundle/Gemfile.lock {WORK}/;')
    return drive(MinitestRunner, case, config, tests_patch(path, tests_from), ids, evidence,
                 {'image': image, 'commit': commit, 'tests_from': tests_label, 'lock': setup_record['lock'],
                  'lock_sha256': setup_record['installed_lock_sha256'], 'includes': list(includes),
                  'setup_docker_args': setup_record['setup_docker_args']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['setup', 'run'])
    parser.add_argument('--image', required=True, help='Prepared ruby31 image config id (sha256:<64 hex>)')
    parser.add_argument('--checkout', required=True, type=Path, help='Checkout of the case; its HEAD commit is what runs')
    parser.add_argument('--bundle', required=True, type=Path, help='Case bundle directory filled by setup')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--tests-from', type=Path, help='Directory whose HEAD supplies the test file (default: --checkout)')
    parser.add_argument('--include', action='append', default=[], help='Repository-relative `-I` directory (repeatable)')
    parser.add_argument('--setup-docker-arg', action='append', default=[], help='Extra `docker run` argument for setup only')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per runner command')
    parser.add_argument('--id', action='append', default=[], help='Control then security `path.rb::Class#test_method`')
    args = parser.parse_args()
    require_image_id(parser, args.image)
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = head(args.checkout)
    with tempfile.TemporaryDirectory(dir=args.evidence) as scratch:
        scratch = Path(scratch).resolve()
        tree = commit_tree(args.checkout, scratch / 'checkout')
        if args.phase == 'setup':
            args.bundle.mkdir(parents=True, exist_ok=True)
            record = setup(args.image, tree, args.bundle.resolve(), commit, args.evidence, args.setup_docker_arg)
            print(json.dumps({'phase': 'setup', **record}))
            raise SystemExit(record['exit'])
        tests = commit_tree(args.tests_from, scratch / 'tests') if args.tests_from else tree
        tests_label = f'{(args.tests_from or args.checkout).resolve()}@{head(args.tests_from or args.checkout)}'
        summary = run(args.image, tree, args.bundle.resolve(), commit, tuple(args.id), args.evidence, tests,
                      args.include, args.timeout, tests_label)
    print_summary(summary)


if __name__ == '__main__':
    main()
