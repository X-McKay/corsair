"""The read-only viewer over v2 records: loopback HTTP, allow-list projections and hostile local evidence."""
from contextlib import closing, contextmanager
from http.client import HTTPConnection
import json
import os
from pathlib import Path
from threading import Thread

import pytest

from corsair import runs as corsair_runs
from corsair.web.server import AGENTS, Application, Evidence, MAX_JSON, Server, SourceUnavailable, entries, newest
from evals.cases import AGENTS as EVAL_AGENTS, CHAIN

ROOT = Path(__file__).resolve().parents[2]
EVAL_RUN = '20261014T120000Z-development-scripted'
RUN_ID = '20261014T120001Z-0123abcd'


def rollup(attempts=2, clean=1):
    return {'cases': attempts, 'attempts': attempts, 'clean_attempts': clean, 'task_failures': 0,
            'completion': {'attempted': attempts, 'completed': attempts, 'task_failures': 0,
                           'evaluator_failures': 0, 'unknown_failures': 0, 'rate': 1.0},
            'dimensions': {'correctness': {'passed': clean, 'total': attempts}},
            'statuses': {'ok': attempts}, 'status_unreported': 0,
            'parameters': {'model': ['scripted'], 'api_key': ['SECRET'] * 0},
            'wall_s': {'observed': attempts, 'mean': 0.5, 'p50': 0.5, 'p90': 0.9, 'total': 1.0},
            'tokens': {'observed': 0, 'mean': None, 'p50': None, 'p90': None, 'total': None},
            'input_tokens': {'observed': 2, 'mean': 0, 'p50': 0, 'p90': 0, 'total': 0},
            'retries': {'mean': None, 'p50': None, 'p90': None, 'total': None}}


def eval_summary(agent='reviewer', run=EVAL_RUN, attempts=2, clean=1):
    row = {'case': 'python/a', 'language': 'python', 'kind': 'positive', 'receipt': '0001', 'status': 'ok',
           'passed': False, 'dimensions': {'correctness': False}, 'failed_assertions': ['label'],
           'failure': 'SECRET traceback with input', 'failure_kind': 'evaluator', 'wall_s': 0.5, 'tokens': None,
           'label': 'LIKELY_EXPLOITABLE', 'expected_label': 'LIKELY_NOT_EXPLOITABLE', 'terminal_reason': 'ok'}
    return {'schema': 'corsair-eval-summary/v1', 'agent': agent, 'set': 'development', 'language': None,
            'mode': 'scripted', 'run': run, 'identity': {'git_commit': 'abc', 'git_dirty': False, 'model': 'm',
                                                         'prompt_version': 'p1', 'dataset_sha256': 'd'},
            'attempts': [row, dict(row, case='python/b', receipt='0002', passed=True, failure=None,
                                   failure_kind=None, failed_assertions=[])],
            'rollups': {'all': rollup(attempts, clean), 'by_language': {'python': rollup(attempts, clean)},
                        'by_kind': {'positive': rollup(attempts, clean)}}}


def run_record(directory: Path, run_id=RUN_ID, label='LIKELY_EXPLOITABLE'):
    directory.mkdir(parents=True)
    (directory / 'run.json').write_text(json.dumps({
        'schema': 'corsair-v2-run/1', 'run_id': run_id, 'case_id': 'corpus:1', 'mode': 'direct',
        'started_at': '2026-10-14T12:00:01Z', 'finished_at': '2026-10-14T12:00:09Z', 'state': 'completed',
        'git_commit': 'abc', 'git_dirty': False, 'runtime_row': 'pytest-cpython312', 'matrix_sha256': 'f' * 64}))
    (directory / 'summary.json').write_text(json.dumps({
        'schema': 'corsair-v2-run/1', 'run_id': run_id, 'case_id': 'corpus:1', 'mode': 'direct',
        'label': label, 'rule_id': 'R4', 'terminal_reason': 'ok', 'finding': 'reproduced', 'fix': 'verified',
        'sensitivity': None,
        'outcome': {'probes': {'vulnerable': {'control': {'outcome': 'passed', 'facts': {'exit_code': 0}},
                                              'exploit': {'outcome': 'passed', 'facts': {'exit_code': 0},
                                                          'output': 'SECRET probe output'}}}},
        'models': ['m'], 'agents': {'reviewer': {'calls': 1, 'models': ['m'], 'prompt_versions': ['p1'],
                                                 'requests': 2, 'input_tokens': 0, 'wall_s': 1.5,
                                                 'statuses': {'ok': 1}}},
        'totals': {'agent_calls': 1, 'tokens': None, 'wall_s': 8.0, 'requests': 2}}))
    (directory / 'usage.json').write_text(json.dumps([{'step': 'review.1', 'agent': 'reviewer', 'status': 'ok',
                                                       'error': 'SECRET upstream detail', 'input_tokens': 0}]))
    (directory / 'case.json').write_text(json.dumps({'finding': {'title': 'Path traversal', 'start_line': 3}}))
    (directory / 'verdict.json').write_text(json.dumps({'validity': [{'patch_sha256': 'a', 'revision': 'vulnerable',
        'control': {'valid': True, 'defects': [], 'citations': [{'path': 'a.py', 'start_line': 3, 'end_line': 4}]}}],
        'runs': [{'output': 'SECRET probe output'}]}))
    agents = directory / 'agents'
    agents.mkdir()
    (agents / 'review.1.messages.json').write_text('"SECRET message history"')


