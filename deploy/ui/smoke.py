"""Check the production image against existing real v2 records, then remove owned containers.

Requires Docker, a built image and a data root laid out like .runs: evals/ written by the actual eval runner (one
scripted chain eval) and v2/runs/ holding run records (corsair-v2-run/1).
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


def check(image: str, data: Path, runtime_matrix: Path) -> None:
    summaries = sorted((data / 'evals').glob('*/*/summary.json'))
    if len(summaries) != 1:
        raise ValueError('Use an isolated data root with exactly one fresh scripted evals.run --results run')
    expected = json.loads(summaries[0].read_text())
    if expected['mode'] != 'scripted':
        raise ValueError('Smoke validation requires a scripted evaluation; no live model calls are made')
    records = sorted(path.name for path in (data / 'v2' / 'runs').iterdir() if (path / 'summary.json').is_file())
    if not records:
        raise ValueError('The data root must hold at least one run record under v2/runs')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for mounted in (True, False):
        args = ['run', '--detach', '--rm', '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8765',
                '--env', 'CORSAIR_UI_PUBLIC_ORIGIN=http://localhost:8765',
                '--mount', f'type=bind,source={runtime_matrix},target=/config/runtime-matrix.yaml,readonly']
        if mounted:
            args.extend(['--mount', f'type=bind,source={data},target=/data,readonly'])
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
            for path in ('/', '/runs', '/agents', '/system', '/api/live', '/api/runtime'):
                assert request(path)[0] == 200, f'{path} unavailable'
            page = request('/')[1].decode()
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page):
                assert request(asset)[0] == 200, 'Production asset unavailable'
            ready_status, ready = request('/api/ready')
            assert ready_status == (200 if mounted else 503), 'Storage readiness was misreported'
            assert ready['ready'] is mounted
            eval_status, evaluations = request('/api/evaluations')
            runs_status, runs = request('/api/runs')
            assert eval_status == runs_status == (200 if mounted else 503), 'Missing storage must not look empty'
            if mounted:
                actual = next(row for row in evaluations['runs'] if
                              (row['agent'], row['run']) == (expected['agent'], expected['run']))
                overall = expected['rollups']['all']
                for key in ('attempts', 'clean_attempts', 'task_failures'):
                    assert actual['overall'][key] == overall[key], f'{key} differs from producer'
                detail = request(f"/api/evaluations/{expected['agent']}/{expected['run']}")[1]
                assert len(detail['attempts']) == len(expected['attempts']), 'Attempt rows differ from producer'
                assert sorted(row['id'] for row in runs['runs']) == records, 'Run records differ from storage'
                for name in records:
                    summary = json.loads((data / 'v2' / 'runs' / name / 'summary.json').read_text())
                    shown = request(f'/api/runs/{name}')[1]
                    assert (shown['label'], shown['rule']) == (summary['label'], summary['rule_id']), 'Verdict differs'
                print('Real producer summaries and run records match the mounted data.')
            status, health = request('/api/status')
            assert status == 200
            assert all(service['status'] == 'not_configured' for service in health['services'])
            assert request('/api/workflows')[1]['status'] == 'not_configured'
            docker('exec', cid, 'python', '-c',
                   "from pathlib import Path; import os; assert os.getuid()==10001; "
                   "assert not any(Path(p).exists() for p in ('/app/.runs','/app/.state','/app/ui/e2e')); "
                   "assert Path('/app/evals/e2e/baselines/README.md').is_file(); "
                   "assert not Path('/app/evals/e2e/v2').exists()")
            print('Mounted data check passed.' if mounted else 'Missing data correctly fails readiness with HTTP 503.')
        finally:
            docker('stop', '--time', '5', cid)
            # --rm can finish after stop returns. Confirm absence through a successful
            # native listing, without depending on Docker's version-specific error text.
            for _ in range(20):
                if not docker('container', 'ls', '--all', '--no-trunc', '--filter', f'id={cid}', '--format', '{{.ID}}'):
                    break
                time.sleep(.25)
            else:
                raise RuntimeError(f'Cleanup unconfirmed for owned container {cid}')
            print(f'Removed owned container {cid[:12]}.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--data', required=True, type=Path, help='Root holding evals/ and v2/runs/')
    parser.add_argument('--runtime-matrix', required=True, type=Path)
    args = parser.parse_args()
    check(args.image, args.data.resolve(strict=True), args.runtime_matrix.resolve(strict=True))


if __name__ == '__main__':
    main()
