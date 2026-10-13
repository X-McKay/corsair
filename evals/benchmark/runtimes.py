"""SPEC-0042 runtime report over the benchmark cases: which resolve to a qualified image, which need a new one, which
are undetermined. Offline over captured build files, except the two explicit fetch subcommands.

    checkout  fetch only the build files of each pinned commit (blobless git, never executed) into a tree root
    parents   fetch the Maven parent POMs the trees name from Maven Central into a cache directory
    report    detect and select for every inventory case and every in-repository corpus case (SPEC-0067); markdown on
              stdout, JSON with --json. Held-out corpus cases are counted, never named.

Trees are laid out as `<root>/<case dir>/<commit>/<path>`; `<case dir>` is the case id with '/' replaced by '_'.
The pins file (`benchmarks/source-pins.json`, SPEC-0037) names each case's fix commit and baseline candidate.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import get_args
import urllib.request

from corsair.nodes.runtime.contracts import Language, RuntimeRequirement
from corsair.nodes.runtime.detect import detect, is_build_file
from corsair.nodes.runtime.java import Pom
from corsair.nodes.runtime.matrix import MATRIX, load, select
from corsair.nodes.runtime.versions import parse_set, parse_version
from evals.corpus import cases as corpus

REPOSITORY = Path(__file__).resolve().parents[2]
INVENTORY = REPOSITORY / 'benchmarks/candidate-cases.json'
PINS = REPOSITORY / 'benchmarks/source-pins.json'
# Operator-owned parent POM sources, tried in order; a project's own <repositories> are never followed.
REPOSITORIES = ('https://repo.maven.apache.org/maven2', 'https://repo.jenkins-ci.org/public')
MAX_POM_BYTES = 1 << 20
MAX_PARENTS = 128
COORDINATE = re.compile(r'(?!\.+$)[A-Za-z0-9_.-]{1,128}')  # untrusted POM coordinates become URL and file names


def case_dir(case_id: str) -> str:
    return case_id.replace('/', '_')


def revisions(pins: dict) -> list[tuple[str, str, str, str]]:
    """(case id, url, role, commit) for every acquired case: the baseline candidate and the fix."""
    rows = []
    for case_id, pin in pins['cases'].items():
        if pin.get('outcome') != 'acquired': continue
        if pin.get('baseline_candidate'): rows.append((case_id, pin['url'], 'baseline', pin['baseline_candidate']))
        rows.append((case_id, pin['url'], 'fix', pin['commit']))
    return rows


def _git(*args: str, cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never', *args], cwd=cwd,
                          capture_output=True, timeout=timeout, check=True)


def checkout(pins: dict, root: Path, cases: set[str] | None) -> None:
    """Shallow blobless fetch of each commit, then fetch and write only the blobs `is_build_file` selects."""
    root.mkdir(parents=True, exist_ok=True)
    for case_id, url, role, commit in revisions(pins):
        if cases and case_id not in cases: continue
        target = root / case_dir(case_id) / commit
        if target.exists(): continue
        repo = root / '.git-cache' / case_dir(case_id)
        try:
            if not repo.exists():
                repo.mkdir(parents=True)
                _git('init', '-q', '--bare', cwd=repo)
                _git('remote', 'add', 'origin', url, cwd=repo)
                _git('config', 'remote.origin.promisor', 'true', cwd=repo)
                _git('config', 'remote.origin.partialclonefilter', 'blob:none', cwd=repo)
            _git('fetch', '-q', '--filter=blob:none', '--depth=1', 'origin', commit, cwd=repo)
            listing = _git('ls-tree', '-r', '-z', '--full-tree', commit, cwd=repo).stdout.split(b'\0')
            wanted = []
            for entry in filter(None, listing):
                meta, path = entry.split(b'\t', 1)
                mode, kind, oid = meta.split()
                path = path.decode('utf-8', 'surrogateescape')
                if kind == b'blob' and mode in (b'100644', b'100755') and is_build_file(path): wanted.append((path, oid.decode()))
            for start in range(0, len(wanted), 256):
                _git('fetch', '-q', '--filter=blob:none', 'origin', *[oid for _, oid in wanted[start:start + 256]], cwd=repo)
            partial = target.with_name(target.name + '.partial')  # renamed only once every blob is written
            shutil.rmtree(partial, ignore_errors=True)
            partial.mkdir(parents=True)
            for path, oid in wanted:
                relative = PurePosixPath(path)
                if relative.is_absolute() or '..' in relative.parts: continue
                destination = partial / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(_git('cat-file', 'blob', oid, cwd=repo).stdout)
            partial.rename(target)
            print(f'{case_id} {role} {commit[:12]} {len(wanted)} build files', file=sys.stderr)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            detail = getattr(error, 'stderr', b'') or b''
            print(f'{case_id} {role} {commit[:12]} not fetched: {detail.decode(errors="replace").strip()[:200]}', file=sys.stderr)


def read_tree(directory: Path) -> dict[str, bytes]:
    return {str(p.relative_to(directory)): p.read_bytes() for p in sorted(directory.rglob('*'))
            if p.is_file() and is_build_file(str(p.relative_to(directory)))}


def load_parents(cache: Path | None) -> dict[str, bytes]:
    return {p.stem: p.read_bytes() for p in sorted(cache.glob('*.pom'))} if cache and cache.exists() else {}


def fetch_parents(root: Path, cache: Path) -> None:
    """Fetch every parent POM the trees' root POMs name, recursively, from Maven Central (bounded)."""
    cache.mkdir(parents=True, exist_ok=True)
    pending = []
    for pom_path in sorted(root.glob('*/*/pom.xml')):
        try: pending.append(Pom(str(pom_path), pom_path.read_bytes()).parent)
        except Exception: continue
    cached, seen = load_parents(cache), set()
    while pending and len(seen) < MAX_PARENTS:
        gav = pending.pop()
        if not gav or not all(COORDINATE.fullmatch(part) for part in gav) or ':'.join(gav) in seen: continue
        key = ':'.join(gav)
        seen.add(key)
        if key in cached:
            try: pending.append(Pom(key, cached[key]).parent)
            except Exception: pass
            continue
        data, errors = None, []
        for repository in REPOSITORIES:
            url = f'{repository}/{gav[0].replace(".", "/")}/{gav[1]}/{gav[2]}/{gav[1]}-{gav[2]}.pom'
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read(MAX_POM_BYTES + 1)
                break
            except OSError as error:
                errors.append(f'{repository}: {error}')
        if data is None:
            print(f'{key} not fetched: {"; ".join(errors)}', file=sys.stderr)
            continue
        if len(data) > MAX_POM_BYTES: print(f'{key} over {MAX_POM_BYTES} bytes', file=sys.stderr); continue
        (cache / f'{key}.pom').write_bytes(data)
        try: pending.append(Pom(key, data).parent)
        except Exception as error: print(f'{key} refused: {error}', file=sys.stderr)