@pytest.fixture
def root(tmp_path):
    dist = tmp_path / 'ui' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('<html>Corsair</html>')
    (tmp_path / 'deploy' / 'v2').mkdir(parents=True)
    (tmp_path / 'deploy/v2/runtime-matrix.yaml').write_bytes((ROOT / 'deploy/v2/runtime-matrix.yaml').read_bytes())
    run = tmp_path / '.runs/evals/reviewer' / EVAL_RUN
    run.mkdir(parents=True)
    (run / 'summary.json').write_text(json.dumps(eval_summary()))
    (run / 'command.json').write_text(json.dumps({'git_commit': 'abc', 'exit_code': 0, 'note': 'n',
                                                  'argv': ['--provider-config', 'SECRET']}))
    (run / 'policy.json').write_text(json.dumps({'status': 'not_set', 'entries': {
        'accuracy.correctness': {'status': 'not_set', 'value': 0.5, 'limit': None}}}))
    run_record(tmp_path / '.runs/v2/runs' / RUN_ID)
    return tmp_path


@contextmanager
def serving(root, **sources):
    with Server(root, 0, **sources) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=2)


def request(server, path, method='GET', headers=None):
    with closing(HTTPConnection('127.0.0.1', server.server_port, timeout=3)) as connection:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()


def get(server, path):
    status, _, data = request(server, path)
    assert status == 200, data
    return json.loads(data)


def test_agent_list_matches_the_eval_runner():
    assert sorted(AGENTS) == sorted((*EVAL_AGENTS, CHAIN))


def test_eval_listing_and_detail_are_safe_projections(root):
    with serving(root) as server:
        status, headers, data = request(server, '/api/evaluations')
        assert status == 200 and b'SECRET' not in data
        assert headers['Cache-Control'] == 'no-store' and "frame-ancestors 'none'" in headers['Content-Security-Policy']
        (listed,) = json.loads(data)['runs']
        assert listed['overall']['clean_attempts'] == 1 and listed['policy'] == 'not_set'
        assert listed['command']['note'] == 'n' and 'argv' not in listed['command']
        # a measured zero stays zero and an unobserved metric stays unknown
        assert listed['overall']['metrics']['input_tokens']['total'] == 0
        assert listed['overall']['metrics']['tokens']['mean'] is None
        assert listed['overall']['metrics']['tokens']['observed'] == 0
        assert listed['overall']['metrics']['retries']['observed'] is None
        detail = get(server, f'/api/evaluations/reviewer/{EVAL_RUN}')
        assert detail['attempts'][0]['failed'] is True and detail['attempts'][0]['failure_kind'] == 'evaluator'
        assert 'failure' not in detail['attempts'][0]
        assert detail['policy']['entries']['accuracy.correctness']['value'] == 0.5
        assert detail['by_language']['python']['dimensions']['correctness'] == {'passed': 1, 'total': 2}
        assert detail['reference'] is None
        assert b'SECRET' not in request(server, f'/api/evaluations/reviewer/{EVAL_RUN}')[2]
        assert request(server, '/api/evaluations', 'POST')[0] == 405


