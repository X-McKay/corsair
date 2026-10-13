"""Exercise the real scripted producer from outside its checkout against the viewer."""
import json
import os
from pathlib import Path
import subprocess
import sys

from corsair.web.server import Evidence

ROOT = Path(__file__).resolve().parents[2]


def test_actual_scripted_eval_and_viewer_share_relative_configured_results(tmp_path):
    environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'src') + os.pathsep + str(ROOT),
                   'CORSAIR_EVAL_RESULTS': 'records'}
    result = subprocess.run([sys.executable, '-m', 'evals.run', 'identification'],
                            cwd=tmp_path, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    viewer = Evidence(ROOT, results=tmp_path / 'records')
    records = viewer.evaluations()['runs']
    assert len(records) == 1 and records[0]['mode'] == 'scripted'
    run = records[0]
    native = json.loads((tmp_path / 'records' / run['agent'] / run['run'] / 'evidence/report.json').read_text())
    assert run['summary']['attempts'] == len(native['cases']) + len(native['failures'])
    assert run['command']['exit_code'] == 0
    metrics = viewer.metrics()['groups'][0]
    assert metrics['latency_seconds'] == [case['task_duration'] for case in native['cases']]
    assert metrics['telemetry_attempts'] == run['summary']['attempts']
