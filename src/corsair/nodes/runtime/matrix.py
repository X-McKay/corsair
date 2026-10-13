"""SPEC-0042 runtime matrix loader and selection: a requirement either matches one qualified image row exactly,
is unsupported with the missing components named, or is undetermined. No row is ever chosen as a substitute.

SPEC-0069: when the build files declare no runtime version at all, the runtime range is inferred from the operator's
`inference` rows (the runtime versions a test framework release supports, as its own package metadata publishes), and
the newest qualified image inside that range is selected and recorded as inferred. No inference row, no range."""
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator
import yaml

from corsair.nodes.runtime.contracts import (AxisCheck, Component, Language, Need, Rejection, RuntimeRequirement,
                                             Selection, Supported, Undetermined, Unsupported, _Frozen)
from corsair.nodes.runtime.versions import parse_set, parse_version

MAX_TEXT = 240  # contracts.Text
MATRIX = Path(__file__).resolve().parents[4] / 'deploy/runtime-matrix.yaml'
Name = str
VersionText = str


class Qualification(_Frozen):
    # `image-only`: the image built and the gate body and a real case passed under plain Docker; selectable while the
    # project is in development, never reported as qualified. `live`: the kind/OpenShell toolchain gate passed.
    evidence: Literal['live', 'image-only']
    records: tuple[str, ...] = Field(min_length=1)
    report: str = Field(min_length=1)
    note: str = ''

    @field_validator('records')
    @classmethod
    def record_ids(cls, records):
        if not all(re.fullmatch(r'(SPEC|PLAN|HANDOFF|ISSUE)-\d{4}', r) for r in records): raise ValueError('record ids required')
        return records


class Runtime(_Frozen):
    name: Name
    version: VersionText


class ImageRow(_Frozen):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9.-]*$')
    language: Language
    base_image: str = Field(pattern=r'^[^@\s]+@sha256:[0-9a-f]{64}$')
    image_source: str
    runtime: Runtime
    tools: dict[Name, VersionText]
    selector: dict[str, str]
    qualification: Qualification

    @model_validator(mode='after')
    def versions(self) -> 'ImageRow':
        for version in (self.runtime.version, *self.tools.values()): parse_version(version)
        if self.selector: raise ValueError('selector rows need a qualified multi-runtime image (SPEC-0042)')
        return self


class SmokeTemplate(_Frozen):
    """SPEC-0071: one trivially passing test in this framework, written beside the captured commit at preparation
    time (never baked into an image) and used as the environment baseline only when no project test runs."""
    path: str = Field(min_length=1, max_length=256, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_./-]*$')
    test_id: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=4096)


class FrameworkRow(_Frozen):
    name: Name
    language: Language
    versions: str = Field(description='Canonical version set the runner and report parser are qualified for')
    runner: str
    smoke: SmokeTemplate | None = None
    images: tuple[str, ...] = Field(min_length=1, description='Image ids this range was qualified on; a new image row has '
                                                                'no framework support until its own range is qualified')
    qualification: Qualification

    def applies(self, row: 'ImageRow') -> bool:
        return row.language == self.language and row.id in self.images

    @field_validator('versions')
    @classmethod
    def canonical(cls, versions):
        if parse_set(versions).is_empty: raise ValueError('empty framework range')
        return versions


class InferenceRow(_Frozen):
    """The runtime versions a framework release range supports, copied from that release's published metadata
    (PyPI requires-python, npm engines, CPAN MIN_PERL_VERSION). It never says what a project needs, only what the
    framework it declares can run on."""
    framework: Name
    language: Language
    versions: str = Field(description='Canonical framework version set this row covers')
    runtime: Name
    supports: str = Field(description='Canonical runtime version set those releases declare')
    source: str = Field(min_length=1, max_length=200, description='Where the metadata was read')

    @field_validator('versions', 'supports')
    @classmethod
    def canonical(cls, value):
        if parse_set(value).is_empty: raise ValueError('empty version set')
        return value


class Matrix(_Frozen):
    schema_version: int = Field(ge=1, le=1)
    images: tuple[ImageRow, ...] = Field(min_length=1)
    frameworks: tuple[FrameworkRow, ...]
    inference: tuple[InferenceRow, ...] = ()

    @model_validator(mode='after')
    def unique(self) -> 'Matrix':
        if len({row.id for row in self.images}) != len(self.images): raise ValueError('duplicate image id')
        ids = {row.id: row for row in self.images}
        for f in self.frameworks:
            if any(i not in ids or ids[i].language != f.language for i in f.images):
                raise ValueError(f'framework row {f.name} names an image that is not a {f.language} row')
        for row in self.images:
            names = [f.name for f in self.frameworks if f.applies(row)]
            if len(names) != len(set(names)): raise ValueError(f'duplicate framework row for image {row.id}')
        for f in self.frameworks:
            if any(g.name == f.name and g.smoke != f.smoke for g in self.frameworks):
                raise ValueError(f'framework rows named {f.name} carry different smoke tests')
        runtimes = {(row.language, row.runtime.name) for row in self.images}
        for i in self.inference:
            if (i.language, i.runtime) not in runtimes: raise ValueError(f'inference row {i.framework} names runtime {i.runtime}, '
                                                                         f'which no {i.language} image row provides')
        return self