def test_reference_follows_the_runner_order(root):
    agent = root / '.runs/evals/reviewer'
    later = '20261014T130000Z-development-scripted'
    (agent / later).mkdir()
    (agent / later / 'summary.json').write_text(json.dumps(eval_summary(run=later, clean=2)))
    (agent / 'index.jsonl').write_text('\n'.join(json.dumps({'run': r, 'set': 'development', 'mode': 'scripted'})
                                                 for r in (EVAL_RUN, later)) + '\n')
    evidence = Evidence(root)
    reference = evidence.evaluation('reviewer', later)['reference']
    assert (reference['run'], reference['kind']) == (EVAL_RUN, 'previous run')
    (agent / 'baseline-development-scripted.json').write_text(json.dumps({'run': EVAL_RUN}))
    assert evidence.evaluation('reviewer', later)['reference']['kind'] == 'baseline'
    assert evidence.baselines()['baselines'] == [{'agent': 'reviewer', 'set': 'development', 'mode': 'scripted',
                                                   'source': 'promoted', 'run': EVAL_RUN}]


def test_committed_baseline_is_read_beside_the_agent(root):
    folder = root / 'src/corsair/agents/reviewer/evals/baselines'
    folder.mkdir(parents=True)
    record = {k: v for k, v in eval_summary(run='20261010T000000Z-development-live').items() if k != 'attempts'}
    (folder / 'development-live.json').write_text(json.dumps(record | {'mode': 'live', 'policy_status': 'pass'}))
    (found,) = Evidence(root).baselines()['baselines']
    assert found['source'] == 'committed' and found['policy_status'] == 'pass' and found['mode'] == 'live'


def test_run_records_match_runs_compare_and_hide_private_text(root):
    with serving(root) as server:
        (row,) = get(server, '/api/runs')['runs']
        expected = corsair_runs.row(root / '.runs/v2/runs' / RUN_ID)
        for key in ('run', 'case', 'mode', 'label', 'rule', 'reason', 'state'):
            assert row[key] == expected[key]
        assert row['totals']['tokens'] is None and row['totals']['wall_s'] == 8.0
        status, _, data = request(server, f'/api/runs/{RUN_ID}')
        assert status == 200 and b'SECRET' not in data
        detail = json.loads(data)
        assert detail['probes']['vulnerable']['exploit']['outcome'] == 'passed'
        assert detail['calls'][0] == detail['calls'][0] | {'status': 'ok', 'input_tokens': 0}
        assert detail['validity'][0]['roles']['control']['citations'][0]['end_line'] == 4
        assert detail['finding_detail']['title'] == 'Path traversal'
        assert request(server, f'/runs/{RUN_ID}')[0] == 200


def test_an_unfinished_record_is_incomplete_not_running(root):
    stopped = root / '.runs/v2/runs/20261014T130000Z-ffffffff'
    stopped.mkdir()
    (stopped / 'run.json').write_text(json.dumps({'schema': 'corsair-v2-run/1', 'state': 'recorded'}))
    (root / '.runs/v2/runs/not-a-record').mkdir()
    rows = Evidence(root).runs()['runs']
    assert [r['state'] for r in rows] == ['incomplete', 'completed']


def test_chain_eval_attempt_links_its_kept_record(root):
    chain = root / '.runs/evals/chain' / '20261014T120000Z-v2-scripted'
    chain.mkdir(parents=True)
    (chain / 'summary.json').write_text(json.dumps(eval_summary('chain', chain.name)))
    run_record(chain / 'evidence/runs/0001')
    evidence = Evidence(root)
    rows = evidence.evaluation('chain', chain.name)['attempts']
    assert [r['record'] for r in rows] == [True, False]
    shown = evidence.eval_attempt('chain', chain.name, '0001')
    assert shown['source']['expected_label'] == 'LIKELY_NOT_EXPLOITABLE' and shown['run'] == RUN_ID
    with pytest.raises(ValueError):
        evidence.eval_attempt('reviewer', EVAL_RUN, '0001')


@pytest.mark.parametrize('headers', [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'},
                                     {'Sec-Fetch-Site': 'cross-site'}])
def test_cross_origin_and_dns_rebinding_refused(root, headers):
    with serving(root) as server:
        host = {'Host': f'127.0.0.1:{server.server_port}'}
        assert request(server, '/api/runs', headers=host | headers)[0] == 403


@pytest.mark.parametrize('path', ['/api/runs/%2e%2e', '/api/evaluations/reviewer/%2e%2e', '/%2e%2e/secret.html',
                                  '/api/runs/a%5cb', '/api/evaluations/planning/x', '/.runs/v2/runs'])