def evaluate(root: Path, pins: dict, inventory: list[dict], parents: dict[str, bytes]) -> list[dict]:
    matrix = load()
    pinned = {case_id: pin for case_id, pin in pins['cases'].items() if pin.get('outcome') == 'acquired'}
    results = []
    for row in inventory:
        case_id, language = row['case_id'], row['language'].lower()
        record = dict(case_id=case_id, language=language)
        pin = pinned.get(case_id)
        if pin is None:
            results.append({**record, 'status': 'not_acquired', 'detail': 'no pinned commit (SPEC-0037)'}); continue
        record['revisions'] = {}
        for role, commit in (('baseline', pin.get('baseline_candidate')), ('fix', pin['commit'])):
            if not commit: continue
            directory = root / case_dir(case_id) / commit
            if not directory.is_dir():
                record['revisions'][role] = dict(commit=commit, status='not_fetched'); continue
            requirement = detect(read_tree(directory), language, parents=parents)
            if isinstance(requirement, str):
                record['revisions'][role] = dict(commit=commit, status='undetermined', missing=[requirement]); continue
            selection = select(requirement, matrix)
            record['revisions'][role] = dict(commit=commit, requirement=requirement.model_dump(mode='json'),
                                             **selection.model_dump(mode='json'))
        decisive = record['revisions'].get('baseline') or record['revisions'].get('fix') or {}
        record['status'] = decisive.get('status', 'not_fetched')
        statuses = {r.get('status') for r in record['revisions'].values()}
        record['revisions_agree'] = len(statuses) == 1
        results.append(record)
    return results


def _select(files: dict[str, bytes], language: str, matrix, parents: dict[str, bytes] | None = None) -> dict:
    if language not in get_args(Language):
        return dict(status='undetermined', missing=[f'no {language} detector or matrix row (SPEC-0042 reads {", ".join(get_args(Language))})'])
    requirement = detect(files, language, parents=parents)
    if isinstance(requirement, str): return dict(status='undetermined', missing=[requirement])
    return dict(requirement=requirement.model_dump(mode='json'), **select(requirement, matrix).model_dump(mode='json'))


