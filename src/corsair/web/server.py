"""Read-only view of v2 records, with a local HTTP adapter and a production WSGI adapter.

Two record families, both written by v2 itself and never by this module:

- run records (``corsair-v2-run/1``, ``src/corsair/RUN_RECORD.md``): one directory per chain run, from
  ``corsair-v2 run`` under the runs root (default ``.runs/v2/runs``) and, for every chain eval attempt, the copy
  the eval keeps under ``<results>/chain/<run>/evidence/runs/<receipt>``;
- eval runs (``corsair-eval-summary/v1``, ``evals/agent_summary.py``): ``<results>/<agent>/<run>/`` with
  ``summary.json``, ``policy.json`` and ``command.json`` (default results root ``.runs/evals``), plus committed
  baselines beside each agent's cases.

Every value is projected through an allow-list before it leaves the server. Message histories, stage outputs,
probe output, provider error text and task failure text are never returned. Null stays null (unknown, never zero).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import Message
import hashlib
import heapq
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit

RUN_SCHEMA = 'corsair-v2-run/1'
EVAL_SCHEMA = 'corsair-eval-summary/v1'
# The six v2 agents and the whole chain (evals/cases.py AGENTS + CHAIN; tests/ui pins the two lists together).
AGENTS = ('grounding', 'investigator', 'builder', 'control_prober', 'exploit_prober', 'reviewer', 'chain')
LABELS = ('LIKELY_EXPLOITABLE', 'LIKELY_NOT_EXPLOITABLE', 'INCONCLUSIVE', 'UNABLE_TO_RUN', 'ERROR')
METRICS = ('wall_s', 'requests', 'tool_calls', 'input_tokens', 'output_tokens', 'tokens', 'retries')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z')
KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}\Z')
MAX_JSON = 4 * 1024 * 1024
MAX_STATIC = 8 * 1024 * 1024
MAX_RUNS = 500
MAX_ENTRIES = 2000
MAX_ROWS = 2000
TEXT = 500
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
        '.ico': 'image/x-icon', '.woff2': 'font/woff2'}


class SourceUnavailable(OSError):
    """A configured source cannot be read; never interpret this as zero records."""


class EvidenceError(ValueError):
    """Missing, unsafe or malformed evidence, without leaking file contents."""


@contextmanager
def directory(root: Path, parts: tuple[str, ...] = ()):
    """Directory descriptors and O_NOFOLLOW throughout, so a symlink swap cannot redirect a read."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _check_parts(parts: tuple[str, ...]) -> None:
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', p) or p in ('.', '..') for p in parts):
        raise EvidenceError('Invalid evidence path')


def read_file(root: Path, parts: tuple[str, ...], limit: int) -> bytes:
    _check_parts(parts)
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


def read_json(root: Path, parts: tuple[str, ...], kind: type = dict):
    try:
        value = json.loads(read_file(root, parts, MAX_JSON))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EvidenceError('Evidence is not valid JSON') from error
    if not isinstance(value, kind):
        raise EvidenceError('Evidence has an unexpected shape')
    return value


def optional_json(root: Path, parts: tuple[str, ...], kind: type = dict):
    """A file the record may lack: absent is None; present but unreadable or malformed is an error."""
    try:
        return read_json(root, parts, kind)
    except FileNotFoundError:
        return None


def newest(names, limit: int = MAX_ENTRIES) -> tuple[list[str], bool]:
    """The ``limit`` lexically greatest of ``names``, newest first, and whether any were left out. Every name is
    seen before the cut, so scan order (unspecified for a directory) never decides which records are shown."""
    kept, limited = [], False
    for name in names:
        if len(kept) < limit:
            heapq.heappush(kept, name)
        else:
            limited = True
            heapq.heappushpop(kept, name)
    return sorted(kept, reverse=True), limited


def entries(root: Path, parts: tuple[str, ...]) -> tuple[list[str], bool]:
    """Directory names (no symlinks) in ``parts``, newest name first, and whether the limit cut it short."""
    with directory(root, parts) as fd, os.scandir(fd) as found:
        return newest(entry.name for entry in found
                      if NAME.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False))


def is_dir(root: Path, parts: tuple[str, ...]) -> bool:
    try:
        with directory(root, parts):
            return True
    except OSError:
        return False


# --- allow-list projections -----------------------------------------------------------------------------------


def obj(value) -> dict:
    return value if isinstance(value, dict) else {}


def text(value, limit: int = TEXT) -> str | None:
    return value[:limit] if isinstance(value, str) else None


def number(value) -> float | int | None:
    ok = (isinstance(value, (float, int)) and not isinstance(value, bool)
          and abs(value) <= 1e100 and math.isfinite(value))
    return value if ok else None


def count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10**12 else None


def flag(value) -> bool | None:
    return value if isinstance(value, bool) else None


