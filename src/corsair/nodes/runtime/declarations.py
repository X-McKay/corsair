"""Shared declaration plumbing for SPEC-0042 detectors: one record per declaring line, combined per component.

Combination rule (SPEC-0042): constraints intersect; pins, when present, decide the series; otherwise the
highest-ranked tested source present (CI, then tox/nox, then classifiers, then a derived level) gives the
versions the project actually exercises. A runtime the project neither pins nor tests stays at its
constraints. An empty result is a conflict, never a fallback.
"""
from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping

import yaml

from corsair.nodes.runtime.contracts import Component, Evidence, Kind, Provider, Strength, Unparsed
from corsair.nodes.runtime.versions import ANY, Version, VersionSet, render, version_key

TESTED_RANK = ('ci', 'tox', 'classifier', 'derived')
MAX_TEXT = 240


@dataclass(frozen=True)
class Declaration:
    kind: Kind
    name: str
    provider: Provider
    strength: Strength
    source: str
    path: str
    line: int
    text: str
    versions: VersionSet | None  # None: seen but not understood
    listed: Version | None = None  # an explicitly named version (pin or tested entry), used for `preferred`
    reason: str = ''


@dataclass
class Collector:
    files: Mapping[str, bytes]
    declarations: list[Declaration] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def text(self, path: str) -> str | None:
        data = self.files.get(path)
        if data is None: return None
        return data.decode('utf-8', errors='replace')

    def add(self, kind: Kind, name: str, provider: Provider, strength: Strength, source: str, path: str, needle: str,
            versions: VersionSet | None, listed: Version | None = None, reason: str = '', line: int | None = None):
        text = self.text(path) or ''
        line = line or line_of(text, needle)
        self.declarations.append(Declaration(kind, name, provider, strength, source, path, line, excerpt(text, line),
                                             versions, listed, reason))

    def unparsed(self, kind: Kind, name: str, provider: Provider, path: str, needle: str, reason: str, line: int | None = None,
                 strength: Strength = 'constraint'):
        self.add(kind, name, provider, strength, 'unparsed', path, needle, None, reason=reason, line=line)


def line_of(text: str, needle: str) -> int:
    """1-based line of the first occurrence of `needle`; 1 when absent (the whole file is the citation)."""
    index = text.find(needle) if needle else -1
    return text.count('\n', 0, index) + 1 if index >= 0 else 1


def excerpt(text: str, line: int) -> str:
    lines = text.splitlines()
    return (lines[line - 1].strip() if 0 < line <= len(lines) else '')[:MAX_TEXT]


def combine(declarations: Iterable[Declaration]) -> tuple[Component, ...]:
    grouped: dict[tuple[str, str], list[Declaration]] = {}
    for d in declarations: grouped.setdefault((d.kind, d.name), []).append(d)
    components = []
    for (kind, name), items in grouped.items():
        parsed = [d for d in items if d.versions is not None]
        constraint = ANY
        for d in parsed:
            if d.strength == 'constraint': constraint = constraint.intersect(d.versions)
        pins = [d for d in parsed if d.strength == 'pinned']
        chosen = pins
        if not pins:
            for source in TESTED_RANK:
                chosen = [d for d in parsed if d.strength == 'tested' and d.source == source]
                if chosen: break
        allowed = constraint
        if chosen:
            selected = ANY if pins else VersionSet(())
            for d in chosen: selected = selected.intersect(d.versions) if pins else selected.union(d.versions)
            allowed = constraint.intersect(selected)
        listed = sorted({d.listed for d in chosen if d.listed is not None and allowed.contains(d.listed)},
                        key=version_key)
        preferred = render(listed[-1]) if listed else (render(allowed.lowest) if allowed.lowest else None)
        used = {id(d) for d in parsed if d.strength == 'constraint'} | {id(d) for d in chosen}
        components.append(Component(
            kind=kind, name=name, provider=items[0].provider, allowed=str(allowed), preferred=preferred,
            declared=bool(parsed), conflict=allowed.is_empty,
            evidence=tuple(Evidence(path=d.path, line=d.line, text=d.text, strength=d.strength, source=d.source,
                                    declares=str(d.versions)[:MAX_TEXT]) for d in parsed if id(d) in used)[:64],
            unparsed=tuple(Unparsed(path=d.path, line=d.line, text=d.text, strength=d.strength, reason=d.reason[:MAX_TEXT])
                           for d in items if d.versions is None)[:64]))
    return tuple(components)


