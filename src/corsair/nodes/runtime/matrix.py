"""SPEC-0042 runtime matrix loader and selection: a requirement either matches one qualified image row exactly,
is unsupported with the missing components named, or is undetermined. No row is ever chosen as a substitute."""
from pathlib import Path
import re

from pydantic import Field, field_validator, model_validator
import yaml

from corsair.nodes.runtime.contracts import (AxisCheck, Component, Language, Need, Rejection, RuntimeRequirement,
                                             Selection, Supported, Undetermined, Unsupported, _Frozen)
from corsair.nodes.runtime.versions import parse_set, parse_version

MATRIX = Path(__file__).resolve().parents[4] / 'deploy/runtime-matrix.yaml'
Name = str
VersionText = str


class Qualification(_Frozen):
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


class FrameworkRow(_Frozen):
    name: Name
    language: Language
    versions: str = Field(description='Canonical version set the runner and report parser are qualified for')
    runner: str
    qualification: Qualification

    @field_validator('versions')
    @classmethod
    def canonical(cls, versions):
        if parse_set(versions).is_empty: raise ValueError('empty framework range')
        return versions


class Matrix(_Frozen):
    schema_version: int = Field(ge=1, le=1)
    images: tuple[ImageRow, ...] = Field(min_length=1)
    frameworks: tuple[FrameworkRow, ...]

    @model_validator(mode='after')
    def unique(self) -> 'Matrix':
        if len({row.id for row in self.images}) != len(self.images): raise ValueError('duplicate image id')
        if len({(f.language, f.name) for f in self.frameworks}) != len(self.frameworks): raise ValueError('duplicate framework row')
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


def _missing(requirement: RuntimeRequirement) -> list[str]:
    missing = []
    runtimes = requirement.component('runtime')
    if not any(c.declared for c in runtimes):
        reasons = '; '.join(f'{u.path}:{u.line} {u.reason}' for c in runtimes for u in c.unparsed)[:200]
        missing.append('runtime version not declared in the build files' + (f' ({reasons})' if reasons else ''))
    missing += [f'{c.name} declarations conflict: {", ".join(f"{e.path}:{e.line} {e.declares}" for e in c.evidence)}'[:240]
                for c in requirement.components if c.declared and c.conflict and _matched(c)]
    if not any(c.declared for c in requirement.component('test_framework')):
        reasons = '; '.join(f'{u.path}:{u.line} {u.reason}' for c in requirement.component('test_framework') for u in c.unparsed)[:200]
        missing.append('test framework not identified' + (f' ({reasons})' if reasons else ''))
    return missing


def select(requirement: RuntimeRequirement, matrix: Matrix) -> Selection:
    if (missing := _missing(requirement)):
        return Undetermined(status='undetermined', missing=tuple(missing + list(requirement.unresolved))[:64])
    wanted = [c for c in requirement.components if c.declared and _matched(c)]
    supported = {f.name: f.versions for f in matrix.frameworks if f.language == requirement.language}
    rejected = []
    for row in matrix.images:
        if row.language != requirement.language: continue
        provided = {('runtime', row.runtime.name): row.runtime.version,
                    **{('build_tool', k): v for k, v in row.tools.items()},
                    **{('test_framework', k): v for k, v in supported.items()}}
        checks = tuple(_check(c, provided.get((c.kind, c.name))) for c in wanted)
        # Every runtime and image tool must match; of the project's declared test frameworks, one qualified
        # runner suffices (its name is in `checks`), since the baseline and authored tests use that framework.
        frameworks = [check for check in checks if check.kind == 'test_framework']
        if all(check.satisfied for check in checks if check.kind != 'test_framework') and any(f.satisfied for f in frameworks):
            return Supported(status='supported', image_id=row.id, image=row.base_image, checks=checks)
        unmet = [c for c in checks if not c.satisfied and c.kind != 'test_framework']
        rejected.append(Rejection(image_id=row.id, unmet=tuple(unmet + ([] if any(f.satisfied for f in frameworks) else frameworks))))
    unmet = {(c.kind, c.name) for c in min(rejected, key=lambda r: len(r.unmet)).unmet} if rejected else \
        {(c.kind, c.name) for c in wanted}
    needs = tuple(Need(kind=c.kind, name=c.name, allowed=c.allowed, preferred=c.preferred)
                  for c in wanted if (c.kind, c.name) in unmet)
    return Unsupported(status='unsupported', needs=needs, rejected=tuple(rejected))