def plain(value, depth: int = 3):
    """JSON scalars, short strings and small nested containers with plain keys; anything else is dropped."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return number(value)
    if isinstance(value, str):
        return value[:TEXT]
    if depth <= 0:
        return None
    if isinstance(value, list):
        return [plain(item, depth - 1) for item in value[:50]]
    if isinstance(value, dict):
        return {k: plain(v, depth - 1) for k, v in list(value.items())[:100] if isinstance(k, str) and KEY.fullmatch(k)}
    return None


def ratio(value) -> dict | None:
    value = obj(value)
    passed, total = count(value.get('passed')), count(value.get('total'))
    if passed is None or total is None or passed > total:
        return None
    return {'passed': passed, 'total': total}


def stats(value) -> dict:
    value = obj(value)
    return {'observed': count(value.get('observed')),
            **{key: number(value.get(key)) for key in ('mean', 'p50', 'p90', 'total')}}


def named(value, project) -> dict:
    return {k: v for k, raw in list(obj(value).items())[:200]
            if isinstance(k, str) and KEY.fullmatch(k) and (v := project(raw)) is not None}


def dispositions(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    abstentions = {}
    for label, entry in obj(value.get('abstentions')).items():
        if label in LABELS:
            entry = obj(entry)
            abstentions[label] = {'count': count(entry.get('count')), 'rate': number(entry.get('rate')),
                                  'by_terminal_reason': named(entry.get('by_terminal_reason'), count)}
    return {'runs': count(value.get('runs')), 'decisive': count(value.get('decisive')),
            'decisive_rate': number(value.get('decisive_rate')),
            'decisive_correct': count(value.get('decisive_correct')),
            'accuracy_by_expected_label': {k: v for k, v in named(value.get('accuracy_by_expected_label'), ratio).items()
                                           if k in LABELS},
            'abstentions': abstentions}


def rollup(value, *, parameters: bool = False) -> dict | None:
    """One ``evals/agent_summary.py rollup``: counts, completion, dimensions, dispositions and efficiency."""
    if not isinstance(value, dict):
        return None
    completion = obj(value.get('completion'))
    result = {key: count(value.get(key)) for key in ('cases', 'attempts', 'clean_attempts', 'task_failures',
                                                     'status_unreported')}
    if result['clean_attempts'] is not None and result['attempts'] is not None \
            and result['clean_attempts'] > result['attempts']:
        raise EvidenceError('Inconsistent attempt counts')
    result |= {
        'completion': {**{key: count(completion.get(key)) for key in (
            'attempted', 'completed', 'task_failures', 'evaluator_failures', 'unknown_failures')},
            'rate': number(completion.get('rate'))} if completion else None,
        'dimensions': named(value.get('dimensions'), ratio),
        'dispositions': dispositions(value.get('dispositions')),
        'statuses': named(value.get('statuses'), count),
        'metrics': {metric: stats(value.get(metric)) for metric in METRICS},
        'revisions': stats(value['revisions']) if isinstance(value.get('revisions'), dict) else None,
        'accepted_within_limit': ratio(value.get('accepted_within_limit')),
    }
    if parameters:
        result['parameters'] = plain(value.get('parameters'), 4) if isinstance(value.get('parameters'), dict) else {}
    return result


def policy(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    entries_ = {}
    for name, entry in list(obj(value.get('entries')).items())[:200]:
        entry = obj(entry)
        if isinstance(name, str) and KEY.fullmatch(name):
            entries_[name] = {'status': text(entry.get('status'), 32), 'value': number(entry.get('value')),
                              'limit': number(entry.get('limit'))}
    return {'status': text(value.get('status'), 32), 'deferred': flag(value.get('deferred')),
            'in_scope': flag(value.get('in_scope')), 'entries': entries_,
            'missing_provenance': [text(v, 80) for v in value.get('missing_provenance', [])[:50]
                                   if isinstance(v, str)] if isinstance(value.get('missing_provenance'), list) else []}


def command(value) -> dict:
    value = obj(value)
    return {'git_commit': text(value.get('git_commit'), 64), 'git_dirty': flag(value.get('git_dirty')),
            'started': text(value.get('started'), 64), 'ended': text(value.get('ended'), 64),
            'exit_code': number(value.get('exit_code')), 'note': text(value.get('note'))}


def eval_run(summary: dict, agent: str, run: str, *, detail: bool = False) -> dict:
    """One eval run's summary; the per-attempt rows only in detail, without failure text."""
    if summary.get('schema') != EVAL_SCHEMA:
        raise EvidenceError('Not a v2 eval summary')
    if summary.get('agent') != agent or summary.get('run') != run:
        raise EvidenceError('Evidence identity does not match its directory')
    rollups = summary.get('rollups')
    result = {'agent': agent, 'run': run, 'set': text(summary.get('set'), 160),
              'language': text(summary.get('language'), 32), 'mode': text(summary.get('mode'), 32),
              'identity': plain(summary.get('identity'), 2) if isinstance(summary.get('identity'), dict) else {},
              'report': 'missing' if summary.get('report') == 'missing' or rollups is None else 'present',
              'overall': rollup(obj(rollups).get('all'), parameters=detail)}
    if detail:
        result['by_language'] = {k: rollup(v) for k, v in list(obj(obj(rollups).get('by_language')).items())[:20]
                                 if isinstance(k, str) and KEY.fullmatch(k)}
        result['by_kind'] = {k: rollup(v) for k, v in list(obj(obj(rollups).get('by_kind')).items())[:50]
                             if isinstance(k, str) and KEY.fullmatch(k)}
        rows = summary.get('attempts') if isinstance(summary.get('attempts'), list) else []
        result['attempts'] = [attempt(row) for row in rows[:MAX_ROWS] if isinstance(row, dict)]
        result['attempts_limited'] = len(rows) > MAX_ROWS
    return result