class _StringLoader(yaml.SafeLoader):
    """Safe YAML that keeps scalars as written, so `3.10` stays `3.10` rather than the float 3.1."""


for _tag in ('int', 'float', 'bool', 'null', 'timestamp'):
    _StringLoader.add_constructor(f'tag:yaml.org,2002:{_tag}', lambda loader, node: loader.construct_scalar(node))


def load_yaml(text: str):
    try:
        return yaml.load(text, Loader=_StringLoader)
    except yaml.YAMLError:
        return None


def scalars(value, depth: int = 0) -> list[str]:
    """String leaves of nested lists, at most 4 deep and 256 items (YAML aliases cannot recurse or blow up)."""
    if isinstance(value, (str, int, float)): return [str(value)]
    if not isinstance(value, list) or depth >= 4: return []
    return [s for item in value[:256] for s in scalars(item, depth + 1)][:256]


TEST_HINT = re.compile(r'\b(test|tests|pytest|tox|nox|unittest|mvn|maven|gradle|npm|yarn|jest|mocha|rake|rspec|prove|make)\b', re.I)


def ci_versions(collector: Collector, keys: tuple[str, ...], travis_keys: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """(path, raw value, source) for every runtime version a CI file names under the given matrix/setup keys.

    GitHub workflows: `strategy.matrix` values and `include` entries of jobs whose name or `run` steps look like
    testing (the workflow's own name does not count), plus
    literal `with:` inputs of setup steps. Travis: the top-level language key and `matrix`/`jobs` include
    entries. Expressions (`${{ ... }}`) are skipped; callers keep anything non-numeric as unparsed."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(collector.files):
        if path.startswith('.github/workflows/') and path.endswith(('.yml', '.yaml')):
            document = load_yaml(collector.text(path) or '')
            jobs = document.get('jobs') if isinstance(document, dict) else None
            for job in (jobs.values() if isinstance(jobs, dict) else ()):
                if not isinstance(job, dict): continue
                steps = [s for s in job.get('steps') or [] if isinstance(s, dict)]
                testing = TEST_HINT.search(' '.join([str(job.get('name', ''))] +
                                                    [str(s.get('run', '')) + ' ' + str(s.get('name', '')) for s in steps]))
                if not testing: continue
                matrix = job['strategy'].get('matrix') if isinstance(job.get('strategy'), dict) else None
                if isinstance(matrix, dict):
                    for key, value in matrix.items():
                        if key in keys: found += [(path, v, 'ci') for v in scalars(value)]
                    for entry in matrix.get('include') if isinstance(matrix.get('include'), list) else []:
                        if isinstance(entry, dict):
                            found += [(path, v, 'ci') for key, value in entry.items() if key in keys for v in scalars(value)]
                for step in steps:
                    inputs = step.get('with') if isinstance(step.get('with'), dict) else {}
                    found += [(path, v, 'ci') for key, value in inputs.items() if key in keys
                              for v in scalars(value) if '${{' not in v]
        elif path in ('.travis.yml',):
            document = load_yaml(collector.text(path) or '')
            if not isinstance(document, dict): continue
            entries = [document] + [e for section in ('matrix', 'jobs') if isinstance(document.get(section), dict)
                                    and isinstance(document[section].get('include'), list)
                                    for e in document[section]['include'] if isinstance(e, dict)]
            for entry in entries:
                found += [(path, v, 'ci') for key in travis_keys if key in entry for v in scalars(entry[key])]
    return [(p, v.strip(), s) for p, v, s in found if '${{' not in v]
