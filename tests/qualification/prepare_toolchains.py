"""Explicit native fixed toolchain image preparation; no registry push."""
import argparse
import hashlib
import json
import os
import re
import shutil
import urllib.request
import uuid

from tests.qualification.support import ROOT, LOCK, Kubectl, require_owned_cluster

SOURCE = ROOT / 'deploy/qualification/toolchains'
CACHE = ROOT / '.cache/toolchains'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
BASES = {
    'python': 'docker.io/library/python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d',
    'java': 'docker.io/library/maven@sha256:5394efaabc436795b507ca400aaf86311db03543072e0e87ae66c595965d4aed',
    'java8': 'docker.io/library/maven@sha256:f2cb52730ea0bde9dc8ba20e5e539d000dcdd7ab9e498d70c301fe04fbddb656',
    'python37': 'docker.io/library/python@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b',
    'perl526': 'docker.io/library/perl@sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7',
}
# Interpreter each Python toolchain directory is built for; its wheels are fetched hash-checked before an offline build.
PYTHONS = {'python': 'python3.12', 'python37': 'python3.7'}
# Both Java images hold the pinned JUnit Platform console launcher for SPEC-0041 discovery.
LAUNCHER = '/opt/corsair-junit/junit-platform-console-standalone-1.14.4.jar'
JAVA_TESTS = ('nativeRoundtrip', 'nativeRuntime')
# Perl image directories: the upstream image already carries make and the core TAP harness, so nothing is fetched.
PERLS = ('perl526',)
TAP_TESTS = ('native_roundtrip', 'native_runtime')


def source_hashes(language=None):
    """Source digests of one image (each image is prepared and invalidated alone) or, with no language, of all."""
    root = SOURCE / language if language else SOURCE
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


def image_receipt(language):
    receipt = json.loads((CACHE / language / 'image.json').read_text())
    assert receipt['sources'] == source_hashes(language), 'Toolchain source changed after preparation'
    assert receipt['base'] == BASES[language]
    assert receipt['image'] == 'docker.io/library/corsair-' + language + '@' + receipt['manifest_digest']
    return receipt


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


