"""The real scripted producer writes what the viewer reads: one agent eval, run from outside the checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys

from corsair.web.server import Evidence

ROOT = Path(__file__).resolve().parents[2]


def test_actual_scripted_eval_is_read_back_unchanged(tmp_path):
    environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'src') + os.pathsep + str(ROOT)}
    result = subprocess.run([sys.executable, '-m', 'evals.run', 'grounding', '--results', str(tmp_path / 'evals')],
                            cwd=ROOT, env=environment, capture_output=True, timeout=300)
    assert result.returncode == 0, result.stderr.decode()[-2000:]
    viewer = Evidence(ROOT, results=tmp_path / 'evals')
    (listed,) = viewer.evaluations()['runs']
    written = json.loads((tmp_path / 'evals' / 'grounding' / listed['run'] / 'summary.json').read_text())
    overall = written['rollups']['all']
    for key in ('attempts', 'clean_attempts', 'task_failures', 'cases'):
        assert listed['overall'][key] == overall[key]
    assert listed['overall']['dimensions'] == overall['dimensions']
    for metric in ('wall_s', 'tokens'):
        assert listed['overall']['metrics'][metric] == overall[metric]
    detail = viewer.evaluation('grounding', listed['run'])
    assert [row['case'] for row in detail['attempts']] == [row['case'] for row in written['attempts']]
    assert detail['policy']['status'] == json.loads(
        (tmp_path / 'evals' / 'grounding' / listed['run'] / 'policy.json').read_text())['status']
