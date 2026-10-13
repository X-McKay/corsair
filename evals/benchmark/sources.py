"""IDEA-0005 step 2 (G2c): resolve each inventory case's fix commit and acquire it on the host under SPEC-0037.

`resolve` is offline and covers all inventory rows: a case either names one repository URL and exact fix commit, or
is reported unresolved with the reason. `fetch` acquires resolved cases into a new private run directory, then tries
the unchanged `GitSource` capture of the fix and its first parent at the largest admitted ceilings, and merges one
record per case into the committed pins file. The first parent is recorded as the baseline candidate only; whether it
is the vulnerable revision is a case-admission question (PLAN-0021), not something a fetch shows.

Reads `benchmarks/candidate-cases.json` directly rather than through the case loader proposed beside this file, so
the two land independently.
"""
import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil
import sys
import time
from uuid import uuid4

from corsair.adapters.git_acquire import AcquireLimits, AcquisitionError, GitAcquisition, HostTransport
from corsair.adapters.git_source import Executable, GitSource, SourceCaptureError, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.nodes.source_fetch import FetchTarget

REPOSITORY = Path(__file__).resolve().parents[2]
INVENTORY = REPOSITORY / 'benchmarks/candidate-cases.json'
PINS = REPOSITORY / 'benchmarks/source-pins.json'
HOSTS = frozenset({'github.com', 'salsa.debian.org'})
# Largest ceilings `SourceLimits` admits; a refusal here is the G2b/G3 size finding, not a fetch failure.
CAPTURE = SourceLimits(max_files=4096, max_file_bytes=16*1024*1024, max_total_bytes=64*1024*1024, wall_seconds=60,
                       cpu_seconds=30)

COMMIT_URL = re.compile(r'https://(?P<host>[a-z0-9.-]+)/(?P<path>[A-Za-z0-9._~/-]+?)/(?:-/)?commit/'
                        r'(?P<commit>[0-9a-f]{40})(?P<patch>\.patch)?')
PULL_URL = re.compile(r'https://github\.com/(?P<path>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/pull/(?P<number>[0-9]+)'
                      r'/commits/(?P<commit>[0-9a-f]{40})')


@dataclass(frozen=True)
class SourceRequest:
    case_id: str
    target: FetchTarget
    via: str  # commit, patch or pull_request: the form of the inventory's fix reference
    repository_matches_inventory: bool


@dataclass(frozen=True)
class Unresolved:
    case_id: str
    reason: str


def _same(a: str | None, b: str | None) -> bool:
    norm = lambda url: url.rstrip('/').removesuffix('.git').casefold() if url else None
    return norm(a) == norm(b)


def resolve(row: dict) -> SourceRequest | Unresolved:
    reference, repository = row.get('fixed_reference'), row.get('repository_url')
    if not reference:
        return Unresolved(row['case_id'], 'no fix reference' + ('' if repository else ' and no repository'))
    if match := PULL_URL.fullmatch(reference):
        url, via = f'https://github.com/{match["path"]}', 'pull_request'
    elif match := COMMIT_URL.fullmatch(reference):
        url, via = f'https://{match["host"]}/{match["path"]}', 'patch' if match['patch'] else 'commit'
    else:
        return Unresolved(row['case_id'], 'fix reference is not a commit URL')
    return SourceRequest(row['case_id'], FetchTarget(url, match['commit']), via, _same(url, repository))


def load_rows(path: Path = INVENTORY) -> list[dict]:
    rows = json.loads(path.read_text())['cases']
    if len({row['case_id'] for row in rows}) != len(rows): raise ValueError('duplicate inventory case id')
    return rows


def _pin(path: str) -> Executable:
    import hashlib
    with open(path, 'rb') as stream: return Executable(Path(path), hashlib.file_digest(stream, 'sha256').hexdigest())


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def case_dir(run: Path, case_id: str) -> Path:
    return run/case_id.replace('/', '_')


def _capture(repo: str, commit: str, directory: Path) -> dict:
    with LocalArtifacts(_private(directory/f'objects-{commit}'), max_bytes=CAPTURE.max_file_bytes) as store, \
            GitSource(_pin('/usr/bin/git'), _pin('/usr/bin/prlimit'), store=store, limits=CAPTURE,
                      receipts=_private(directory/f'capture-{commit}')) as source:
        try:
            snapshot = source.capture(Path(repo), commit, uuid4())
            return dict(outcome='completed', files=len(snapshot.files), manifest=asdict(snapshot.manifest))
        except SourceCaptureError as error:
            return dict(outcome='refused', layer=error.receipt.get('layer'), detail=str(error))


