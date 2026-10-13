"""Check the production image against existing real eval records, then remove owned containers.

Requires Docker, a built image and a results root populated by the actual eval runner.
Does not create results, deploy to Kubernetes, inherit credentials or call a model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request


def docker(*args: str) -> str:
    return subprocess.check_output(['docker', *args], text=True, timeout=60).strip()


def check(image: str, results: Path, runtime_matrix: Path) -> None:
    summaries = sorted(results.glob('*/*/summary.json'))
    if len(summaries) != 1:
        raise ValueError('Use an isolated results root with exactly one fresh scripted evals.run --results run')
    expected = json.loads(summaries[0].read_text())
    if expected['mode'] != 'scripted':
        raise ValueError('Smoke validation requires a scripted evaluation; no live model calls are made')
    native = json.loads((summaries[0].parent / 'evidence/report.json').read_text())
    durations = [case['task_duration'] for case in native['cases']]
    if not durations:
        raise ValueError('The native report must include measured completed cases')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for mounted in (True, False):
        args = ['run', '--detach', '--rm', '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8765',
                '--env', 'CORSAIR_UI_PUBLIC_ORIGIN=http://localhost:8765',
                '--mount', f'type=bind,source={runtime_matrix},target=/config/runtime-matrix.yaml,readonly']
        if mounted:
            args.extend(['--mount', f'type=bind,source={results},target=/data/evals,readonly'])
        cid = docker(*args, image)
        if not re.fullmatch('[0-9a-f]{64}', cid):
            raise RuntimeError('Docker did not return an immutable container ID')
        try:
            ports = json.loads(docker('inspect', '--format', '{{json .NetworkSettings.Ports}}', cid))
            port = ports['8765/tcp'][0]['HostPort']

            def request(path: str):
                request = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
                                                 headers={'Host': 'localhost:8765'})
                try:
                    response = opener.open(request, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    body = response.read()
                    if response.headers.get_content_type() == 'application/json':
                        body = json.loads(body)
                    return response.status, body

            for _ in range(80):
                try:
                    if request('/api/live')[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('UI container did not become live within 20 seconds')
            for path in ('/', '/agents', '/system', '/api/live', '/api/runtime'):
                assert request(path)[0] == 200, f'{path} unavailable'
            page = request('/')[1].decode()
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page):
                assert request(asset)[0] == 200, 'Production asset unavailable'
            ready_status, ready = request('/api/ready')
            assert ready_status == (200 if mounted else 503), 'Storage readiness was misreported'
            assert ready['ready'] is mounted
            eval_status, evaluations = request('/api/evaluations')
            assert eval_status == (200 if mounted else 503), 'Missing storage must not look empty'
            if mounted:
                actual = next(row for row in evaluations['runs'] if
                              (row['agent'], row['run']) == (expected['agent'], expected['run']))
                for key in ('attempts', 'clean_attempts', 'task_failures'):
                    assert actual['summary'].get(key) == expected['summary'].get(key), f'{key} differs from producer'
                metrics_status, metrics = request('/api/metrics')
                assert metrics_status == 200 and len(metrics['groups']) == 1, 'Expected one native metric cohort'
                group = metrics['groups'][0]
                for key in ('attempts', 'clean_attempts', 'task_failures'):
                    assert group[key] == expected['summary'][key], f'Aggregate {key} differs from producer'
                assert group['latency_seconds'] == durations, 'Latency distribution differs from native task durations'
                observed = [case['metrics'] for case in native['cases']]
                if all('observed_input_tokens' in row and 'observed_output_tokens' in row for row in observed):
                    for field in ('input_tokens', 'output_tokens'):
                        assert group[field] == [row['observed_' + field] for row in observed], f'{field} differ from native metrics'
                    assert group['total_tokens'] == [row['observed_input_tokens'] + row['observed_output_tokens']
                                                     for row in observed], 'Paired token distribution differs from native metrics'
                print('Real producer summary and native metrics match the mounted results.')
            status, health = request('/api/status')
            assert status == 200
            assert all(service['status'] == 'not_configured' for service in health['services'])
            assert request('/api/runs')[1]['status'] == 'not_configured'
            docker('exec', cid, 'python', '-c',
                   "from pathlib import Path; import os; assert os.getuid()==10001; "
                   "assert not any(Path(p).exists() for p in ('/app/.runs','/app/.state','/app/ui/e2e'))")
            print('Mounted results check passed.' if mounted else 'Missing results correctly fail readiness with HTTP 503.')
        finally:
            docker('stop', '--time', '5', cid)
            removed = subprocess.run(['docker', 'inspect', cid], capture_output=True, timeout=10)
            if removed.returncode != 1 or b'no such object' not in removed.stderr.lower():
                raise RuntimeError(f'Cleanup unconfirmed for owned container {cid}')
            print(f'Removed owned container {cid[:12]}.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--runtime-matrix', required=True, type=Path)
    args = parser.parse_args()
    check(args.image, args.results.resolve(strict=True), args.runtime_matrix.resolve(strict=True))


if __name__ == '__main__':
    main()
