"""Real loopback requests and hostile local evidence exercise the viewer boundary."""
from contextlib import closing, contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread

import pytest

from corsair.web.server import Evidence, EvidenceError, MAX_JSON, Server


@pytest.fixture
def root(tmp_path):
    dist = tmp_path / 'ui' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('<html>Corsair</html>')
    run = tmp_path / '.runs/evals/planning/20261013-development-scripted'
    run.mkdir(parents=True)
    record = {
        'agent': 'planning', 'run': run.name, 'set': 'development', 'mode': 'scripted',
        'command': {'git_commit': 'abc123', 'git_dirty': False, 'exit_code': 0,
                    'argv': ['--token', 'SECRET'], 'note': 'PRIVATE NOTE'},
        'summary': {'identity': {'model': 'test', 'execution': 'static', 'api_key': 'SECRET'},
                    'attempts': 2, 'clean_attempts': 1, 'task_failures': 1,
                    'assertions': {'valid': {'passed': 1, 'total': 1}},
                    'cases': {'case1': {'attempts': 2, 'clean': 1, 'task_failures': ['SECRET error']}},
                    'efficiency_mean': {'observed_input_tokens': 0, 'task_seconds': 1.5},
                    'efficiency_samples': {'observed_input_tokens': {'observed': 1, 'attempts': 2}}}}
    (run / 'summary.json').write_text(json.dumps(record))
    (run / 'evidence').mkdir()
    (run / 'evidence/report.json').write_text(json.dumps({
        'cases': [{'name': 'c', 'inputs': 'SECRET input', 'output': 'SECRET output'}],
        'failures': [{'error_message': 'SECRET error'}]}))
    return tmp_path


@contextmanager
def serving(root):
    with Server(root, 0) as server:
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


def test_http_listing_detail_and_static_are_read_only_safe_projections(root):
    with serving(root) as server:
        status, headers, data = request(server, '/api/evaluations')
        assert status == 200
        record = json.loads(data)['runs'][0]
        assert record['summary']['efficiency_mean']['observed_input_tokens'] == 0
        assert 'observed_output_tokens' not in record['summary']['efficiency_mean']
        assert record['summary']['efficiency_samples']['observed_input_tokens']['observed'] == 1
        assert b'SECRET' not in data and b'PRIVATE' not in data
        assert headers['Cache-Control'] == 'no-store'
        assert headers['X-Content-Type-Options'] == 'nosniff'
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        status, _, data = request(server, '/api/evaluations/planning/' + record['run'])
        assert status == 200
        assert json.loads(data)['report'] == {'completed_attempts': 1, 'failed_attempts': 1}
        assert b'SECRET' not in data
        assert request(server, '/')[0] == 200
        assert request(server, '/evaluations/planning/' + record['run'])[0] == 200
        assert request(server, '/runtime')[0] == 200
        assert request(server, '/api/health')[0] == 200
        assert request(server, '/api/evaluations', 'POST')[0] == 405