def control(kube, image, language):
    cidfile = kube.evidence / (language + '-control.id')
    command = ('cp -R /opt/corsair-fixture /tmp/project; cd /tmp/project; perl Makefile.PL; make; prove -b -v t/' if language in PERLS else
               'cp /opt/corsair-fixture/test_native.py /tmp/test_native.py; cd /tmp; ' + PYTHONS[language] + ' -m pytest -q test_native.py --junitxml=/tmp/result.xml; cat /tmp/result.xml' if language in PYTHONS else
               'sha256sum -c /opt/corsair-junit.sha256 >/dev/null; cd /opt/corsair-m2; sha256sum -c /opt/corsair-m2.sha256 >/dev/null; printf "CACHE-BEGIN\\n"; cat /opt/corsair-m2.sha256; printf "CACHE-END\\n"; cp -R /opt/corsair-fixture /tmp/project; cp -R /opt/corsair-m2 /tmp/m2; /usr/share/maven/bin/mvn -B -ntp -o -f /tmp/project/pom.xml -Dmaven.repo.local=/tmp/m2 test; cat /tmp/project/target/surefire-reports/TEST-corsair.NativeTest.xml')
    try:
        result = kube.native(DOCKER + ['run', '--rm', '--cidfile', str(cidfile), '--network=none', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=10001:10001', image, '/bin/sh', '-ec', command], timeout=180)
        if language in PERLS:
            tap_report(result.stdout, TAP_TESTS)
        else:
            assert 'tests="%d"' % (1 if language in PYTHONS else len(JAVA_TESTS)) in result.stdout and 'failures="0"' in result.stdout and 'skipped="0"' in result.stdout
            assert all(name in result.stdout for name in (('test_native_roundtrip',) if language in PYTHONS else JAVA_TESTS))
        if language not in PYTHONS and language not in PERLS:
            (kube.evidence / (language + '-maven-cache.sha256')).write_text(result.stdout.split('CACHE-BEGIN\n', 1)[1].split('CACHE-END\n', 1)[0])
    finally:
        cleanup = {'confirmed': False}
        try:
            identity = cleanup['container_id'] = cidfile.read_text().strip()
            current = kube.native(DOCKER + ['inspect', '--format', '{{.Id}} {{.Image}}', identity], check=False)
            if current.returncode == 0:
                assert current.stdout.strip() == identity + ' ' + image, 'Control identity differs; refusing cleanup'
                kube.native(DOCKER + ['rm', '--force', identity])
            absent = kube.native(DOCKER + ['inspect', '--format', '{{.Id}}', identity], check=False)
            assert absent.returncode != 0 and 'no such object' in absent.stderr.lower()
            cleanup['confirmed'] = True
        finally:
            (kube.evidence / (language + '-control-cleanup.json')).write_text(json.dumps(cleanup, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'load'])
    parser.add_argument('--language', choices=sorted(BASES), action='append', help='Prepare only these images (default: all)')
    args = parser.parse_args()
    os.umask(0o077)
    evidence = ROOT / '.runs/toolchains-image' / uuid.uuid4().hex
    evidence.mkdir(parents=True)
    kube = Kubectl(ROOT / '.state/kind/kubeconfig', 'kind-corsair', evidence)
    try:
        node = require_owned_cluster(kube) if args.action == 'load' else None
        for language, base in BASES.items():
            if args.language and language not in args.language:
                continue
            cache = CACHE / language
            if args.action == 'build':
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
                kube.native(DOCKER + ['pull', base], timeout=180)
                # Maven's trusted preparation explicitly downloads exact pinned artifacts;
                # its strict native checksums and complete cache hashes are retained. Python and Perl build offline.
                kube.native(DOCKER + ['build', '--network=' + ('none' if language in PYTHONS or language in PERLS else 'default'), '--pull=false', '--tag', tag, str(context)], timeout=300)
                config = kube.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', tag]).stdout.strip()
                control(kube, config, language)
                receipt = {'tag': tag, 'config_id': config, 'base': base, 'sources': hashes, 'evidence': str(evidence), 'trusted_control_passed': True}
                (cache / 'build.json').write_text(json.dumps(receipt, indent=2))
            else:
                receipt = json.loads((cache / 'build.json').read_text())
                assert receipt['sources'] == source_hashes(language) and receipt['base'] == base and receipt['trusted_control_passed'] is True
                assert kube.native(DOCKER + ['image', 'inspect', '--format', '{{.Id}}', receipt['tag']]).stdout.strip() == receipt['config_id']
                env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ') if key in os.environ}
                env['KIND_EXPERIMENTAL_PROVIDER'] = 'docker'
                kube.native([str(ROOT / '.tools/linux-amd64/kind'), 'load', 'docker-image', receipt['tag'], '--name', 'corsair'], env=env, timeout=180)
                rows = kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'images', 'list']).stdout.splitlines()
                row = [line.split() for line in rows if line.split()[0] == receipt['tag']]
                assert len(row) == 1
                digest = row[0][2]
                data = kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'content', 'get', digest]).stdout.encode()
                assert 'sha256:' + hashlib.sha256(data).hexdigest() == digest and json.loads(data)['config']['digest'] == receipt['config_id']
                image = 'docker.io/library/corsair-' + language + '@' + digest
                kube.native(DOCKER + ['exec', 'corsair-control-plane', 'ctr', '-n', 'k8s.io', 'images', 'tag', receipt['tag'], image])
                loaded = dict(receipt, image=image, manifest_digest=digest)
                if (cache / 'image.json').exists():
                    assert loaded == image_receipt(language)
                else:
                    (cache / 'image.json').write_text(json.dumps(loaded, indent=2))
                (evidence / (language + '-load.json')).write_text(json.dumps(dict(loaded, node_uid=node['metadata']['uid']), indent=2))
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'passed', 'runtime_qualified': False}))
    except Exception as error:
        (evidence / 'result.json').write_text(json.dumps({'outcome': 'failed', 'detail': str(error)}))
        raise
    finally:
        print(f'Toolchain artifact evidence: {evidence}')


if __name__ == '__main__':
    main()