def load(path: Path = MATRIX) -> Matrix:
    return Matrix.model_validate(yaml.safe_load(path.read_text()))


def _check(component: Component, provided: str | None) -> AxisCheck:
    """An image component must contain the provided version; a framework range must overlap the qualified range."""
    if provided is None: satisfied = False
    elif component.kind == 'test_framework': satisfied = not parse_set(component.allowed).intersect(parse_set(provided)).is_empty
    else: satisfied = parse_set(component.allowed).contains(parse_version(provided))
    return AxisCheck(kind=component.kind, name=component.name, allowed=component.allowed, provided=provided, satisfied=satisfied)


def _matched(component: Component) -> bool:
    return component.provider == 'image' or component.kind == 'test_framework'


def _blocking(component: Component) -> str:
    """Constraints or pins the detector saw but could not read; any of them could exclude a row that otherwise fits.
    Unread `tested` entries are alternatives (a CI PyPy or dev job) and do not block."""
    return '; '.join(f'{u.path}:{u.line} {u.reason}' for u in component.unparsed if u.strength != 'tested')[:200]


def _inferable(requirement: RuntimeRequirement) -> bool:
    """No runtime version declared and nothing unread that could have declared one: SPEC-0069 inference applies."""
    runtimes = requirement.component('runtime')
    return not any(c.declared for c in runtimes) and not any(u.strength != 'tested' for c in runtimes for u in c.unparsed)


def _missing(requirement: RuntimeRequirement, infer: bool = False) -> list[str]:
    missing = []
    runtimes = requirement.component('runtime')
    missing += [f'{c.name} {c.kind.replace("_", " ")} declaration not understood: {reasons}'
                for c in requirement.components
                if _matched(c) and c.kind != 'test_framework' and (c.declared or c.kind != 'runtime') and (reasons := _blocking(c))]
    framework_known = any(c.declared for c in requirement.component('test_framework'))
    if not any(c.declared for c in runtimes) and not (infer and framework_known):
        reasons = '; '.join(f'{u.path}:{u.line} {u.reason}' for c in runtimes for u in c.unparsed)[:200]
        missing.append('runtime version not declared in the build files' + (f' ({reasons})' if reasons else ''))
    missing += [f'{c.name} declarations conflict: {", ".join(f"{e.path}:{e.line} {e.declares}" for e in c.evidence)}'[:240]
                for c in requirement.components if c.declared and c.conflict and _matched(c)]
    missing += [f'unresolved input: {u}' for u in requirement.unresolved]
    if not any(c.declared for c in requirement.component('test_framework')):
        reasons = '; '.join(f'{u.path}:{u.line} {u.reason}' for c in requirement.component('test_framework') for u in c.unparsed)[:200]
        missing.append('test framework not identified' + (f' ({reasons})' if reasons else ''))
    return [m[:MAX_TEXT] for m in missing]


