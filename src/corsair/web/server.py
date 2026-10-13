"""A loopback-only evidence viewer; no workload execution or configuration writes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit

AGENTS = ('environment', 'identification', 'planning', 'authoring', 'assessment', 'chain')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z')
MAX_JSON = 4 * 1024 * 1024
MAX_STATIC = 8 * 1024 * 1024
MAX_RUNS = 500
MAX_ENTRIES = 2000
MAX_SAMPLES = 20000
MAX_REPORTS = 100
IDENTITY = ('prompt_version', 'config_version', 'skill_sha256', 'toolset_sha256', 'model',
            'dataset', 'dataset_sha256', 'mode', 'runner', 'execution', 'composition')
METRIC = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,100}\Z')
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
        '.ico': 'image/x-icon', '.woff2': 'font/woff2'}


class EvidenceError(ValueError):
    """Missing, unsafe or malformed evidence, without leaking file contents."""


@contextmanager
def directory(root: Path, parts: tuple[str, ...] = ()):
    """Use directory descriptors and O_NOFOLLOW throughout to reject symlink swaps."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def read_file(root: Path, parts: tuple[str, ...], limit: int) -> bytes:
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', p) or p in ('.', '..') for p in parts):
        raise EvidenceError('Invalid evidence path')
    with directory(root, parts[:-1]) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise EvidenceError('Evidence exceeds the size limit or is not a regular file')
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise EvidenceError('Evidence exceeds the size limit')
            return data


def read_json(root: Path, parts: tuple[str, ...]) -> dict:
    try:
        value = json.loads(read_file(root, parts, MAX_JSON))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EvidenceError('Evidence is not valid JSON') from error
    if not isinstance(value, dict):
        raise EvidenceError('Evidence must be an object')
    return value


def obj(value):
    return value if isinstance(value, dict) else {}


def number(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and abs(value) <= 1e100 and math.isfinite(value))


def text_fields(value, keys):
    return {k: v[:500] for k, v in obj(value).items() if k in keys and isinstance(v, str)}


def numeric_fields(value, keys):
    return {k: v for k, v in obj(value).items() if k in keys and number(v)}


def counts(value, keys, pair=None):
    result = {}
    for key, value in obj(value).items():
        if key not in keys:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10**12:
            raise EvidenceError('Invalid evidence count')
        result[key] = value
    if pair and all(key in result for key in pair) and result[pair[0]] > result[pair[1]]:
        raise EvidenceError('Inconsistent evidence counts')
    return result


def named_numbers(value, keys):
    return {k: counts(v, keys, keys) for k, v in list(obj(value).items())[:500]
            if METRIC.fullmatch(k)}


def project(record: dict, agent: str, run: str) -> dict:
    if record.get('agent') != agent or record.get('run') != run:
        raise EvidenceError('Evidence identity does not match its directory')
    source = obj(record.get('summary'))
    identity = obj(source.get('identity'))
    safe_identity = text_fields(identity, IDENTITY)
    if isinstance(identity.get('model'), dict):
        safe_identity['model'] = text_fields(identity['model'], ('model_name', 'system'))
    safe_identity['versions'] = {k: text_fields(v, IDENTITY) for k, v in obj(identity.get('versions')).items()
                                 if k in AGENTS}
    if isinstance(identity.get('live_stages'), list):
        safe_identity['live_stages'] = [s for s in identity['live_stages'] if s in AGENTS]
    safe_identity['budget'] = numeric_fields(identity.get('budget'),
        ('requests', 'request_limit', 'tool_calls', 'tool_calls_limit', 'input_tokens', 'output_tokens',
         'total_tokens', 'input_tokens_limit', 'output_tokens_limit', 'total_tokens_limit', 'max_tokens',
         'task_seconds', 'response_token_limit', 'output_retries', 'repeat'))
    summary = counts(source, ('attempts', 'clean_attempts', 'task_failures'), ('clean_attempts', 'attempts'))
    if (summary.get('task_failures', 0) + summary.get('clean_attempts', 0)
            > summary.get('attempts', 10**12)):
        raise EvidenceError('Inconsistent failure count')
    summary.update(identity=safe_identity,
        assertions=named_numbers(source.get('assertions'), ('passed', 'total')),
        efficiency_samples=named_numbers(source.get('efficiency_samples'), ('observed', 'attempts')),
        efficiency_mean={k: v for k, v in list(obj(source.get('efficiency_mean')).items())[:500]
                         if METRIC.fullmatch(k) and number(v)},
        cases={k[:160]: counts(v, ('attempts', 'clean'), ('clean', 'attempts')) | {
            'failed_assertions': {a: n for a, n in list(obj(obj(v).get('failed_assertions')).items())[:100]
                                  if METRIC.fullmatch(a) and number(n)},
            'task_failure_count': len(obj(v).get('task_failures', []))
                if isinstance(obj(v).get('task_failures'), list) else 0}
            for k, v in list(obj(source.get('cases')).items())[:500]})
    if source.get('report') == 'missing':
        summary['report'] = 'missing'
    command = text_fields(record.get('command'), ('git_commit', 'started', 'ended', 'suite_note'))
    command.update(numeric_fields(record.get('command'), ('exit_code',)))
    if isinstance(obj(record.get('command')).get('git_dirty'), bool):
        command['git_dirty'] = record['command']['git_dirty']
    return {'agent': agent, 'run': run, **text_fields(record, ('set', 'mode')),
            'command': command, 'summary': summary}