def attempt(row: dict) -> dict:
    return {'case': text(row.get('case'), 200), 'language': text(row.get('language'), 32),
            'kind': text(row.get('kind'), 64), 'receipt': text(row.get('receipt'), 32) if isinstance(
                row.get('receipt'), str) and NAME.fullmatch(row['receipt']) else None,
            'status': text(row.get('status'), 32), 'passed': flag(row.get('passed')),
            'dimensions': named(row.get('dimensions'), flag),
            'failed_assertions': [v[:100] for v in row.get('failed_assertions', [])[:50] if isinstance(v, str)]
            if isinstance(row.get('failed_assertions'), list) else [],
            # failure text can carry inputs and exceptions; only its kind is shown
            'failed': row.get('failure') is not None, 'failure_kind': text(row.get('failure_kind'), 32),
            **{key: number(row.get(key)) for key in (*METRICS, 'revisions')},
            **{key: text(row.get(key), 64) for key in ('label', 'expected_label', 'terminal_reason')}}


def run_state(run: dict, summary: dict) -> str:
    """As ``corsair.runs.details``: an unfinished file proves only an incomplete record, never active work."""
    if summary.get('label'):
        return 'completed'
    return run.get('state') if run.get('state') in ('completed', 'cancelled') else 'incomplete'


def agent_totals(value) -> dict:
    keys = ('calls', 'requests', 'input_tokens', 'output_tokens', 'tool_calls', 'retries')
    return {name: {**{key: count(entry.get(key)) for key in keys}, 'wall_s': number(entry.get('wall_s')),
                   'models': [text(m, 120) for m in entry.get('models', [])[:10] if isinstance(m, str)]
                   if isinstance(entry.get('models'), list) else [],
                   'prompt_versions': [text(m, 120) for m in entry.get('prompt_versions', [])[:10] if isinstance(m, str)]
                   if isinstance(entry.get('prompt_versions'), list) else [],
                   'steps': [text(m, 80) for m in entry.get('steps', [])[:50] if isinstance(m, str)]
                   if isinstance(entry.get('steps'), list) else [],
                   'statuses': named(entry.get('statuses'), count)}
            for name, entry in list(obj(value).items())[:20]
            if isinstance(name, str) and KEY.fullmatch(name) and isinstance(entry, dict)}


def totals(value) -> dict:
    value = obj(value)
    return {key: number(value.get(key)) for key in ('agent_calls', 'requests', 'input_tokens', 'output_tokens',
                                                    'tokens', 'tool_calls', 'retries', 'agent_wall_s', 'wall_s')}


def run_row(run: dict, summary: dict, name: str) -> dict:
    """The comparison row of ``corsair-v2 runs compare`` (``corsair.runs.row``), plus times and runtime."""
    for record in (run, summary):
        if record and record.get('schema') not in (None, RUN_SCHEMA):
            raise EvidenceError('Not a v2 run record')
    recorded = text(summary.get('run_id'), 160) or text(run.get('run_id'), 160)
    agents = obj(summary.get('agents'))
    models = summary.get('models') if isinstance(summary.get('models'), list) else sorted(
        {m for a in agents.values() for m in obj(a).get('models', []) if isinstance(m, str)})
    # `id` is the directory (what links address); `run` the recorded run id. They differ for a chain eval
    # attempt, whose copy is stored under its receipt number.
    return {'id': name, 'run': recorded or name, 'case': text(summary.get('case_id'), 160) or text(run.get('case_id'), 160),
            'mode': text(summary.get('mode'), 32) or text(run.get('mode'), 32),
            'label': text(summary.get('label'), 64), 'rule': text(summary.get('rule_id'), 16),
            'reason': text(summary.get('terminal_reason'), 64), 'finding': text(summary.get('finding'), 64),
            'fix': text(summary.get('fix'), 64), 'sensitivity': text(summary.get('sensitivity'), 32),
            'state': run_state(run, summary), 'started': text(run.get('started_at'), 64),
            'finished': text(run.get('finished_at'), 64), 'runtime_row': text(run.get('runtime_row'), 128),
            'models': [text(m, 120) for m in models[:10] if isinstance(m, str)],
            'totals': totals(summary.get('totals'))}


def probe(value) -> dict:
    value = obj(value)
    facts = obj(value.get('facts'))
    return {'outcome': text(value.get('outcome'), 64), 'duration_s': number(value.get('duration_s')),
            'patch_sha256': text(value.get('patch_sha256'), 64), 'image_digest': text(value.get('image_digest'), 256),
            'tree_sha256': text(value.get('tree_sha256'), 64), 'cleanup_confirmed': flag(value.get('cleanup_confirmed')),
            'facts': {'exit_code': number(facts.get('exit_code')), 'exit_class': text(facts.get('exit_class'), 32),
                      'timed_out': flag(facts.get('timed_out')), 'start_marker': flag(facts.get('start_marker')),
                      'end_marker': flag(facts.get('end_marker')), 'token_in_output': flag(facts.get('token_in_output')),
                      'check_marker': text(facts.get('check_marker'), 32)}}


