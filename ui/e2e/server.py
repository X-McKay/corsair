"""Real local API with synthetic saved-result fixtures; no model or workload execution."""
from pathlib import Path
import json
import shutil
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
from corsair.web.server import Server


def seed(root: Path):
    (root / 'deploy').mkdir()
    shutil.copyfile(REPO / 'deploy/runtime-matrix.yaml', root / 'deploy/runtime-matrix.yaml')
    shutil.copytree(REPO / 'ui/dist', root / 'ui/dist')
    records = [
        ('planning', '20261013T120000Z-development-scripted', 'scripted', 4, 3,
         {'input_tokens': 120, 'output_tokens': 40, 'task_seconds': 2.5}),
        ('assessment', '20261013T130000Z-development-live', 'live', 2, 2,
         {'input_tokens': 0, 'output_tokens': 0, 'task_seconds': 0}),
        ('planning', '20261013T150000Z-development-scripted', 'scripted', 4, 4,
         {'input_tokens': 110, 'output_tokens': 35, 'task_seconds': 2.0}),
        ('authoring', '20261013T140000Z-development-scripted', 'scripted', None, None, {}),
    ]
    for agent, run, mode, attempts, clean, metrics in records:
        p = root / '.runs/evals' / agent / run
        p.mkdir(parents=True)
        summary = {'identity': {'model': 'fixture-model', 'dataset_sha256': 'fixture-dataset',
                              'prompt_version': 'test-v2' if '150000' in run else 'test-v1', 'mode': mode, 'execution': 'synthetic observations'},
                   'efficiency_mean': metrics,
                   'efficiency_samples': {k: {'observed': attempts, 'attempts': attempts} for k in metrics},
                   'assertions': {}, 'cases': {}}
        if attempts is None:
            summary['report'] = 'missing'
        else:
            summary.update(attempts=attempts, clean_attempts=clean, task_failures=attempts-clean,
                assertions={'contract': {'passed': clean, 'total': attempts}},
                cases={'<img src=x onerror=alert(1)>': {'attempts': attempts, 'clean': clean,
                       'failed_assertions': {'contract': attempts-clean}, 'task_failures': ['PRIVATE TRACE']}})
        record = {'agent': agent, 'run': run, 'set': 'development', 'mode': mode,
                  'command': {'git_commit': 'a'*40, 'git_dirty': False, 'started': '2026-10-13T12:00:00Z',
                              'ended': '2026-10-13T12:00:20Z', 'exit_code': 0 if clean==attempts else 1,
                              'suite_note': 'Synthetic browser test fixture', 'argv': ['PRIVATE ARGUMENT']},
                  'summary': summary}
        (p / 'summary.json').write_text(json.dumps(record))
        if attempts is not None:
            (p / 'evidence').mkdir()
            native = {'cases': [{'name': f'test-{i}', 'task_duration': float(i),
                       'attributes': {'provider_usage_present': True},
                       'metrics': {'input_tokens': 0 if agent == 'assessment' else 100*(i+1),
                                   'output_tokens': 0 if agent == 'assessment' else 10*(i+1)}}
                      for i in range(clean)],
                      'failures': [{'name':'test-failure'} for _ in range(attempts-clean)]}
            (p / 'evidence/report.json').write_text(json.dumps(native))
    bad = root / '.runs/evals/planning/broken-record'
    bad.mkdir()
    (bad / 'summary.json').write_text('{incomplete')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='corsair-ui-browser-') as temp:
        root=Path(temp)
        seed(root)
        server = Server(root, port=8767)
        try:
            server.serve_forever()
        finally:
            server.server_close()