class Evidence:
    def __init__(self, root: Path):
        # The operator chooses this root, but symlinks beneath it are never followed.
        self.root = root.resolve(strict=True)

    def detail(self, agent: str, run: str) -> dict:
        if agent not in AGENTS or not NAME.fullmatch(run) or run in ('.', '..'):
            raise EvidenceError('Invalid run identifier')
        parts = ('.runs', 'evals', agent, run)
        result = project(read_json(self.root, parts + ('summary.json',)), agent, run)
        # Native reports contain inputs, outputs and arbitrary exception text. Only expose counts.
        try:
            report = read_json(self.root, parts + ('evidence', 'report.json'))
            result['report'] = {
                'completed_attempts': len(report['cases']) if isinstance(report.get('cases'), list) else None,
                'failed_attempts': len(report['failures']) if isinstance(report.get('failures'), list) else None}
        except (OSError, EvidenceError):
            result['report'] = {'available': False}
        return result

    def evaluations(self) -> dict:
        candidates, warnings = [], []
        for agent in AGENTS:
            try:
                with directory(self.root, ('.runs', 'evals', agent)) as fd:
                    with os.scandir(fd) as entries:
                        for index, entry in enumerate(entries):
                            if index >= MAX_ENTRIES:
                                warnings.append(f'{agent}: directory scan limit reached; some runs omitted.')
                                break
                            if NAME.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False):
                                candidates.append((entry.name, agent))
            except FileNotFoundError:
                continue
            except OSError:
                warnings.append(f'{agent}: evidence directory could not be read safely.')
        if len(candidates) > MAX_RUNS:
            warnings.append(f'Showing at most {MAX_RUNS} recent runs; older runs omitted.')
        runs = []
        for run, agent in sorted(candidates, reverse=True)[:MAX_RUNS]:
            try:
                runs.append(project(read_json(self.root, ('.runs', 'evals', agent, run, 'summary.json')), agent, run))
            except (OSError, EvidenceError):
                warnings.append(f'{agent}/{run}: summary unavailable, malformed or unsafe; omitted.')
        return {'runs': runs, 'warnings': warnings}

    def metrics(self) -> dict:
        listing = self.evaluations()
        groups = {}
        sampled_cases = 0
        reports_read = 0
        warnings = list(listing['warnings'])
        for record in listing['runs']:
            agent, run = record['agent'], record['run']
            parts = ('.runs', 'evals', agent, run)
            try:
                raw = read_json(self.root, parts + ('summary.json',))
                # Revalidate after rereading: the producer may still be replacing records.
                record = project(raw, agent, run)
                identity = obj(obj(raw.get('summary')).get('identity'))
                digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
            except (OSError, ValueError, RecursionError):
                warnings.append(f'{agent}/{run}: identity unavailable; metrics omitted.')
                continue
            safe = record['summary']['identity']
            version_keys = ('prompt_version', 'config_version', 'skill_sha256', 'toolset_sha256')
            versions = obj(identity.get('versions'))
            has_versions = all(identity.get(k) for k in version_keys) or (
                bool(versions) and all(isinstance(v, dict) and all(v.get(k) for k in version_keys)
                                       for v in versions.values()))
            model = safe.get('model')
            has_model = bool(model) if isinstance(model, str) else bool(obj(model).get('model_name'))
            complete_identity = (bool(safe.get('dataset_sha256')) and has_model
                                 and has_versions and bool(record.get('mode')) and bool(record.get('set')))
            key = (agent, record.get('mode'), record.get('set'), digest, None if complete_identity else run)
            if key not in groups:
                groups[key] = {
                    'id': hashlib.sha256(json.dumps(key).encode()).hexdigest(), 'agent': agent,
                    'mode': record.get('mode'), 'set': record.get('set'),
                    'dataset_sha256': safe.get('dataset_sha256'), 'model': safe.get('model'),
                    'identity_digest': digest, 'runs': 0, 'measured_runs': 0,
                    'attempts': None, 'clean_attempts': None, 'task_failures': None,
                    'latency_seconds': [], 'input_tokens': [], 'output_tokens': [],
                    'telemetry_attempts': 0, 'assertions': {},
                    'warnings': [] if complete_identity else ['Incomplete identity; this run is kept separate.']}
            group = groups[key]
            group['runs'] += 1
            summary = record['summary']
            count_keys = ('attempts', 'clean_attempts', 'task_failures')
            complete_counts = all(k in summary for k in count_keys) and summary.get('report') != 'missing'
            if complete_counts:
                group['measured_runs'] += 1
                for field in count_keys:
                    group[field] = (group[field] or 0) + summary[field]
                for name, values in summary['assertions'].items():
                    if set(values) != {'passed', 'total'}:
                        continue
                    entry = group['assertions'].setdefault(name, {'passed': 0, 'total': 0})
                    for field in ('passed', 'total'):
                        entry[field] += values[field]
            else:
                group['warnings'].append('A run has incomplete counts; it is excluded from aggregate rates.')
            if reports_read >= MAX_REPORTS or sampled_cases >= MAX_SAMPLES:
                group['warnings'].append('Native report sample limit reached; distribution coverage is incomplete.')
                continue
            reports_read += 1
            try:
                report = read_json(self.root, parts + ('evidence', 'report.json'))
            except (OSError, EvidenceError):
                group['warnings'].append('Native report unavailable; no distribution samples for this run.')
                continue
            cases, failures = report.get('cases'), report.get('failures')
            if not isinstance(cases, list) or not isinstance(failures, list):
                group['warnings'].append('Native report has incomplete attempt lists; samples omitted.')
                continue
            if complete_counts and (len(cases) + len(failures) != summary['attempts']
                                    or len(failures) != summary['task_failures']):
                group['warnings'].append('Native report and summary counts disagree; samples omitted.')
                continue
            for case in cases:
                if sampled_cases >= MAX_SAMPLES:
                    group['warnings'].append('Native report sample limit reached; distribution coverage is incomplete.')
                    break
                sampled_cases += 1
                if not isinstance(case, dict):
                    continue
                observed = False
                duration = case.get('task_duration')
                if number(duration) and duration >= 0:
                    group['latency_seconds'].append(duration)
                    observed = True
                attributes, metrics = obj(case.get('attributes')), obj(case.get('metrics'))
                usage_present = attributes.get('provider_usage_present')
                token_coverage = usage_present is True or (record.get('mode') == 'scripted' and usage_present is not False)
                if not token_coverage:
                    group['warnings'].append('Token samples without complete provider usage coverage are excluded.')
                if token_coverage:
                    for field in ('input_tokens', 'output_tokens'):
                        # Native metrics take precedence; attributes retain measured zero increments.
                        candidates = (metrics.get('observed_' + field), metrics.get(field),
                                      attributes.get('observed_' + field))
                        value = next((v for v in candidates if number(v) and v >= 0 and int(v) == v), None)
                        if value is not None:
                            group[field].append(value)
                            observed = True
                if observed:
                    group['telemetry_attempts'] += 1
            if failures:
                group['warnings'].append('Task failures contribute to attempt counts; failed-attempt telemetry is unavailable.')
        for group in groups.values():
            group['warnings'] = list(dict.fromkeys(group['warnings']))
        return {'groups': list(groups.values()), 'warnings': warnings}

    def runtime(self) -> dict:
        import yaml
        from corsair.nodes.runtime.matrix import Matrix
        try:
            matrix = Matrix.model_validate(yaml.safe_load(read_file(
                self.root, ('deploy', 'runtime-matrix.yaml'), MAX_JSON)))
        except (ValueError, yaml.YAMLError) as error:
            raise EvidenceError('Runtime matrix is invalid') from error
        return {'rows': [row.model_dump(mode='json') | {'frameworks': [f.model_dump(mode='json')
                        for f in matrix.frameworks if f.applies(row)]} for row in matrix.images],
                'limitations': ['Image-only evidence is not OpenShell qualification.',
                                'Matrix records describe bounded qualification; they do not establish end-to-end readiness.']}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root: Path, port: int = 8765):
        self.evidence = Evidence(root)
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'Corsair'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass  # Do not echo untrusted URLs or evidence into terminal logs.

    def respond(self, status: int, data: bytes, content_type: str = 'application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def error(self, status, message):
        self.respond(status, json.dumps({'error': message}).encode())

    def allowed(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        host = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        return (len(host) == 1 and host[0] in hosts and
                (not origins or origins == [f'http://{host[0]}']) and
                self.headers.get('Sec-Fetch-Site') not in ('cross-site',))

    def do_GET(self):
        if not self.allowed():
            return self.error(403, 'Only same-origin loopback requests are accepted')
        try:
            url = urlsplit(self.path)
            path = unquote(url.path, errors='strict')
            if (url.scheme or url.netloc or url.fragment or '\\' in path or '\x00' in path
                    or (url.query and path.startswith('/api/'))):
                return self.error(400, 'Invalid request path')
            parts = tuple(path.strip('/').split('/'))
            if any(p in ('.', '..') for p in parts):
                return self.error(400, 'Invalid request path')
            if path == '/api/health':
                result = {'service': 'corsair', 'version': '0.0.0', 'read_only': True}
            elif path == '/api/evaluations':
                result = self.server.evidence.evaluations()
            elif len(parts) == 4 and parts[:2] == ('api', 'evaluations'):
                result = self.server.evidence.detail(parts[2], parts[3])
            elif path == '/api/metrics':
                result = self.server.evidence.metrics()
            elif path == '/api/runtime':
                result = self.server.evidence.runtime()
            elif path.startswith('/api/'):
                return self.error(404, 'Unknown endpoint')
            else:
                spa = path in ('/', '/evaluations', '/runtime', '/metrics') or (
                    len(parts) == 3 and parts[0] == 'evaluations' and parts[1] in AGENTS
                    and NAME.fullmatch(parts[2]))
                static_parts = ('index.html',) if spa else parts
                suffix = Path(static_parts[-1]).suffix
                if suffix not in MIME:
                    return self.error(404, 'Static asset not found')
                data = read_file(self.server.evidence.root, ('ui', 'dist') + static_parts, MAX_STATIC)
                return self.respond(200, data, MIME[suffix])
            self.respond(200, json.dumps(result, allow_nan=False).encode())
        except FileNotFoundError:
            self.error(404, 'Evidence or UI assets not found; build the UI and run an evaluation first')
        except (OSError, EvidenceError, UnicodeError, ValueError, RecursionError):
            self.error(422, 'Evidence could not be read safely; check the local record and size limits')

    do_HEAD = do_GET

    def do_POST(self):
        self.error(405, 'This viewer is read-only')

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='Corsair checkout containing .runs and ui/dist')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with Server(args.root, args.port) as server:
        print(f'Corsair read-only viewer: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