def validity(value) -> list[dict]:
    """The Reviewer's outcome-blind judgement per frozen pair: booleans, defects and cited lines."""
    result = []
    for pair in value[:10] if isinstance(value, list) else []:
        pair = obj(pair)
        roles = {}
        for role in ('control', 'exploit'):
            entry = obj(pair.get(role))
            if not entry:
                continue
            roles[role] = {
                **{key: flag(entry.get(key)) for key in ('valid', 'calls_real_target', 'exercises_condition',
                                                         'assertion_relevant', 'doubles_only_dependencies')},
                'defects': [text(d) for d in entry.get('defects', [])[:20] if isinstance(d, str)]
                if isinstance(entry.get('defects'), list) else [],
                'citations': [{'path': text(obj(c).get('path'), 300), 'start_line': count(obj(c).get('start_line')),
                               'end_line': count(obj(c).get('end_line'))}
                              for c in entry.get('citations', [])[:20]] if isinstance(entry.get('citations'), list) else []}
        result.append({'patch_sha256': text(pair.get('patch_sha256'), 64), 'revision': text(pair.get('revision'), 32),
                       'roles': roles})
    return result


def run_detail(root: Path, parts: tuple[str, ...]) -> dict:
    """A run directory's record, projected; requires run.json or summary.json like ``corsair.runs.details``."""
    if not is_dir(root, parts):
        raise FileNotFoundError('run directory')
    run = optional_json(root, parts + ('run.json',)) or {}
    summary = optional_json(root, parts + ('summary.json',)) or {}
    if not run and not summary:
        raise EvidenceError('No run.json or summary.json in the record')
    case = optional_json(root, parts + ('case.json',)) or {}
    verdict = optional_json(root, parts + ('verdict.json',)) or {}
    timings = optional_json(root, parts + ('timings.json',), list) or []
    usage = optional_json(root, parts + ('usage.json',), list)
    outcome = obj(summary.get('outcome'))
    review = obj(summary.get('review'))
    finding = obj(case.get('finding'))
    revisions = {}
    for key in ('revision', 'fixed_revision'):
        value = obj(run.get(key)) or obj(case.get(key))
        revisions[key] = {'tree_sha256': text(value.get('tree_sha256'), 64), 'commit': text(value.get('commit'), 64)} \
            if value else None
    return {
        **run_row(run, summary, parts[-1]),
        'record': 'run.json' if run else 'summary.json',
        'provenance': {**{key: text(run.get(key), 256) for key in (
            'hostname', 'stopped_at', 'last_started_step', 'git_commit', 'provider_config_sha256', 'matrix_sha256',
            'runtime_row', 'runtime_image', 'runtime_image_id')}, 'git_dirty': flag(run.get('git_dirty')),
            **revisions,
            'environments': {name: {k: text(obj(env).get(k), 256) for k in (
                'image', 'image_id', 'tree_sha256', 'recipe_sha256', 'runtime_row')}
                for name, env in list(obj(run.get('environments')).items())[:4] if name in ('vulnerable', 'fixed')}},
        'finding_detail': {key: text(finding.get(key), 2000 if key == 'description' else 300)
                           for key in ('title', 'description', 'file_path', 'symbol', 'cwe')}
        | {'start_line': count(finding.get('start_line'))},
        'fix_reason': text(outcome.get('fix_reason') or summary.get('fix_reason'), 64),
        'probes': {revision: {role: probe(entry) for role, entry in obj(roles).items() if role in ('control', 'exploit')}
                   for revision, roles in obj(outcome.get('probes')).items() if revision in ('vulnerable', 'fixed')},
        'review': {'rounds': count(review.get('rounds')),
                   'authors': {role: {key: plain(entry.get(key), 1) for key in (
                       'first_review_valid', 'revisions_used', 'mechanical_fixes', 'final_valid', 'recovered')}
                       for role, entry in obj(review.get('authors')).items()
                       if role in ('control', 'exploit') and isinstance(entry, dict)}} if review else None,
        'attempts': [{'number': count(a.get('number')), 'patch_sha256': text(a.get('patch_sha256'), 64),
                      'exploit_outcome': text(a.get('exploit_outcome'), 64), 'review_rounds': count(a.get('review_rounds')),
                      'decided': flag(a.get('decided')),
                      'first_review_valid': named(a.get('first_review_valid'), flag)}
                     for a in summary.get('attempts', [])[:4] if isinstance(a, dict)]
        if isinstance(summary.get('attempts'), list) else [],
        'validity': validity(verdict.get('validity')),
        'agents': agent_totals(summary.get('agents')),
        'timings': [{'step': text(t.get('step'), 80), 'wall_s': number(t.get('wall_s')), 'error': flag(t.get('error'))}
                    for t in timings[:200] if isinstance(t, dict)],
        # usage.json without the error text (it can carry upstream detail); the status still names the failure kind
        'calls': None if usage is None else [
            {**{key: text(u.get(key), 120) for key in ('step', 'agent', 'model', 'provider_host', 'status',
                                                       'prompt_version', 'config_version', 'thinking')},
             **{key: number(u.get(key)) for key in ('temperature', 'max_tokens', 'thinking_budget', 'request_limit',
                                                    'tool_calls_limit', 'wall_s', 'requests', 'input_tokens',
                                                    'output_tokens', 'tool_calls', 'retries')}}
            for u in usage[:500] if isinstance(u, dict)],
    }


