"""Explicit native fixed toolchain image preparation; no registry push.

    make toolchain-images TOOLCHAINS="python java"

Builds each named image from deploy/qualification/toolchains/<name> (offline where the toolchain allows), runs its
trusted control in a locked-down container, and writes a receipt to .cache/toolchains/<name>/build.json. Every native
command's receipt lands under .runs/toolchains-image/<id>/.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'deploy/qualification/toolchains'
CACHE = ROOT / '.cache/toolchains'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
BASES = {
    'python': 'docker.io/library/python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d',
    'java': 'docker.io/library/maven@sha256:5394efaabc436795b507ca400aaf86311db03543072e0e87ae66c595965d4aed',
    'java8': 'docker.io/library/maven@sha256:f2cb52730ea0bde9dc8ba20e5e539d000dcdd7ab9e498d70c301fe04fbddb656',
    'python37': 'docker.io/library/python@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b',
    'ruby31': 'docker.io/library/ruby@sha256:91627f55e8969006aab67d15c92fb930500ff73948803da1330b8a853fecebb5',
    'perl526': 'docker.io/library/perl@sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7',
    'node8': 'docker.io/library/node@sha256:c9025a77a42d87e95433337ac581c0d42810c1263f0e78802691046920d1560b',
}
# Interpreter each Python toolchain directory is built for; its wheels are fetched hash-checked before an offline build.
PYTHONS = {'python': 'python3.12', 'python37': 'python3.7'}
# Both Java images hold the pinned JUnit Platform console launcher for SPEC-0041 discovery.
LAUNCHER = '/opt/corsair-junit/junit-platform-console-standalone-1.14.4.jar'
JAVA_TESTS = ('nativeRoundtrip', 'nativeRuntime')
# Minitest has no native XML report; its verbose run lists each test and ends with this summary line.
RUBY_TESTS = ('test_native_roundtrip', 'test_native_runtime')
RUBY_SUMMARY = '2 runs, 4 assertions, 0 failures, 0 errors, 0 skips'
RUBY_RUN = ['/usr/bin/env', 'BUNDLE_FROZEN=true', '/usr/local/bin/bundle', 'exec', '/usr/local/bin/ruby', '-Itest', 'test/native_test.rb', '-v']
# Perl image directories: the upstream image already carries make and the core TAP harness, so nothing is fetched.
PERLS = ('perl526',)
TAP_TESTS = ('native_roundtrip', 'native_runtime')
# Node toolchain directories; each fixture's package-lock.json pins every npm package by SHA-512 (SPEC-0055).
NODES = ('node8',)
NODE_TESTS = ('nativeRoundtrip', 'nativeRuntime')
NPM = ('/usr/local/bin/node', '/usr/local/lib/node_modules/npm/bin/npm-cli.js', '--ignore-scripts', '--no-audit', '--no-update-notifier')
JEST = ('/usr/local/bin/node', 'node_modules/jest/bin/jest.js', '--ci')


def jest_report(text, expected):
    """Jest's own --json report: every expected test ran and passed, nothing else ran."""
    report = json.loads(text)
    results = [a for suite in report['testResults'] for a in suite['assertionResults']]
    assert report['success'] is True and report['numTotalTests'] == report['numPassedTests'] == len(expected)
    assert report['numFailedTests'] == report['numPendingTests'] == report['numTodoTests'] == 0
    assert sorted(a['fullName'] for a in results) == sorted(expected) and all(a['status'] == 'passed' for a in results)
    return {'tests': len(results), 'ids': sorted(a['fullName'] for a in results), 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def source_hashes(language=None):
    """Source digests of one image (each image is prepared and invalidated alone) or, with no language, of all."""
    root = SOURCE / language if language else SOURCE
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


class Native:
    """Runs native commands and retains a receipt for each, including uncertain delivery."""

    def __init__(self, evidence):
        self.evidence = evidence
        self.counter = 0

    def native(self, argv, check=True, timeout=120, env=None):
        self.counter += 1
        receipt = {'argv': list(map(str, argv)), 'started_at': datetime.now(timezone.utc).isoformat()}
        started = time.monotonic()
        try:
            result = subprocess.run(receipt['argv'], capture_output=True, text=True, timeout=timeout, env=env)
            receipt.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as error:
            receipt.update(timed_out=True, stdout=(error.stdout or b'').decode(), stderr=(error.stderr or b'').decode())
            raise RuntimeError('Native command timed out; remote completion unknown; see command receipt') from error
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - started
            (self.evidence / f'command-{self.counter:04d}.json').write_text(json.dumps(receipt, indent=2))
        if check and result.returncode:
            raise RuntimeError(f'Native infrastructure/resource error ({result.returncode}): {result.stderr[-2000:]}')
        return result


def tap_report(text, expected):
    """Admit one passing `prove -v` run of a single test file: its plan, exactly the expected top-level subtests ok
    in order, no failing, skipped or todo line, and prove's own summary. Exit 0 alone is not a pass: prove also exits
    0 when it finds no tests (`Result: NOTESTS`)."""
    lines = text.splitlines()
    assert f'1..{len(expected)}' in lines and lines.count(f'1..{len(expected)}') == 1
    assert [line for line in lines if re.match(r'(not )?ok \d+', line)] == [f'ok {n} - {name}' for n, name in enumerate(expected, 1)]
    assert not any(re.match(r'\s*not ok\b', line) or re.search(r'#\s*(SKIP|TODO)', line, re.I) for line in lines)
    assert any(line.startswith(f'Files=1, Tests={len(expected)}, ') for line in lines) and lines[-1] == 'Result: PASS'
    return {'tests': len(expected), 'ids': list(expected), 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def control(runner, image, language):
    cidfile = runner.evidence / (language + '-control.id')
    npm, jest = ' '.join(NPM), ' '.join(JEST)
    command = ('cp -R /opt/corsair-fixture /tmp/project; cp -R /opt/corsair-npm /tmp/npm; cd /tmp/project; ' + npm + ' --cache /tmp/npm ci --offline >&2; ' + jest + ' --json --outputFile=/tmp/result.json >&2; cat /tmp/result.json' if language in NODES else
               'cp -R /opt/corsair-fixture /tmp/project; cd /tmp/project; perl Makefile.PL; make; prove -b -v t/' if language in PERLS else
               'cp /opt/corsair-fixture/test_native.py /tmp/test_native.py; cd /tmp; ' + PYTHONS[language] + ' -m pytest -q test_native.py --junitxml=/tmp/result.xml; cat /tmp/result.xml' if language in PYTHONS else
               'sha256sum -c /opt/corsair-junit.sha256 >/dev/null; cd /opt/corsair-m2; sha256sum -c /opt/corsair-m2.sha256 >/dev/null; printf "CACHE-BEGIN\\n"; cat /opt/corsair-m2.sha256; printf "CACHE-END\\n"; cp -R /opt/corsair-fixture /tmp/project; cp -R /opt/corsair-m2 /tmp/m2; /usr/share/maven/bin/mvn -B -ntp -o -f /tmp/project/pom.xml -Dmaven.repo.local=/tmp/m2 test; cat /tmp/project/target/surefire-reports/TEST-corsair.NativeTest.xml')
    if language == 'ruby31':
        command = 'cp -R /opt/corsair-fixture /tmp/project; cd /tmp/project; ' + ' '.join(RUBY_RUN)
    try:
        result = runner.native(DOCKER + ['run', '--rm', '--cidfile', str(cidfile), '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=10001:10001', image, '/bin/sh', '-ec', command], timeout=180)
        if language in NODES:
            (runner.evidence / (language + '-control-report.json')).write_text(json.dumps(jest_report(result.stdout, NODE_TESTS), indent=2))
        elif language in PERLS:
            tap_report(result.stdout, TAP_TESTS)
        elif language == 'ruby31':
            assert result.stdout.rstrip().endswith(RUBY_SUMMARY) and all(f'NativeTest#{name} = ' in result.stdout for name in RUBY_TESTS)
        else:
            assert 'tests="%d"' % (1 if language in PYTHONS else len(JAVA_TESTS)) in result.stdout and 'failures="0"' in result.stdout and 'skipped="0"' in result.stdout
            assert all(name in result.stdout for name in (('test_native_roundtrip',) if language in PYTHONS else JAVA_TESTS))
        if language.startswith('java'):
            (runner.evidence / (language + '-maven-cache.sha256')).write_text(result.stdout.split('CACHE-BEGIN\n', 1)[1].split('CACHE-END\n', 1)[0])
    finally:
        cleanup = {'confirmed': False}
        try:
            identity = cleanup['container_id'] = cidfile.read_text().strip()
            current = runner.native(DOCKER + ['inspect', '--format', '{{.Id}} {{.Image}}', identity], check=False)
            if current.returncode == 0:
                assert current.stdout.strip() == identity + ' ' + image, 'Control identity differs; refusing cleanup'
                runner.native(DOCKER + ['rm', '--force', identity])
            absent = runner.native(DOCKER + ['inspect', '--format', '{{.Id}}', identity], check=False)
            assert absent.returncode != 0 and 'no such object' in absent.stderr.lower()
            cleanup['confirmed'] = True
        finally:
            (runner.evidence / (language + '-control-cleanup.json')).write_text(json.dumps(cleanup, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--language', choices=sorted(BASES), action='append', help='Prepare only these images (default: all)')
    args = parser.parse_args()
    os.umask(0o077)
    evidence = ROOT / '.runs/toolchains-image' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    runner = Native(evidence)
    try:
        for language, base in BASES.items():
            if args.language and language not in args.language:
                continue
            cache = CACHE / language
            assert not cache.exists(), 'Existing attempt retained: inspect/archive it before new preparation'
            cache.mkdir(parents=True)
            context = cache / 'context'
            shutil.copytree(SOURCE / language, context)
            hashes = source_hashes(language)
            if language in PYTHONS:
                wheel_dir = context / 'wheels'
                wheel_dir.mkdir()
                for wheel in json.loads((SOURCE / language / 'wheels.json').read_text()):
                    data = urllib.request.urlopen(wheel['url'], timeout=30).read()
                    assert hashlib.sha256(data).hexdigest() == wheel['sha256']
                    (wheel_dir / wheel['filename']).write_bytes(data)
                (evidence / (language + '-wheels.json')).write_text((SOURCE / language / 'wheels.json').read_text())
            source_digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
            tag = 'docker.io/library/corsair-' + language + ':' + source_digest[:16]
            runner.native(DOCKER + ['pull', base], timeout=180)
            # Maven's trusted preparation explicitly downloads exact pinned artifacts;
            # its strict native checksums and complete cache hashes are retained. Python, Perl and Ruby build offline.
            # npm's trusted preparation installs only the checked-in lockfile, each tarball SHA-512 checked.
            runner.native(DOCKER + ['build', '--network=' + ('none' if language in PYTHONS or language in PERLS or language == 'ruby31' else 'default'), '--pull=false', '--tag', tag, str(context)], timeout=300)
            config = runner.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', tag]).stdout.strip()
            control(runner, config, language)
            receipt = {'tag': tag, 'config_id': config, 'base': base, 'sources': hashes, 'evidence': str(evidence), 'trusted_control_passed': True}
            (cache / 'build.json').write_text(json.dumps(receipt, indent=2))
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'runtime_qualified': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        raise
    finally:
        print(f'Toolchain artifact evidence: {evidence}')


if __name__ == '__main__':
    main()
