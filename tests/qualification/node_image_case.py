"""Image-only run of the Jest runner on a real benchmark checkout: the prepared node8 image under Docker, no OpenShell.

Two phases, each its own container (`image_case`). `setup` installs the project's own dependencies from its lockfile with network
(`npm ci --ignore-scripts`; no test runs) into a case directory. `run` drives `JestRunner` in one offline container
from the same image: a fresh copy of the commit and its installed dependencies per run, the test file as the patch,
listing and execution exactly as SPEC-0057 builds them. This is image evidence for SPEC-0055/SPEC-0057, not
sandbox qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from corsair.adapters.jest_runner import JestRunner, JestRunnerConfig
from corsair.ports.test_runner import JsTestId
from tests.qualification.image_case import (HARDENED, WORK, DockerCase, commit_tree, docker, drive, head, print_summary,
                                            require_image_id, tests_patch, user)
from tests.qualification.prepare_toolchains import NPM

JEST = ('/usr/local/bin/node', 'node_modules/jest/bin/jest.js', '--ci')
# Passed through to setup only when the host needs them to reach the registry (a proxy and its CA file).
SETUP_ENV = ('HTTPS_PROXY', 'https_proxy', 'NODE_EXTRA_CA_CERTS')


def setup(image, checkout, modules, evidence):
    npm = ' '.join(NPM)
    script = f'cp -R /src {WORK}; cd {WORK}; {npm} --cache /tmp/npm ci; cp -R {WORK}/node_modules /modules/'
    env = [arg for key in SETUP_ENV if os.environ.get(key) for arg in ('-e', f'{key}={os.environ[key]}')]
    ca = os.environ.get('NODE_EXTRA_CA_CERTS')
    mounts = ['-v', f'{ca}:{ca}:ro'] if ca else []
    result = docker('run', '--rm', '--network=host' if env else '--network=bridge', *HARDENED, '--user', user(), '-e', 'HOME=/tmp', *env, *mounts,
                    '-v', f'{checkout}:/src:ro', '-v', f'{modules}:/modules', image, '/bin/sh', '-ec', script, timeout=1800)
    (evidence / 'setup.stdout').write_bytes(result.stdout)
    (evidence / 'setup.stderr').write_bytes(result.stderr)
    return result.returncode


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
    staged = evidence / 'patch'
    (staged / path).parent.mkdir(parents=True)
    (staged / path).write_bytes(Path(test_file).read_bytes())
    config = JestRunnerConfig(command=JEST, workspace_root=WORK, report_path='/tmp/corsair-jest.json')
    case = DockerCase(image, checkout, commit, timeout, kind='node-image-case', docker=docker,
                      mounts=((modules, '/modules'),), env=('HOME=/tmp',), copies=f'cp -R /modules/node_modules {WORK}/;')
    return drive(JestRunner, case, config, tests_patch(path, staged), ids, evidence,
                 {'image': image, 'commit': commit, 'setup_receipt': receipt, 'test_file': str(test_file)})


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
    require_image_id(parser, args.image)
    args.evidence.mkdir(parents=True, exist_ok=False)
    commit = head(args.checkout)
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
    print_summary(summary)


if __name__ == '__main__':
    main()