class Evidence:
    def __init__(self, root: Path, *, results: Path | None = None, runs: Path | None = None,
                 runtime_matrix: Path | None = None, assets: Path | None = None):
        # Explicit roots are operator configuration, never request parameters.
        self.root = root.resolve(strict=True)
        self.results_root, self.results_parts = (results.absolute(), ()) if results is not None \
            else (self.root, ('.runs', 'evals'))
        self.runs_root, self.runs_parts = (runs.absolute(), ()) if runs is not None \
            else (self.root, ('.runs', 'v2', 'runs'))
        self.assets_root, self.assets_parts = (assets.absolute(), ()) if assets is not None \
            else (self.root, ('ui', 'dist'))
        self.matrix = runtime_matrix.absolute() if runtime_matrix is not None \
            else self.root / 'deploy' / 'v2' / 'runtime-matrix.yaml'

    # --- sources ---

    def _require(self, root: Path, parts: tuple[str, ...], what: str, setting: str) -> None:
        try:
            with directory(root, parts) as fd:
                with os.scandir(fd) as found:  # enumeration, not merely traversal permission
                    next(found, None)
        except OSError as error:
            raise SourceUnavailable(f'{what} storage is unavailable. Check the mount, read permissions and '
                                    f'{setting}.') from error

    def require_results(self) -> None:
        self._require(self.results_root, self.results_parts, 'Evaluation', 'CORSAIR_UI_RESULTS')

    def require_runs(self) -> None:
        self._require(self.runs_root, self.runs_parts, 'Run record', 'CORSAIR_UI_RUNS')

    def static(self, parts: tuple[str, ...]) -> bytes:
        return read_file(self.assets_root, self.assets_parts + parts, MAX_STATIC)

    def sources(self) -> list[dict]:
        checks = (
            ('evaluations', self.require_results, 'Eval run storage is readable. Only saved records are shown.',
             'Check the eval results directory (CORSAIR_UI_RESULTS) and its read permissions; `make eval` writes '
             '.runs/evals by default.'),
            ('runs', self.require_runs, 'Run record storage is readable. Only saved records are shown.',
             'Check the run record directory (CORSAIR_UI_RUNS) and its read permissions; `corsair-v2 run` writes '
             '.runs/v2/runs by default.'),
            ('runtime', self.runtime, 'Runtime matrix is readable and valid. Registration is not current service health.',
             'Mount a valid v2 runtime matrix and check CORSAIR_UI_RUNTIME_MATRIX.'),
            ('assets', lambda: self.static(('index.html',)), 'Built UI assets are readable.',
             'Build the UI (make ui-build) and check CORSAIR_UI_ASSETS or the container image.'),
        )
        result = []
        for name, check, success, failure in checks:
            try:
                check()
                result.append({'id': name, 'status': 'available', 'detail': success})
            except (OSError, ValueError, RecursionError):
                result.append({'id': name, 'status': 'unavailable', 'detail': failure})
        return result

    # --- run records ---

    def runs(self) -> dict:
        self.require_runs()
        names, limited = entries(self.runs_root, self.runs_parts)
        warnings = ['Directory scan limit reached; some run records omitted.'] if limited else []
        if len(names) > MAX_RUNS:
            warnings.append(f'Showing the {MAX_RUNS} newest run records; older records omitted.')
        rows = []
        for name in names[:MAX_RUNS]:
            parts = self.runs_parts + (name,)
            try:
                run = optional_json(self.runs_root, parts + ('run.json',)) or {}
                summary = optional_json(self.runs_root, parts + ('summary.json',)) or {}
                if not run and not summary:
                    continue  # not a run record (no receipt at all)
                rows.append(run_row(run, summary, name))
            except (OSError, EvidenceError):
                warnings.append(f'{name}: record unavailable, malformed or unsafe; omitted.')
        return {'runs': rows, 'warnings': warnings}

    def run(self, name: str) -> dict:
        if not NAME.fullmatch(name):
            raise EvidenceError('Invalid run identifier')
        self.require_runs()
        return run_detail(self.runs_root, self.runs_parts + (name,)) | {'source': {'kind': 'run'}}

    def eval_attempt(self, agent: str, run: str, receipt: str) -> dict:
        """A chain eval attempt's own run record, kept by the eval under evidence/runs/<receipt>."""
        if agent != 'chain' or not NAME.fullmatch(run) or not NAME.fullmatch(receipt):
            raise EvidenceError('Invalid run identifier')
        self.require_results()
        parts = self.results_parts + (agent, run)
        summary = read_json(self.results_root, parts + ('summary.json',))
        row = next((r for r in summary.get('attempts') or [] if isinstance(r, dict) and r.get('receipt') == receipt), {})
        return run_detail(self.results_root, parts + ('evidence', 'runs', receipt)) | {'source': {
            'kind': 'eval', 'agent': agent, 'eval_run': run, 'receipt': receipt, 'case': text(row.get('case'), 200),
            # evaluator-only expectation, shown beside the verdict on the evaluator's own view
            'expected_label': text(row.get('expected_label'), 64), 'passed': flag(row.get('passed'))}}

    # --- eval runs ---

    def evaluations(self) -> dict:
        self.require_results()
        candidates, warnings = [], []
        for agent in AGENTS:
            try:
                names, limited = entries(self.results_root, self.results_parts + (agent,))
            except FileNotFoundError:
                continue
            except OSError:
                warnings.append(f'{agent}: eval directory could not be read safely.')
                continue
            if limited:
                warnings.append(f'{agent}: directory scan limit reached; some runs omitted.')
            candidates += [(name, agent) for name in names]
        candidates.sort(reverse=True)
        if len(candidates) > MAX_RUNS:
            warnings.append(f'Showing the {MAX_RUNS} newest eval runs; older runs omitted.')
        runs = []
        for run, agent in candidates[:MAX_RUNS]:
            parts = self.results_parts + (agent, run)
            try:
                summary = read_json(self.results_root, parts + ('summary.json',))
            except FileNotFoundError:
                warnings.append(f'{agent}/{run}: no summary yet (still running, or the run failed before writing one).')
                continue
            except (OSError, EvidenceError):
                warnings.append(f'{agent}/{run}: summary unavailable, malformed or unsafe; omitted.')
                continue
            try:
                record = eval_run(summary, agent, run)
                record['policy'] = self._policy_status(parts)
                record['command'] = command(optional_json(self.results_root, parts + ('command.json',)))
            except (OSError, EvidenceError):
                warnings.append(f'{agent}/{run}: not a readable v2 eval summary; omitted.')
                continue
            runs.append(record)
        return {'runs': runs, 'warnings': warnings}

    def _policy_status(self, parts: tuple[str, ...]) -> str | None:
        try:
            return text(obj(optional_json(self.results_root, parts + ('policy.json',))).get('status'), 32)
        except (OSError, EvidenceError):
            return None

    def evaluation(self, agent: str, run: str) -> dict:
        if agent not in AGENTS or not NAME.fullmatch(run):
            raise EvidenceError('Invalid run identifier')
        self.require_results()
        parts = self.results_parts + (agent, run)
        result = eval_run(read_json(self.results_root, parts + ('summary.json',)), agent, run, detail=True)
        result['command'] = command(optional_json(self.results_root, parts + ('command.json',)))
        try:
            result['policy'] = policy(optional_json(self.results_root, parts + ('policy.json',)))
        except (OSError, EvidenceError):
            result['policy'] = None
        if agent == 'chain':
            for row in result['attempts']:
                row['record'] = bool(row['receipt']) and is_dir(
                    self.results_root, parts + ('evidence', 'runs', row['receipt']))
        result['reference'] = self.reference(agent, result)
        return result

    def reference(self, agent: str, current: dict) -> dict | None:
        """What ``evals/run.py`` compares against: the promoted baseline, else the committed baseline, else the
        latest earlier whole-set run with the same set and mode."""
        base_set, mode = current['set'], current['mode']
        if not base_set or not mode or not NAME.fullmatch(f'{base_set}-{mode}'):
            return None
        agent_parts = self.results_parts + (agent,)
        candidates = []
        try:
            pointer = obj(optional_json(self.results_root, agent_parts + (f'baseline-{base_set}-{mode}.json',)))
            if isinstance(pointer.get('run'), str) and NAME.fullmatch(pointer['run']):
                candidates.append((pointer['run'], 'baseline'))
        except (OSError, EvidenceError):
            pass
        for run_id, kind in candidates:
            try:
                summary = read_json(self.results_root, agent_parts + (run_id, 'summary.json'))
                return self._reference(summary, agent, run_id, kind)
            except (OSError, EvidenceError):
                pass
        committed = self._committed(agent, base_set, mode)
        if committed is not None:
            return committed | {'kind': 'committed baseline'}
        try:
            index = read_file(self.results_root, agent_parts + ('index.jsonl',), MAX_JSON).decode()
        except (OSError, EvidenceError, UnicodeError):
            return None
        earlier = []
        for line in index.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if (isinstance(entry, dict) and entry.get('set') == base_set and entry.get('mode') == mode
                    and not entry.get('language') and isinstance(entry.get('run'), str)
                    and NAME.fullmatch(entry['run']) and entry['run'] < current['run']):
                earlier.append(entry['run'])
        for run_id in reversed(earlier):
            try:
                summary = read_json(self.results_root, agent_parts + (run_id, 'summary.json'))
                return self._reference(summary, agent, run_id, 'previous run')
            except (OSError, EvidenceError):
                continue
        return None

    def _reference(self, summary: dict, agent: str, run_id: str, kind: str) -> dict:
        projected = eval_run(summary, agent, run_id, detail=False)
        by_language = {k: rollup(v) for k, v in list(obj(obj(summary.get('rollups')).get('by_language')).items())[:20]
                       if isinstance(k, str) and KEY.fullmatch(k)}
        return {'run': run_id, 'kind': kind, 'language': projected['language'], 'identity': projected['identity'],
                'overall': projected['overall'], 'by_language': by_language}

    def _baseline_dir(self, agent: str) -> tuple[str, ...]:
        return ('evals', 'e2e', 'baselines') if agent == 'chain' else ('src', 'corsair', 'agents', agent, 'evals',
                                                                         'baselines')

    def _committed(self, agent: str, base_set: str, mode: str) -> dict | None:
        try:
            record = read_json(self.root, self._baseline_dir(agent) + (f'{base_set}-{mode}.json',))
            run_id = record.get('run')
            if not isinstance(run_id, str) or not NAME.fullmatch(run_id):
                return None
            return self._reference(record | {'agent': agent}, agent, run_id, 'committed baseline') | {
                'policy_status': text(record.get('policy_status'), 32), 'committed': text(record.get('committed'), 64)}
        except (OSError, EvidenceError):
            return None

    def baselines(self) -> dict:
        """Committed baselines (beside each agent's cases) and promoted pointers (under the results root)."""
        found = []
        for agent in AGENTS:
            try:
                names = entries_files(self.root, self._baseline_dir(agent), '.json')
            except OSError:
                names = []
            for name in names:
                base_set, _, mode = name.removesuffix('.json').rpartition('-')
                if (committed := self._committed(agent, base_set, mode)) is not None:
                    found.append({'agent': agent, 'set': base_set, 'mode': mode, 'source': 'committed',
                                  'run': committed['run'], 'policy_status': committed.get('policy_status'),
                                  'committed': committed.get('committed'), 'overall': committed['overall']})
            try:
                pointers = entries_files(self.results_root, self.results_parts + (agent,), '.json')
            except OSError:
                pointers = []
            for name in pointers:
                if not name.startswith('baseline-'):
                    continue
                base_set, _, mode = name.removeprefix('baseline-').removesuffix('.json').rpartition('-')
                try:
                    run_id = obj(read_json(self.results_root, self.results_parts + (agent, name))).get('run')
                except (OSError, EvidenceError):
                    continue
                if isinstance(run_id, str) and NAME.fullmatch(run_id):
                    found.append({'agent': agent, 'set': base_set, 'mode': mode, 'source': 'promoted', 'run': run_id})
        return {'baselines': found}

    # --- runtime matrix ---

    def runtime(self) -> dict:
        import yaml
        from corsair.matrix import Matrix
        try:
            # Kubernetes ConfigMap files are atomic symlinks. Only this explicitly operator-selected file may
            # resolve them; run and static paths still refuse links.
            selected = self.matrix.resolve(strict=True)
            raw = read_file(selected.parent, (selected.name,), MAX_JSON)
            matrix = Matrix.model_validate(yaml.safe_load(raw))
        except (ValueError, yaml.YAMLError) as error:
            raise EvidenceError('Runtime matrix is invalid') from error
        return {'schema': matrix.schema_version, 'sha256': hashlib.sha256(raw).hexdigest(),
                'rows': [row.model_dump(mode='json', exclude={'canary_setup'}) for row in matrix.rows],
                'limitations': ['canary-only rows are skipped by Select until their canaries classify on the image.',
                                'image-only rows are proven under plain Docker; only live rows passed the '
                                'kind/OpenShell gate.',
                                'Registration is not current image or service availability.']}