@pytest.mark.parametrize('headers', [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'},
                                      {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_browser_cross_origin_and_dns_rebinding_refused(root, headers):
    with serving(root) as server:
        assert request(server, '/api/evaluations', headers=headers)[0] == 403


def test_loopback_same_origin_accepted(root):
    with serving(root) as server:
        host = f'localhost:{server.server_port}'
        assert request(server, '/api/health', headers={'Host': host, 'Origin': f'http://{host}'})[0] == 200


@pytest.mark.parametrize('path', ['/api/evaluations/planning/%2e%2e', '/%2e%2e/secret.html',
                                  '/%5csecret.js', '/api/health?file=secrets', '/.runs/secret.json'])
def test_path_escape_and_raw_file_routes_refused(root, path):
    with serving(root) as server:
        assert request(server, path)[0] in (400, 404, 422)


def test_symlink_summary_is_omitted_without_reading(root):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    path.unlink()
    secret = root / 'private.json'
    secret.write_text('{"password":"SECRET"}')
    path.symlink_to(secret)
    result = Evidence(root).evaluations()
    assert result['runs'] == []
    assert result['warnings']
    assert 'SECRET' not in json.dumps(result)


def test_symlink_static_and_parent_directory_are_rejected(root):
    secret = root / 'secret.html'
    secret.write_text('SECRET')
    (root / 'ui/dist/leak.html').symlink_to(secret)
    (root / 'ui/dist/leak').symlink_to(root)
    with serving(root) as server:
        for path in ('/leak.html', '/leak/secret.html'):
            status, _, body = request(server, path)
            assert status == 422 and b'SECRET' not in body


def test_invalid_and_oversized_evidence_does_not_hide_other_runs(root):
    bad = root / '.runs/evals/planning/bad'
    bad.mkdir()
    (bad / 'summary.json').write_text('x' * (MAX_JSON + 1))
    malformed = root / '.runs/evals/planning/malformed'
    malformed.mkdir()
    (malformed / 'summary.json').write_text('{')
    result = Evidence(root).evaluations()
    assert len(result['runs']) == 1 and len(result['warnings']) == 2


def test_missing_records_not_fabricated(root):
    empty = root / 'empty'
    empty.mkdir()
    assert Evidence(empty).evaluations() == {'runs': [], 'warnings': []}
    with serving(empty) as server:
        assert request(server, '/api/evaluations/planning/missing')[0] == 404


def test_nan_infinite_and_boolean_metrics_are_omitted(root):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    record = json.loads(path.read_text())
    record['summary']['efficiency_mean'].update(nan=float('nan'), infinity=float('inf'), boolean=True)
    path.write_text(json.dumps(record))
    result = Evidence(root).evaluations()['runs'][0]
    assert result['summary']['efficiency_mean'] == {'observed_input_tokens': 0, 'task_seconds': 1.5}
    json.dumps(result, allow_nan=False)


def test_mismatched_identity_is_rejected(root):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    record = json.loads(path.read_text())
    record['agent'] = 'assessment'
    path.write_text(json.dumps(record))
    assert Evidence(root).evaluations()['runs'] == []


def test_repository_runtime_projection_preserves_evidence_levels():
    checkout = Path(__file__).resolve().parents[2]
    result = Evidence(checkout).runtime()
    assert {row['qualification']['evidence'] for row in result['rows']} == {'live', 'image-only'}
    assert all('frameworks' in row for row in result['rows'])
    assert result['limitations']


@pytest.mark.parametrize('updates', [
    {'attempts': -1}, {'clean_attempts': 3}, {'task_failures': 3}, {'attempts': True},
    {'assertions': {'valid': {'passed': 3, 'total': 2}}},
    {'efficiency_samples': {'task_seconds': {'observed': 3, 'attempts': 2}}},
    {'cases': {'case': {'attempts': 1, 'clean': 2}}}])
def test_invalid_counts_cannot_claim_success(root, updates):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    record = json.loads(path.read_text())
    record['summary'].update(updates)
    path.write_text(json.dumps(record))
    result = Evidence(root).evaluations()
    assert result['runs'] == [] and result['warnings']


def test_native_model_identity_preserved_without_provider_settings(root):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    record = json.loads(path.read_text())
    record['summary']['identity']['model'] = {
        'model_name': 'function:respond:', 'system': 'function', 'model_settings': {'api_key': 'SECRET'}}
    record['summary']['identity']['budget'] = {'repeat': 2, 'task_seconds': 180, 'output_retries': 1}
    path.write_text(json.dumps(record))
    result = Evidence(root).evaluations()['runs'][0]
    identity = result['summary']['identity']
    assert identity['model'] == {'model_name': 'function:respond:', 'system': 'function'}
    assert identity['budget'] == {'repeat': 2, 'task_seconds': 180, 'output_retries': 1}
    assert 'SECRET' not in json.dumps(result)



def test_spa_filter_query_and_unavailable_report(root):
    report = next(root.glob('.runs/evals/planning/*/evidence/report.json'))
    report.unlink()
    with serving(root) as server:
        assert request(server, '/evaluations?agent=planning')[0] == 200
        status, _, data = request(server, '/api/evaluations/planning/20261013-development-scripted')
        assert status == 200
        assert json.loads(data)['report'] == {'available': False}


def test_invalid_model_metadata_cannot_break_other_measurements(root):
    path = next(root.glob('.runs/evals/planning/*/summary.json'))
    record = json.loads(path.read_text())
    record['summary']['identity']['model'] = 123
    path.write_text(json.dumps(record))
    result = Evidence(root).evaluations()['runs'][0]
    assert 'model' not in result['summary']['identity']
    assert result['summary']['attempts'] == 2


def metric_run(root, run='20261014-development-live', *, mode='live', model='test-model', dataset='dataset-a',
               cases=None, failures=None, attempts=None):
    path = root / '.runs/evals/assessment' / run
    (path / 'evidence').mkdir(parents=True)
    cases = cases if cases is not None else [{'task_duration': 2, 'metrics': {'input_tokens': 50, 'output_tokens': 4}}]
    failures = failures or []
    for case in cases:
        case.setdefault('attributes', {}).setdefault('provider_usage_present', True)
    count = len(cases) + len(failures) if attempts is None else attempts
    record = {'agent': 'assessment', 'run': run, 'mode': mode, 'set': 'development',
              'summary': {'identity': {'model': model, 'dataset_sha256': dataset,
                                      'prompt_version': 'p1', 'config_version': 'c1',
                                      'skill_sha256': 's1', 'toolset_sha256': 't1'},
                          'attempts': count, 'clean_attempts': len(cases), 'task_failures': len(failures),
                          'assertions': {'structural_validity': {'passed': len(cases), 'total': len(cases)}}}}
    (path / 'summary.json').write_text(json.dumps(record))
    (path / 'evidence/report.json').write_text(json.dumps({'cases': cases, 'failures': failures}))
    return path


def test_metrics_aggregate_native_samples_not_run_means(root):
    metric_run(root, cases=[{'task_duration': 1, 'metrics': {'input_tokens': 10, 'output_tokens': 1}},
                            {'task_duration': 3, 'metrics': {'input_tokens': 30, 'output_tokens': 3}}],
               failures=[{'error_message': 'SECRET'}])
    metric_run(root, run='20261015-development-live')
    with serving(root) as server:
        status, _, data = request(server, '/api/metrics')
        assert status == 200 and b'SECRET' not in data
        group = next(g for g in json.loads(data)['groups'] if g['agent'] == 'assessment')
        assert group['runs'] == 2 and group['attempts'] == 4 and group['clean_attempts'] == 3
        assert group['task_failures'] == 1
        assert sorted(group['latency_seconds']) == [1, 2, 3]
        assert sorted(group['input_tokens']) == [10, 30, 50]
        assert group['telemetry_attempts'] == 3
        assert group['assertions']['structural_validity'] == {'passed': 3, 'total': 3}
        assert group['warnings']
        assert request(server, '/metrics')[0] == 200


def test_metrics_preserve_zero_exclude_incomplete_usage_and_invalid_numbers(root):
    metric_run(root, cases=[
        {'task_duration': 0, 'attributes': {'observed_input_tokens': 0, 'observed_output_tokens': 0}},
        {'task_duration': 1, 'attributes': {'provider_usage_present': False},
         'metrics': {'input_tokens': 123, 'output_tokens': 3}},
        {'task_duration': float('inf'), 'metrics': {'input_tokens': -1, 'output_tokens': True}}])
    group = next(g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment')
    assert group['latency_seconds'] == [0, 1]
    assert group['input_tokens'] == [0] and group['output_tokens'] == [0]
    assert group['telemetry_attempts'] == 2


def test_metrics_different_identity_and_modes_never_pool(root):
    metric_run(root)
    metric_run(root, run='different-model', model='other-model')
    metric_run(root, run='different-mode', mode='scripted')
    metric_run(root, run='different-dataset', dataset='dataset-b')
    groups = [g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment']
    assert len(groups) == 4
    assert all(g['runs'] == 1 for g in groups)


def test_metrics_unknown_identity_runs_stay_separate(root):
    for name in ('missing-identity-a', 'missing-identity-b'):
        path = metric_run(root, run=name)
        record = json.loads((path / 'summary.json').read_text())
        record['summary']['identity'].pop('toolset_sha256')
        (path / 'summary.json').write_text(json.dumps(record))
    groups = [g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment']
    assert len(groups) == 2 and all(g['warnings'] for g in groups)


def test_metrics_unavailable_reports_and_counts_remain_unknown(root):
    path = metric_run(root)
    record = json.loads((path / 'summary.json').read_text())
    record['summary'] = {'identity': record['summary']['identity'], 'report': 'missing'}
    (path / 'summary.json').write_text(json.dumps(record))
    (path / 'evidence/report.json').unlink()
    group = next(g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment')
    assert group['attempts'] is None and group['clean_attempts'] is None
    assert group['measured_runs'] == 0 and group['latency_seconds'] == []
    assert group['warnings']


def test_metrics_sample_cap_reports_incomplete_coverage(root, monkeypatch):
    import corsair.web.server as web
    monkeypatch.setattr(web, 'MAX_SAMPLES', 1)
    metric_run(root, cases=[{'task_duration': 1}, {'task_duration': 2}])
    group = next(g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment')
    assert group['attempts'] == 2
    assert len(group['latency_seconds']) == 1
    assert any('limit' in warning for warning in group['warnings'])


def test_metrics_inconsistent_report_counts_dont_invent_coverage(root):
    metric_run(root, attempts=3)
    group = next(g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment')
    assert group['attempts'] == 3 and group['latency_seconds'] == []
    assert any('disagree' in warning for warning in group['warnings'])



def test_live_metrics_missing_usage_flag_is_unknown_even_with_default_zero(root):
    path = metric_run(root, cases=[{'task_duration': 1, 'metrics': {'input_tokens': 0, 'output_tokens': 0}}])
    report = json.loads((path / 'evidence/report.json').read_text())
    report['cases'][0]['attributes'].pop('provider_usage_present')
    (path / 'evidence/report.json').write_text(json.dumps(report))
    group = next(g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment')
    assert group['input_tokens'] == [] and group['output_tokens'] == []
    assert group['latency_seconds'] == [1]
    assert any('usage coverage' in w for w in group['warnings'])


def test_hidden_provider_settings_separate_cohorts_without_exposing_secrets(root):
    for run, cap in (('setting-a', 2048), ('setting-b', 4096)):
        metric_run(root, run=run, model={'model_name': 'same-model', 'system': 'openai',
                                        'model_settings': {'max_tokens': cap, 'api_key': 'SECRET'}})
    groups = [g for g in Evidence(root).metrics()['groups'] if g['agent'] == 'assessment']
    assert len(groups) == 2
    assert all(g['model'] == {'model_name': 'same-model', 'system': 'openai'} for g in groups)
    assert 'SECRET' not in json.dumps(groups)
