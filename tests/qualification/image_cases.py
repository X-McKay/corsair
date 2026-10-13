"""Image-only real-case runs per toolchain image (the CI opt-in table): prepare each case's revisions, then
`java_image_case` setup and run on both, and check the expected outcome. Image evidence only, never sandbox evidence.

A case is one table entry: where its source comes from, the commits, how its test file is built, the control and
security ids, and the outcome each revision must show. The fix revision runs its own test file; the vulnerable one
runs the fix's test file (`--tests-from`), so the control passes on both and only the security test changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
# Fixed identity so the overlay commit is the same object on every run.
GIT_ENV = {'GIT_AUTHOR_NAME': 'Corsair', 'GIT_AUTHOR_EMAIL': 'corsair@invalid', 'GIT_COMMITTER_NAME': 'Corsair',
           'GIT_COMMITTER_EMAIL': 'corsair@invalid', 'GIT_AUTHOR_DATE': '2026-10-13T00:00:00Z',
           'GIT_COMMITTER_DATE': '2026-10-13T00:00:00Z'}

# VUL4J-6 (CVE-2018-1324, commons-compress). The Vul4J branch carries the project history and its PoV. The overlay is
# the PoV file byte for byte, then (after one blank line) a Corsair-authored control copied verbatim from the
# unrelated upstream ZipShortTest#testToBytes, the same overlay #51 ran on RIG0.
VUL4J_6 = {
    'id': 'VUL4J-6',
    'repository': 'https://github.com/tuhh-softsec/vul4j', 'branch': 'VUL4J-6',
    'fix': '2a2f1dc48e22a34ddb72321a4db211da91aa933b', 'vulnerable': 'dcb0486fb4cb2b6592c04d6ec2edbd3f690df5f2',
    'pov': {'commit': '45ddad15edd0f56a38d1d10e1ac6e1c2de9de881',
            'path': 'src/test/java/org/apache/commons/compress/Test_CVE_2018_1324.java',
            'sha256': '5d597bb34dbedbd77b0001a192e439486ddc16bdc4405d8a972217feb54c30ef'},
    'control': {'path': 'src/test/java/org/apache/commons/compress/archivers/zip/ZipShortTest.java',
                'sha256': '27a06a0c2dfed2228b00e260c94c5d5c760b0af7eac7eb0c6d6e623edaf61bc4',
                'method': 'testToBytes', 'name': 'testBenignZipShortToBytes'},
    'overlay_sha256': '18a406a5d65d1121fe8fda1dbcfac41312f731a8d5a3b6097c46551a7d0534d5',
    'ids': ('org.apache.commons.compress.Test_CVE_2018_1324#testBenignZipShortToBytes',
            'org.apache.commons.compress.Test_CVE_2018_1324#testCVE_2018_1324'),
    'expect': {'fix': ('passed', 'passed'), 'vulnerable': ('passed', 'not passed')},
}
CASES = {'java8': (VUL4J_6,)}


def git(*args, cwd=None, env=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                          env=None if env is None else {**os.environ, **env}).stdout


def blob(clone, commit, path, sha256):
    data = git('show', f'{commit}:{path}', cwd=clone)
    assert hashlib.sha256(data).hexdigest() == sha256, f'{path}@{commit[:8]} differs from the recorded source'
    return data.decode()


def control_method(source, method, name):
    """The upstream test method, annotation to closing brace, verbatim apart from its name."""
    head = f'    @Test\n    public void {method}() {{\n'
    start = source.index(head)
    return source[start:source.index('\n    }\n', start) + 7].replace(f'void {method}()', f'void {name}()', 1)


def prepare(case, work):
    clone = work / 'source.git'
    git('clone', '--quiet', '--bare', '--single-branch', '--branch', case['branch'], case['repository'], str(clone))
    pov = blob(clone, case['pov']['commit'], case['pov']['path'], case['pov']['sha256'])
    control = control_method(blob(clone, case['fix'], case['control']['path'], case['control']['sha256']),
                             case['control']['method'], case['control']['name'])
    body, closing = pov.rstrip('\n').rsplit('}', 1)
    overlay = body + '\n' + control + '}' + closing + '\n'
    digest = hashlib.sha256(overlay.encode()).hexdigest()
    assert digest == case['overlay_sha256'], f'overlay sha256 {digest} is not the recorded one'
    trees = {}
    for revision in ('fix', 'vulnerable'):
        tree = trees[revision] = work / revision
        git('clone', '--quiet', '--no-checkout', str(clone), str(tree))
        git('checkout', '--quiet', '--detach', case[revision], cwd=tree)
    target = trees['fix'] / case['pov']['path']
    target.write_text(overlay)
    git('add', case['pov']['path'], cwd=trees['fix'])
    git('commit', '--quiet', '-m', f'{case["id"]}: Vul4J PoV with a verbatim upstream control', cwd=trees['fix'], env=GIT_ENV)
    return trees, digest


def harness(*args):
    command = [sys.executable, '-m', 'tests.qualification.java_image_case', *args]
    print('+', ' '.join(command), flush=True)
    # The project is not an installed package (pyproject `package = false`); the harness imports `corsair` from src.
    path = os.pathsep.join(filter(None, (str(ROOT / 'src'), str(ROOT), os.environ.get('PYTHONPATH'))))
    return subprocess.run(command, cwd=ROOT, check=False, env={**os.environ, 'PYTHONPATH': path})


def outcome(run, ids):
    """Outcome per id from run.json `cases`: rows of (test_id, outcome) or, from #89's shared harness,
    (test_id, outcome, failure_detail). Any other shape is a harness defect, not a test result."""
    cases = {}
    for row in run.get('cases') or []:
        assert isinstance(row, (list, tuple)) and len(row) in (2, 3) and all(isinstance(v, str) for v in row[:2]), \
            f'unexpected case row {row!r}'
        cases[row[0]] = row[1]
    return tuple(cases.get(test_id, 'missing') for test_id in ids)


def run_case(image, case, evidence):
    evidence.mkdir(parents=True)
    trees, digest = prepare(case, evidence / 'work')
    m2 = evidence / 'm2'
    results = {'case': case['id'], 'image': image, 'overlay_sha256': digest, 'revisions': {}}
    ok = True
    for revision in ('fix', 'vulnerable'):
        commit = git('rev-parse', 'HEAD', cwd=trees[revision]).decode().strip()
        setup = harness('setup', '--image', image, '--checkout', str(trees[revision]), '--m2', str(m2),
                        '--evidence', str(evidence / f'setup-{revision}'))
        entry = results['revisions'][revision] = {'commit': commit, 'setup_exit': setup.returncode}
        if setup.returncode:
            ok = False
            continue
        ids = [arg for test_id in case['ids'] for arg in ('--id', test_id)]
        harness('run', '--image', image, '--checkout', str(trees[revision]), '--m2', str(m2), '--tests-from',
                str(trees['fix']), '--evidence', str(evidence / f'run-{revision}'), *ids)
        report = evidence / f'run-{revision}' / 'run.json'
        run = json.loads(report.read_text()) if report.exists() else {}
        got = outcome(run, case['ids'])
        want = case['expect'][revision]
        entry.update(outcome=got, expected=want, container_cleanup=run.get('container_cleanup'),
                     failure_layer=run.get('failure_layer'), elapsed_seconds=run.get('elapsed_seconds'))
        # 'not passed' accepts a failure or an error of the security test, never a pass, skip or absence.
        matches = all(g == w or (w == 'not passed' and g in ('failed', 'error')) for g, w in zip(got, want))
        ok = ok and matches and run.get('container_cleanup') == 'confirmed'
    results['outcome'] = 'passed' if ok else 'failed'
    (evidence / 'summary.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('toolchain', help='Image directory; its cases come from CASES')
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    image = json.loads((ROOT / '.cache/toolchains' / args.toolchain / 'build.json').read_text())['config_id']
    ok = all([run_case(image, case, args.evidence / case['id']) for case in CASES.get(args.toolchain, ())])
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