def entries_files(root: Path, parts: tuple[str, ...], suffix: str) -> list[str]:
    with directory(root, parts) as fd, os.scandir(fd) as found:
        names, _ = newest(entry.name for entry in found
                          if entry.name.endswith(suffix) and NAME.fullmatch(entry.name)
                          and entry.is_file(follow_symlinks=False))
    return sorted(names)


SECURITY_HEADERS = (
    ('Cache-Control', 'no-store'),
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'no-referrer'),
    ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"),
    ('Cross-Origin-Resource-Policy', 'same-origin'),
)
SPA = ('/', '/runs', '/evaluations', '/agents', '/runtime', '/system')


def validate_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
            or any(c.isspace() for c in value) or ',' in value):
        raise ValueError('Public origin must be an http(s) origin without credentials, path or query')
    try:
        parsed.port
    except ValueError as error:
        raise ValueError('Public origin has an invalid port') from error
    return value


def spa_path(parts: tuple[str, ...]) -> bool:
    if len(parts) == 2 and parts[0] == 'runs':
        return bool(NAME.fullmatch(parts[1]))
    if len(parts) >= 3 and parts[0] == 'evaluations' and parts[1] in AGENTS and NAME.fullmatch(parts[2]):
        return len(parts) == 3 or (len(parts) == 5 and parts[1] == 'chain' and parts[3] == 'attempts'
                                   and bool(NAME.fullmatch(parts[4])))
    return False