def fetch(requests: list[SourceRequest], run: Path, transport: HostTransport, limits: AcquireLimits,
          capture: bool) -> dict[str, dict]:
    run.mkdir(mode=0o700, parents=False)
    records = {}
    with GitAcquisition(_pin('/usr/bin/git'), _pin('/usr/bin/prlimit'), transport=transport, limits=limits,
                        receipts=_private(run/'receipts')) as acquisition:
        for request in requests:
            started = time.monotonic()
            record = dict(case_id=request.case_id, url=request.target.url, commit=request.target.commit,
                          via=request.via, repository_matches_inventory=request.repository_matches_inventory,
                          depth=limits.depth, fsck_warn=sorted(limits.fsck_warn))
            directory = _private(case_dir(run, request.case_id))
            try:
                source = acquisition.acquire(request.target, directory/'repo', uuid4())
            except AcquisitionError as error:
                calls = error.receipt.get('native_calls') or [{}]
                record.update(outcome='refused', layer=error.layer, detail=str(error)[:600],
                              stderr=calls[-1].get('stderr', '')[-600:],
                              elapsed_seconds=round(time.monotonic()-started, 3))
                records[request.case_id] = record
                print(f'{request.case_id}: refused {error.layer}', file=sys.stderr)
                continue
            result = asdict(source)
            result.pop('repository'); result.pop('url'); result.pop('commit')
            result['elapsed_seconds'] = round(result['elapsed_seconds'], 3)
            single = source.first_parent if len(source.parents) == 1 else None
            record.update(outcome='acquired', **result,
                          baseline_candidate=single.commit if single else None)
            if capture and not source.shallow:
                record['capture'] = {'commit': _capture(source.repository, source.commit, directory)}
                if single: record['capture']['first_parent'] = _capture(source.repository, single.commit, directory)
            records[request.case_id] = record
            print(f'{request.case_id}: acquired {source.repository_bytes} bytes, {source.tree.regular_files} files',
                  file=sys.stderr)
    return records


def write_pins(records: dict[str, dict], unresolved: list[Unresolved], path: Path = PINS) -> None:
    existing = json.loads(path.read_text())['cases'] if path.exists() else {}
    existing.update(records)
    order = [row['case_id'] for row in load_rows()]
    document = dict(schema_version=1, spec='SPEC-0037',
                    note='Host acquisition of each case\'s fix commit; first parent is a baseline candidate only.',
                    cases={case: existing[case] for case in order if case in existing},
                    unresolved={item.case_id: item.reason for item in unresolved})
    path.write_text(json.dumps(document, indent=1, sort_keys=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('resolve', help='Offline: list resolved and unresolved cases')
    run = sub.add_parser('fetch', help='Acquire resolved cases over the network into a new run directory')
    run.add_argument('--run-dir', type=Path, required=True, help='New private directory, normally under .runs/')
    run.add_argument('--cases', nargs='*', help='Case ids (default: every resolved case)')
    run.add_argument('--depth', type=int, help='Shallow, measure-only fetch; GitSource capture is skipped')
    run.add_argument('--proxy', help='Explicit operator HTTPS proxy, scheme://host:port')
    run.add_argument('--ca-bundle', type=Path, help='Explicit operator CA bundle for the proxy')
    run.add_argument('--no-capture', action='store_true')
    run.add_argument('--fsck-warn', nargs='*', default=[], help='Format-only fsck message ids to record, not refuse')
    run.add_argument('--keep', action='store_true', help='Keep fetched repositories (default: delete after recording)')
    run.add_argument('--pins', type=Path, default=PINS)
    args = parser.parse_args()
    rows = load_rows()
    resolved = [item for item in map(resolve, rows) if isinstance(item, SourceRequest)]
    unresolved = [item for item in map(resolve, rows) if isinstance(item, Unresolved)]
    if args.command == 'resolve':
        for item in resolved:
            print(f'{item.case_id}\t{item.via}\t{item.target.url}\t{item.target.commit}'
                  + ('' if item.repository_matches_inventory else '\trepository differs from inventory'))
        for item in unresolved: print(f'{item.case_id}\tunresolved\t{item.reason}')
        print(f'resolved {len(resolved)}, unresolved {len(unresolved)}', file=sys.stderr)
        return
    selected = [item for item in resolved if not args.cases or item.case_id in args.cases]
    if args.cases and len(selected) != len(set(args.cases)): parser.error('unknown or unresolved case id')
    transport = HostTransport(HOSTS, args.proxy, args.ca_bundle.resolve() if args.ca_bundle else None)
    limits = AcquireLimits(depth=args.depth, fsck_warn=frozenset(args.fsck_warn))
    records = fetch(selected, args.run_dir.resolve(), transport, limits, not args.no_capture)
    write_pins(records, unresolved, args.pins)
    if not args.keep:  # receipts stay; repositories and captured objects are reproducible from the pins
        for case in records:
            for path in case_dir(args.run_dir.resolve(), case).glob('[ro]*'):
                if path.name == 'repo' or path.name.startswith('objects-'): shutil.rmtree(path)
    print(json.dumps({outcome: sum(r['outcome'] == outcome for r in records.values())
                      for outcome in ('acquired', 'refused')}), file=sys.stderr)


if __name__ == '__main__':
    main()