def evaluate_corpus(cases=None) -> list[dict]:
    """Both variants of every corpus case, read from the in-repository copy; nothing is fetched or run."""
    matrix = load()
    results = []
    for case in cases if cases is not None else corpus.load():
        record = dict(case_id=case.case_id, language=case.language, split=case.split, revisions={})
        for role, entry in (('baseline', case.baseline), ('candidate', case.candidate)):
            if entry is None: continue
            tree = {path: data for path, data in corpus.snapshot(corpus.CORPUS / str(entry.variant)).items() if is_build_file(path)}
            record['revisions'][role] = _select(tree, case.language, matrix)
        record['status'] = record['revisions']['baseline']['status']
        record['revisions_agree'] = len({r['status'] for r in record['revisions'].values()}) == 1
        results.append(record)
    return results


def _requirement(record: dict) -> RuntimeRequirement | None:
    revision = record.get('revisions', {}).get('baseline') or record.get('revisions', {}).get('fix') or {}
    return RuntimeRequirement.model_validate(revision['requirement']) if 'requirement' in revision else None


def recommend(results: list[dict]) -> list[tuple[str, str, list[str]]]:
    """Greedy runtime rows: for unsupported cases, the series (named by some case's tested or pinned versions) that
    satisfies the most remaining cases' runtime constraint, per language, until none is left uncovered."""
    rows = []
    for language in sorted({r['language'] for r in results}):
        remaining = {}
        for record in results:
            if record['language'] != language or record['status'] != 'unsupported': continue
            requirement = _requirement(record)
            runtime = next((c for c in requirement.component('runtime') if c.declared), None) if requirement else None
            if runtime: remaining[record['case_id']] = runtime
        while remaining:
            candidates = Counter()
            for runtime in remaining.values():
                for evidence in runtime.evidence:
                    if evidence.strength in ('tested', 'pinned') and evidence.declares.endswith('.*'):
                        candidates[(runtime.name, evidence.declares[:-2])] += 0
            for name, series in list(candidates):
                version = parse_version(series)
                candidates[(name, series)] = sum(parse_set(r.allowed).contains(version) for r in remaining.values() if r.name == name)
            if not candidates or max(candidates.values()) == 0:
                rows += [(language, f'{r.name} {r.preferred or r.allowed}', [case]) for case, r in remaining.items()]
                break
            (name, series), _ = max(candidates.items(), key=lambda item: (item[1], parse_version(item[0][1])))
            covered = [case for case, r in remaining.items() if r.name == name and parse_set(r.allowed).contains(parse_version(series))]
            rows.append((language, f'{name} {series}', covered))
            for case in covered: remaining.pop(case)
    return rows


def _outcome(record: dict) -> str:
    """A supported case counts as qualified only on live rows; image-only selections are counted apart, and a runtime
    inferred from framework metadata (SPEC-0069) is named as such, never shown as declared."""
    if record['status'] != 'supported': return record['status']
    # The weakest evidence across every evaluated revision: one image-only commit makes the case image-only.
    revisions = [r for r in record.get('revisions', {}).values() if r.get('status') == 'supported']
    levels = [r.get('evidence', 'evidence unrecorded') for r in revisions]
    notes = [next((level for level in ('evidence unrecorded', 'image-only') if not levels or level in levels), None)]
    if not levels: notes = ['evidence unrecorded']
    if any(r.get('runtime_basis') == 'inferred' for r in revisions): notes.append('runtime inferred')
    notes = [n for n in notes if n]
    return 'supported' + (f' ({", ".join(notes)})' if notes else '')


def _row(record: dict, differs: str = 'fix') -> str:
    revision = record.get('revisions', {}).get('baseline') or record.get('revisions', {}).get('fix') or {}
    requirement = _requirement(record)
    runtime = next((c for c in requirement.component('runtime')), None) if requirement else None
    allowed = (runtime.allowed if runtime and runtime.declared else 'undeclared') if requirement else ''
    if revision.get('status') == 'supported': detail = revision['image_id']
    elif revision.get('status') == 'unsupported':
        detail = '; '.join(f"{n['name']} {n['preferred'] or n['allowed']}" for n in revision['needs'])
    else: detail = '; '.join(revision.get('missing', [record.get('detail', '')]))
    agree = '' if record.get('revisions_agree', True) else f' ({differs} differs)'
    return f"| {record['case_id']} | {record['language']} | {_outcome(record)}{agree} | {allowed.replace('|', '/')} | {detail.replace('|', '/')[:300]} |"