class Application:
    def __init__(self, evidence: Evidence, origins: tuple[str, ...]):
        self.evidence = evidence
        self.origins = tuple(validate_origin(origin) for origin in origins)

    def allowed(self, headers):
        hosts = headers.get_all('Host', [])
        origins = headers.get_all('Origin', [])
        return (len(hosts) == 1 and
                any(hosts[0] == urlsplit(origin).netloc and
                    (not origins or origins == [origin]) for origin in self.origins) and
                headers.get('Sec-Fetch-Site') != 'cross-site')

    def response(self, method, target, headers):
        def json_response(value, status=200):
            return status, json.dumps(value, allow_nan=False).encode(), 'application/json'

        def error(status, message):
            return json_response({'error': message}, status)

        if not self.allowed(headers):
            return error(403, 'Use the configured UI origin; unexpected Host or Origin was refused')
        if method not in ('GET', 'HEAD'):
            return error(405, 'This viewer is read-only')
        try:
            url = urlsplit(target)
            path = unquote(url.path, errors='strict')
            if (url.scheme or url.netloc or url.fragment or '\\' in path or '\x00' in path
                    or (url.query and path.startswith('/api/'))):
                return error(400, 'Invalid request path')
            parts = tuple(path.strip('/').split('/'))
            if any(p in ('.', '..') for p in parts):
                return error(400, 'Invalid request path')
            evidence = self.evidence
            if path in ('/api/health', '/api/live'):
                return json_response({'service': 'corsair-ui', 'read_only': True})
            if path in ('/api/ready', '/api/status'):
                sources = evidence.sources()
                # Ready needs the assets and at least one record source; the other may simply not exist yet.
                by_id = {source['id']: source['status'] == 'available' for source in sources}
                ready = by_id['assets'] and by_id['runtime'] and (by_id['evaluations'] or by_id['runs'])
                result = {'sources': sources, 'ready': ready, 'checked_at': datetime.now(timezone.utc).isoformat()}
                if path == '/api/status':
                    from corsair.web.services import service_status
                    result['services'] = service_status()
                    return json_response(result)
                return json_response(result, 200 if ready else 503)
            if path == '/api/workflows':
                from corsair.web.services import workflow_runs
                return json_response(workflow_runs())
            if path == '/api/runs':
                return json_response(evidence.runs())
            if len(parts) == 3 and parts[:2] == ('api', 'runs'):
                return json_response(evidence.run(parts[2]))
            if path == '/api/evaluations':
                return json_response(evidence.evaluations())
            if path == '/api/baselines':
                return json_response(evidence.baselines())
            if len(parts) == 4 and parts[:2] == ('api', 'evaluations'):
                return json_response(evidence.evaluation(parts[2], parts[3]))
            if len(parts) == 6 and parts[:2] == ('api', 'evaluations') and parts[4] == 'attempts':
                return json_response(evidence.eval_attempt(parts[2], parts[3], parts[5]))
            if path == '/api/runtime':
                try:
                    return json_response(evidence.runtime())
                except (OSError, ValueError):
                    return error(503, 'Runtime matrix unavailable or invalid. Check CORSAIR_UI_RUNTIME_MATRIX.')
            if path.startswith('/api/'):
                return error(404, 'Unknown endpoint')
            static_parts = ('index.html',) if path in SPA or spa_path(parts) else parts
            suffix = Path(static_parts[-1]).suffix
            if suffix not in MIME:
                return error(404, 'Static asset not found')
            return 200, evidence.static(static_parts), MIME[suffix]
        except SourceUnavailable as issue:
            return error(503, str(issue))
        except FileNotFoundError:
            return error(404, 'Record or UI asset not found. Check the selected run or rebuild the UI.')
        except (OSError, EvidenceError, UnicodeError, ValueError, RecursionError):
            return error(422, 'Evidence could not be read safely; check the record, permissions and size limits')

    def __call__(self, environ, start_response):
        headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                headers[key[5:].replace('_', '-')] = value
        # Gunicorn preserves the raw target; decoding PATH_INFO again would permit inconsistent double-decoding
        # between the local and production adapters.
        target = environ.get('RAW_URI') or environ.get('PATH_INFO', '/')
        if 'RAW_URI' not in environ and environ.get('QUERY_STRING'):
            target += '?' + environ['QUERY_STRING']
        status, data, content_type = self.response(environ['REQUEST_METHOD'], target, headers)
        start_response(f'{status} {HTTPStatus(status).phrase}',
                       [('Content-Type', content_type), ('Content-Length', str(len(data))), *SECURITY_HEADERS])
        return [b'' if environ['REQUEST_METHOD'] == 'HEAD' else data]


