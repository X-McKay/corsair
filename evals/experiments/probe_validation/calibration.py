"""Run only reviewed fixture bytes: native probe sensitivity, no model or database."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from corsair.reports.junit import parse_junit

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'benchmarks/fixtures/sql-query-construction'
PAIRS = {'meaningful': FIXTURE / 'test_queries.py',
         'copied': Path(__file__).parent / 'fixtures/copied/test_queries.py',
         'vacuous': Path(__file__).parent / 'fixtures/vacuous/test_queries.py'}
TEST_IDS = ('test_queries.py::test_benign_control', 'test_queries.py::test_security_preserves_query_structure')


def calibrate(destination: Path) -> dict:
    """The exact same frozen pair executes against each variant in a fresh subprocess.

    No path or source is accepted from a model or arbitrary CLI input. All executable
    bytes come from the three repository-owned fixture paths above.
    """
    destination.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'query construction at a recording dependency seam; no database-engine claim',
              'execution': 'native pytest on reviewed repository fixtures', 'pairs': {}}
    for name, patch_path in PAIRS.items():
        patch = patch_path.read_bytes()
        pair = {'patch_sha256': sha256(patch).hexdigest(), 'runs': {}}
        for variant in ('unsafe', 'safe'):
            work = destination / name / variant
            work.mkdir(parents=True)
            source = (FIXTURE / variant / 'queries.py').read_bytes()
            (work / 'queries.py').write_bytes(source)
            (work / 'test_queries.py').write_bytes(patch)
            command = [sys.executable, '-m', 'pytest', '-c', '/dev/null', '--noconftest', '--rootdir', '.',
                       '--import-mode=importlib', '-p', 'no:cacheprovider', '--tb=native',
                       '--junitxml=results.xml', *TEST_IDS]
            started = perf_counter()
            receipt = subprocess.run(command, cwd=work,
                env={'PATH': os.environ['PATH'], 'PYTHONPATH': '.', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                capture_output=True, timeout=30)
            elapsed = perf_counter() - started
            (work / 'stdout.txt').write_bytes(receipt.stdout)
            (work / 'stderr.txt').write_bytes(receipt.stderr)
            if receipt.returncode not in (0, 1):
                raise RuntimeError(f'{name}/{variant}: native runner failed with exit {receipt.returncode}')
            outcomes = parse_junit((work / 'results.xml').read_bytes(), TEST_IDS,
                                   root=str(work), test_paths=frozenset({'test_queries.py'}))
            pair['runs'][variant] = {'source_sha256': sha256(source).hexdigest(),
                'patch_sha256': sha256((work / 'test_queries.py').read_bytes()).hexdigest(),
                'command': command, 'exit_code': receipt.returncode, 'elapsed_seconds': elapsed,
                'outcomes': [asdict(outcome) for outcome in outcomes]}
        pair['control_healthy'] = all(run['outcomes'][0]['outcome'] == 'passed' for run in pair['runs'].values())
        pair['security_distinguishes'] = (pair['runs']['unsafe']['outcomes'][1]['outcome'] == 'failed'
                                         and pair['runs']['safe']['outcomes'][1]['outcome'] == 'passed')
        report['pairs'][name] = pair
    (destination / 'report.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    report = calibrate(args.evidence.resolve())
    passed = all(pair['control_healthy'] and pair['security_distinguishes'] == (name == 'meaningful')
                 for name, pair in report['pairs'].items())
    print(json.dumps({name: {key: pair[key] for key in ('control_healthy', 'security_distinguishes')}
                      for name, pair in report['pairs'].items()}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