def corpus_markdown(results: list[dict]) -> str:
    """Development corpus cases by name; held-out ones only as counts per language and outcome."""
    lines = ['| Case | Language | Outcome | Runtime allowed | Unmet or missing |', '| --- | --- | --- | --- | --- |']
    lines += [_row(r, 'candidate') for r in results if r['split'] == 'development']
    held_out = Counter((r['language'], _outcome(r)) for r in results if r['split'] == 'held_out')
    counts = Counter(_outcome(r) for r in results)
    lines += ['', 'Outcomes (all corpus cases): ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())),
              'Held-out cases, not named: ' + ', '.join(f'{language} {status} {n}' for (language, status), n in sorted(held_out.items()))]
    return '\n'.join(lines) + '\n'


def public(results: list[dict]) -> dict:
    """Development corpus results by case; held-out ones only as counts, so their order cannot name them."""
    held_out = Counter(f"{r['language']} {_outcome(r)}" for r in results if r['split'] == 'held_out')
    return dict(development=[r for r in results if r['split'] == 'development'], held_out=dict(sorted(held_out.items())))


def markdown(results: list[dict]) -> str:
    lines = ['| Case | Language | Outcome | Runtime allowed | Unmet or missing |', '| --- | --- | --- | --- | --- |']
    lines += [_row(record) for record in results]
    counts = Counter(_outcome(r) for r in results)
    lines += ['', 'Outcomes: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())), '',
              '| Language | Suggested runtime row | Cases whose runtime it satisfies |', '| --- | --- | --- |']
    lines += [f'| {language} | {row} | {len(cases)}: {", ".join(cases)} |' for language, row, cases in recommend(results)]
    frameworks = Counter(f"{n['name']} {n['allowed']}" for r in results
                         for n in ((r.get('revisions', {}).get('baseline') or r.get('revisions', {}).get('fix') or {}).get('needs') or [])
                         if n['kind'] == 'test_framework')
    lines += ['', '| Framework range needed | Cases |', '| --- | --- |'] + [f'| {k.replace("|", "/")} | {v} |' for k, v in sorted(frameworks.items())]
    return '\n'.join(lines) + '\n'


def _digest(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def inputs(pins: Path, parents: Path | None) -> dict:
    """What the report was computed from, so a rerun can be compared: detector source, matrix, pins, inventory and
    the parent POMs (by coordinate) that were supplied. The fetched trees are identified by the pinned commits."""
    detector = b''.join(f.name.encode() + b'\0' + f.read_bytes() for f in sorted((REPOSITORY / 'src/corsair/nodes/runtime').glob('*.py')))
    return dict(detector=_digest(detector), matrix=_digest(MATRIX.read_bytes()), pins=_digest(pins.read_bytes()),
                inventory=_digest(INVENTORY.read_bytes()), corpus='sha256:' + corpus.tree_digest(),
                parents={key: _digest(data) for key, data in sorted(load_parents(parents).items())})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['checkout', 'parents', 'report'])
    parser.add_argument('--trees', type=Path, required=True)
    parser.add_argument('--pins', type=Path, default=PINS)
    parser.add_argument('--parents', type=Path, help='Directory of `group:artifact:version.pom` parent POMs')
    parser.add_argument('--cases', nargs='*')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    pins = json.loads(args.pins.read_text())
    if args.action == 'checkout': return checkout(pins, args.trees, set(args.cases or []))
    if args.action == 'parents': return fetch_parents(args.trees, args.parents)
    inventory = json.loads(INVENTORY.read_text())['cases']
    results = evaluate(args.trees, pins, inventory, load_parents(args.parents))
    corpus_results = evaluate_corpus()
    if args.json:
        document = dict(schema_version=1, spec='SPEC-0042', inputs=inputs(args.pins, args.parents), results=results,
                        corpus=public(corpus_results))
        args.json.write_text(json.dumps(document, indent=1) + '\n')
    sys.stdout.write(markdown(results) + '\n## Corpus cases (SPEC-0067)\n\n' + corpus_markdown(corpus_results))


if __name__ == '__main__':
    main()