def _infer(requirement: RuntimeRequirement, matrix: Matrix, wanted: list[Component], unread: dict[str, str]) -> Selection:
    """Newest qualified image whose runtime a usable framework release supports; usable means inside the project's
    range, the row's qualified range and one inference row's range. Recorded as inferred, never as declared. A
    framework with an unread constraint is not usable, since that constraint could exclude every inferred range."""
    if unread:
        return Undetermined(status='undetermined', missing=tuple(
            f'runtime version not declared, and the {name} test framework declaration that would infer it is not understood: {reasons}'[:MAX_TEXT]
            for name, reasons in unread.items())[:64])
    frameworks = [c for c in wanted if c.kind == 'test_framework']
    others = [c for c in wanted if c.kind != 'test_framework']
    rows = sorted((r for r in matrix.images if r.language == requirement.language),
                  key=lambda r: parse_version(r.runtime.version), reverse=True)
    covering = [(c, i) for c in frameworks for i in matrix.inference if i.language == requirement.language
                and i.framework == c.name and not parse_set(c.allowed).intersect(parse_set(i.versions)).is_empty]
    rejected, tool_blocked = [], {}
    for row in rows:
        provided = {('build_tool', k): v for k, v in row.tools.items()}
        checks = [_check(c, provided.get((c.kind, c.name))) for c in others]
        usable = []
        for c, i in covering:
            if i.runtime != row.runtime.name or not parse_set(i.supports).contains(parse_version(row.runtime.version)): continue
            for f in matrix.frameworks:
                if f.name == c.name and f.applies(row):
                    overlap = parse_set(c.allowed).intersect(parse_set(f.versions)).intersect(parse_set(i.versions))
                    if not overlap.is_empty: usable.append((c, i, f, overlap))
        if all(check.satisfied for check in checks) and usable:
            c, i, f, overlap = usable[0]
            runtime = AxisCheck(kind='runtime', name=row.runtime.name, allowed=i.supports, provided=row.runtime.version, satisfied=True)
            framework = AxisCheck(kind='test_framework', name=c.name, allowed=c.allowed, provided=str(overlap), satisfied=True)
            evidence = 'live' if row.qualification.evidence == f.qualification.evidence == 'live' else 'image-only'
            used = tuple(f'{x.framework} {x.versions} supports {x.runtime} {x.supports} ({x.source})'[:MAX_TEXT] for _, x, _, _ in usable)
            return Supported(status='supported', image_id=row.id, image=row.base_image, checks=(runtime, *checks, framework),
                             evidence=evidence, runtime_basis='inferred', inferred_from=tuple(dict.fromkeys(used))[:16])
        rejected.append(Rejection(image_id=row.id, unmet=tuple(c for c in checks if not c.satisfied)))
        if usable:
            # The runtime and framework fit this row; only the project's declared tools did not.
            tool_blocked.update({c.name: c for c, check in zip(others, checks) if not check.satisfied})
    if tool_blocked:
        return Unsupported(status='unsupported', rejected=tuple(rejected), needs=tuple(
            Need(kind=c.kind, name=c.name, allowed=c.allowed, preferred=c.preferred) for c in tool_blocked.values()))
    if not covering:
        return Undetermined(status='undetermined', missing=tuple(
            f'runtime version not declared in the build files, and no inference row covers {c.name} {c.allowed}'[:MAX_TEXT]
            for c in frameworks)[:64])
    by_runtime: dict[str, object] = {}
    for _, i in covering:
        by_runtime[i.runtime] = by_runtime[i.runtime].union(parse_set(i.supports)) if i.runtime in by_runtime else parse_set(i.supports)
    needs = tuple(Need(kind='runtime', name=name, allowed=str(versions), preferred=None) for name, versions in by_runtime.items())
    needs += tuple(Need(kind=c.kind, name=c.name, allowed=c.allowed, preferred=c.preferred) for c in frameworks
                   if c.name in {x.name for x, _ in covering})
    return Unsupported(status='unsupported', needs=needs, rejected=tuple(rejected))


def select(requirement: RuntimeRequirement, matrix: Matrix) -> Selection:
    infer = _inferable(requirement) and bool(matrix.inference)
    if (missing := _missing(requirement, infer)):
        return Undetermined(status='undetermined', missing=tuple(missing)[:64])
    wanted = [c for c in requirement.components if c.declared and _matched(c)]
    # A framework with an unread constraint cannot count as the qualified one, and if the project's runtime fits a
    # row but no readable framework does, the unread one might have: that is undetermined, not unsupported.
    unread = {c.name: reasons for c in requirement.component('test_framework') if (reasons := _blocking(c))}
    if infer:
        return _infer(requirement, matrix, wanted, unread)
    rejected = []
    runtime_fits = False
    for row in matrix.images:
        if row.language != requirement.language: continue
        provided = {('runtime', row.runtime.name): row.runtime.version,
                    **{('build_tool', k): v for k, v in row.tools.items()},
                    **{('test_framework', f.name): f.versions for f in matrix.frameworks if f.applies(row)}}
        checks = tuple(_check(c, None if c.kind == 'test_framework' and c.name in unread else provided.get((c.kind, c.name)))
                       for c in wanted)
        # Every runtime and image tool must match; of the project's declared test frameworks, one qualified
        # runner suffices (its name is in `checks`), since the baseline and authored tests use that framework.
        frameworks = [check for check in checks if check.kind == 'test_framework']
        if all(check.satisfied for check in checks if check.kind != 'test_framework'):
            runtime_fits = True
            if any(f.satisfied for f in frameworks):
                rows = [row.qualification.evidence, *(f.qualification.evidence for f in matrix.frameworks if f.applies(row)
                                                      and any(c.satisfied and c.name == f.name for c in frameworks))]
                evidence = 'live' if all(e == 'live' for e in rows) else 'image-only'
                return Supported(status='supported', image_id=row.id, image=row.base_image, checks=checks, evidence=evidence)
        unmet = [c for c in checks if not c.satisfied and c.kind != 'test_framework']
        rejected.append(Rejection(image_id=row.id, unmet=tuple(unmet + ([] if any(f.satisfied for f in frameworks) else frameworks))))
    if runtime_fits and unread:
        return Undetermined(status='undetermined', missing=tuple(
            f'{name} test framework declaration not understood: {reasons}'[:MAX_TEXT] for name, reasons in unread.items())[:64])
    unmet = {(c.kind, c.name) for c in min(rejected, key=lambda r: len(r.unmet)).unmet} if rejected else \
        {(c.kind, c.name) for c in wanted}
    needs = tuple(Need(kind=c.kind, name=c.name, allowed=c.allowed, preferred=c.preferred)
                  for c in wanted if (c.kind, c.name) in unmet)
    return Unsupported(status='unsupported', needs=needs, rejected=tuple(rejected))