class Server(ThreadingHTTPServer):
    """Development-only HTTP adapter; containers use Gunicorn and the same Application."""
    daemon_threads = True

    def __init__(self, root: Path, port: int = 8765, **sources):
        self.evidence = Evidence(root, **sources)
        super().__init__(('127.0.0.1', port), Handler)
        self.application = Application(self.evidence, (f'http://127.0.0.1:{self.server_port}',
                                                      f'http://localhost:{self.server_port}'))


class Handler(BaseHTTPRequestHandler):
    server_version = 'Corsair'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def do_GET(self):
        status, data, content_type = self.server.application.response(self.command, self.path, self.headers)
        try:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            for key, value in SECURITY_HEADERS:
                self.send_header(key, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    do_HEAD = do_GET
    do_POST = do_GET
    do_PUT = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET
    do_OPTIONS = do_GET


SETTINGS = (('results', 'CORSAIR_UI_RESULTS'), ('runs', 'CORSAIR_UI_RUNS'), ('assets', 'CORSAIR_UI_ASSETS'),
            ('runtime_matrix', 'CORSAIR_UI_RUNTIME_MATRIX'))


def configured_evidence() -> Evidence:
    return Evidence(Path.cwd(), **{key: Path(os.environ[env]) for key, env in SETTINGS if os.environ.get(env)})


def main():
    parser = argparse.ArgumentParser(description='Local read-only viewer of v2 run records and eval runs')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='Checkout root (default sources under it)')
    for key, env in SETTINGS:
        parser.add_argument('--' + key.replace('_', '-'), type=Path, default=os.environ.get(env) or None,
                            help=f'Default: {env} or the checkout default')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with Server(args.root, args.port, **{key: getattr(args, key) for key, _ in SETTINGS}) as server:
        print(f'Corsair read-only viewer: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
