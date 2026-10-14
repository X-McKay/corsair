"""The real local API over records the real v2 producers wrote; no model, Docker or workload execution.

Seeding runs the scripted chain eval and the reviewer eval through `evals.run` into a temporary results root, then
files three of the chain eval's own run records under a runs root the way `corsair-v2 run` writes them. Two records
are then degraded on purpose: one stops before its verdict (an incomplete record) and one is malformed; one
finding title is replaced by markup to check that the browser renders it as text.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from corsair.web.server import Server  # noqa: E402

HOSTILE = '<img src=x onerror=alert(1)>'


def produce(results: Path) -> None:
    env = os.environ | {'PYTHONPATH': os.pathsep.join([str(REPO / 'src'), str(REPO)])}
    for agent, note in (('chain', 'browser fixture'), ('reviewer', 'first'), ('reviewer', 'second')):
        subprocess.run([sys.executable, '-m', 'evals.run', agent, '--results', str(results), '--note', note],
                       cwd=REPO, env=env, check=True, stdout=subprocess.DEVNULL)


def seed(root: Path) -> None:
    results, runs = root / 'evals', root / 'runs'
    produce(results)
    (chain,) = (results / 'chain').glob('*-v2-scripted')
    rows = [json.loads(line) for line in (chain / 'evidence' / 'attempts.jsonl').read_text().splitlines()[1:]]
    wanted = {}
    for row in rows:
        wanted.setdefault(row['label'], row['receipt'])
    runs.mkdir()
    for label in ('LIKELY_EXPLOITABLE', 'LIKELY_NOT_EXPLOITABLE', 'UNABLE_TO_RUN'):
        source = chain / 'evidence' / 'runs' / wanted[label]
        run_id = json.loads((source / 'run.json').read_text())['run_id']
        shutil.copytree(source, runs / run_id)
    exploitable = next(p for p in runs.iterdir()
                       if json.loads((p / 'summary.json').read_text())['label'] == 'LIKELY_EXPLOITABLE')
    case = json.loads((exploitable / 'case.json').read_text())
    case['finding']['title'] = HOSTILE
    (exploitable / 'case.json').write_text(json.dumps(case))
    # A run that stopped before Decide: run.json only, no verdict.
    stopped = runs / '20261014T000000Z-00000000'
    stopped.mkdir()
    run = json.loads((exploitable / 'run.json').read_text())
    run |= {'run_id': stopped.name, 'state': 'recorded', 'finished_at': None, 'last_started_step': 'build'}
    (stopped / 'run.json').write_text(json.dumps(run))
    broken = runs / '20261013T000000Z-broken'
    broken.mkdir()
    (broken / 'summary.json').write_text('{incomplete')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='corsair-ui-browser-') as temp:
        root = Path(temp)
        seed(root)
        server = Server(REPO, port=8767, results=root / 'evals', runs=root / 'runs')
        try:
            server.serve_forever()
        finally:
            server.server_close()