def test_path_escape_and_raw_file_routes_refused(root, path):
    with serving(root) as server:
        assert request(server, path)[0] in (400, 404, 422)


def test_symlinked_and_oversized_records_are_omitted(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp('outside')
    run_record(outside / 'record', run_id='SECRET')
    os.symlink(outside / 'record', root / '.runs/v2/runs/20261014T140000Z-link')
    big = root / '.runs/v2/runs/20261014T150000Z-big'
    big.mkdir()
    (big / 'summary.json').write_text(' ' * (MAX_JSON + 1) + '{}')
    data = Evidence(root).runs()
    assert [r['id'] for r in data['runs']] == [RUN_ID]
    assert any('20261014T150000Z-big' in w for w in data['warnings'])
    with pytest.raises(OSError):
        Evidence(root).run('20261014T140000Z-link')


def test_wrong_schema_and_identity_are_omitted(root):
    run = root / '.runs/evals/reviewer/20261014T160000Z-development-scripted'
    run.mkdir()
    (run / 'summary.json').write_text(json.dumps(eval_summary(run='other')))
    legacy = root / '.runs/evals/reviewer/20261014T170000Z-development-scripted'
    legacy.mkdir()
    (legacy / 'summary.json').write_text(json.dumps({'agent': 'reviewer', 'run': legacy.name, 'summary': {}}))
    data = Evidence(root).evaluations()
    assert [r['run'] for r in data['runs']] == [EVAL_RUN]
    assert len(data['warnings']) == 2


def test_missing_sources_are_unavailable_not_empty(tmp_path):
    (tmp_path / 'ui/dist').mkdir(parents=True)
    (tmp_path / 'ui/dist/index.html').write_text('x')
    evidence = Evidence(tmp_path)
    with pytest.raises(SourceUnavailable):
        evidence.runs()
    with pytest.raises(SourceUnavailable):
        evidence.evaluations()
    app = Application(evidence, ('http://localhost:8765',))
    status, body, _ = app.response('GET', '/api/ready', _Headers(Host='localhost:8765'))
    assert status == 503 and json.loads(body)['ready'] is False


class _Headers(dict):
    def get_all(self, name, default):
        return [self[name]] if name in self else default


def test_ready_needs_one_record_source(root):
    import shutil
    shutil.rmtree(root / '.runs/evals')
    app = Application(Evidence(root), ('http://localhost:8765',))
    status, body, _ = app.response('GET', '/api/ready', _Headers(Host='localhost:8765'))
    assert status == 200
    assert {s['id']: s['status'] for s in json.loads(body)['sources']}['evaluations'] == 'unavailable'


def test_runtime_reads_the_v2_matrix_and_its_digest(root):
    import hashlib
    data = Evidence(root).runtime()
    assert data['schema'] == 'corsair-v2/runtime-matrix/1'
    assert data['sha256'] == hashlib.sha256((ROOT / 'deploy/v2/runtime-matrix.yaml').read_bytes()).hexdigest()
    assert {row['evidence'] for row in data['rows']} <= {'canary-only', 'image-only', 'live'}


def test_production_origin_validation(root):
    for origin in ('https://user:secret@example.com', 'https://example.com/path', 'ftp://example.com'):
        with pytest.raises(ValueError):
            Application(Evidence(root), (origin,))
    environ = {'REQUEST_METHOD': 'GET', 'RAW_URI': '/api/runs', 'HTTP_HOST': 'corsair.example'}
    started = []
    body = Application(Evidence(root), ('https://corsair.example',))(environ, lambda s, h: started.append(s))
    assert started == ['200 OK'] and json.loads(b''.join(body))['runs']


def test_scan_limit_keeps_the_newest_names_whatever_the_scan_order(tmp_path):
    names = [f'20261014T{n:06d}Z-run' for n in range(12)]
    for order in (names, names[::-1], names[5:] + names[:5]):
        assert newest(order, limit=3) == (names[:-4:-1], True)
    assert newest(names[:2], limit=3) == (names[1::-1], False)
    for name in names:
        (tmp_path / name).mkdir()
    (tmp_path / 'not a record').mkdir()
    shown, limited = entries(tmp_path, ())
    assert shown == sorted(names, reverse=True) and limited is False
