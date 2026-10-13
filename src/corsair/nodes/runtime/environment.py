"""SPEC-0042 hand-off to the environment agent (SPEC-0029) and SPEC-0060 runtime stage of the chain: the selected
matrix row becomes the agent's only toolchain, an unselected requirement stops before the agent runs with a
structured blocker, and a ready result is checked against the selection. Deterministic; no model, sandbox or SDK
types.

`prepared` maps a matrix row id to the prepared image reference (`repository@sha256:...`) from the operator's
image receipt (`tests/qualification/prepare_toolchains.py`); a selected row without a prepared image stops too.
"""
from dataclasses import dataclass
import json
import re
from typing import Mapping

from corsair.agents.environment.contracts import EnvironmentInput, ReadyEnvironment, Toolchain
from corsair.core.blockers import Blocker
from corsair.nodes.runtime.contracts import (MAX_INPUT_BYTES, Language, RuntimeInputs, RuntimeOutcome,
                                             RuntimeRequirement, Selection, Supported)
from corsair.nodes.runtime.detect import detect, is_build_file
from corsair.nodes.runtime.matrix import Matrix, select

# Environment agent framework table names (agents/environment/frameworks.py) per runner-table framework name.
AGENT_FRAMEWORK = {'pytest': 'pytest', 'junit5': 'junit5', 'junit4': 'junit4'}
PREPARED_IMAGE = re.compile(r'^[^@\s]+@sha256:[0-9a-f]{64}$')


@dataclass(frozen=True)
class RuntimeCatalog:
    """Operator-owned worker configuration: the runtime matrix and this node's prepared image per row."""
    matrix: Matrix
    prepared: Mapping[str, str]

    def __post_init__(self):
        rows = {row.id for row in self.matrix.images}
        for row, image in self.prepared.items():
            if row not in rows or not PREPARED_IMAGE.fullmatch(image):
                raise ValueError(f'prepared image for {row!r} is not a digest-pinned image of a matrix row')


def _encoded(path: str, data: bytes) -> int:
    """Bytes one `files`/`parents` entry adds to the encoded inputs: JSON-quoted path (ASCII-escaped, so never
    under its UTF-8 size), colon, quoted base64 value, comma."""
    return len(json.dumps(path)) + 4 + 4 * -(-len(data) // 3)


def runtime_inputs(files: Mapping[str, bytes], language: Language | None = None, *,
                   parents: Mapping[str, bytes] | None = None, root: str = '.') -> RuntimeInputs:
    """The case's runtime inputs from a snapshot's files: build files only, smallest first, while the encoded inputs
    (paths and base64 included) stay within `MAX_INPUT_BYTES`; anything left out is named in `omitted`,
    deterministically. Space is reserved for the `omitted` list itself (at most 64 names of up to 1024 bytes)."""
    parents = dict(parents or {})
    base = RuntimeInputs.model_construct(files={}, language=language, parents={}, root=root, omitted=())
    budget = MAX_INPUT_BYTES - len(base.__pydantic_serializer__.to_json(base)) - sum(_encoded(p, v) for p, v in parents.items()) \
        - 64 * (len(json.dumps('x' * 1024)) + 1)
    if budget < 0:
        raise ValueError(f'parent POMs alone exceed {MAX_INPUT_BYTES} encoded bytes')
    kept, omitted = {}, []
    for path in sorted((p for p in files if is_build_file(p)), key=lambda p: (_encoded(p, files[p]), p)):
        cost = _encoded(path, files[path])
        if cost <= budget and len(path) <= 1024:
            kept[path], budget = files[path], budget - cost
        else:
            omitted.append(path[:1024])
    return RuntimeInputs(files=kept, language=language, parents=parents, root=root, omitted=tuple(sorted(omitted))[:64])


def _blocker(requirement: RuntimeRequirement | str, selection: Selection | None) -> Blocker:
    """Operator or developer guidance for a stop (SPEC-0060 carrying #63's structured blockers)."""
    evidence = tuple(f'{e.path}:{e.line}' for c in requirement.components for e in (*c.evidence, *c.unparsed)) \
        if isinstance(requirement, RuntimeRequirement) else ()

    def blocker(code, summary, actions, owner='operator'):
        return Blocker(code=code, summary=summary, certainty='observed', owner=owner, actions=tuple(actions),
                       evidence=evidence)
    if isinstance(requirement, str) or selection is None:
        return blocker('runtime_undetermined', 'No actionable runtime selection is available.',
                       ['Inspect the project root and saved build files; resolve missing or unread declarations before selecting an image.',
                        'Run runtime detection and selection again; do not choose a default or nearby runtime.'], 'developer')
    if selection.status == 'undetermined':
        return blocker('runtime_undetermined', 'Runtime declarations are missing, conflicting or unread.',
                       ['Inspect selection.missing and the cited source declarations.',
                        'Supply the missing metadata or correct parser/input support; rerun selection before adding an image.'], 'developer')
    if selection.status == 'unsupported':
        requirements = '; '.join(f'{c.kind} {c.name} {c.allowed}' for c in requirement.components)
        framework_only = all(n.kind == 'test_framework' for n in selection.needs)
        return blocker('framework_unqualified' if framework_only else 'image_unavailable',
                       'No qualified framework runner matches.' if framework_only else 'No qualified base-image row satisfies the project.',
                       [f'Required components for {requirement.language}: {requirements}.',
                        'Inspect selection.needs and selection.rejected for exact version ranges and per-image mismatches; preferred versions are suggestions, not qualification.',
                        'Qualify the framework/runner on the matching image and register its exact tested version set.' if framework_only else
                        'Add a digest-pinned image with the required runtime/build tools; build and qualify it before registering it in deploy/runtime-matrix.yaml.',
                        'Follow .claude/skills/corsair-base-image/SKILL.md; preserve project constraints and qualify framework support as well.'])
    return blocker('image_not_prepared', f'Qualified image {selection.image_id} is not prepared on this node.',
                   ['Use the existing row and toolchain preparation/load runbook; verify the node image receipt and digest.',
                    'Do not create a replacement row or use the base-image digest as the prepared application image.'])


def runtime_outcome(requirement: RuntimeRequirement | str, selection: Selection | None,
                    prepared: Mapping[str, str]) -> RuntimeOutcome:
    """The typed result of selection: supported with the prepared image, or the status, reason and blocker that stop."""
    def stop(status, reason):
        return RuntimeOutcome(status=status, requirement=None if isinstance(requirement, str) else requirement,
                              detection=requirement[:240] if isinstance(requirement, str) else None,
                              selection=selection, image=None, reason=reason[:2048],
                              diagnostic=_blocker(requirement, selection))
    if isinstance(requirement, str):
        return stop('undetermined', f'no runtime requirement: {requirement}')
    if selection is None:
        return stop('undetermined', 'no runtime requirement: not selected')
    if selection.status != 'supported':
        detail = '; '.join(f'{n.name} {n.preferred or n.allowed}' for n in selection.needs) if selection.status == 'unsupported' \
            else '; '.join(selection.missing)
        return stop(selection.status, f'runtime {selection.status}: {detail}')
    if selection.image_id not in prepared:
        return stop('not_prepared', f'matrix row {selection.image_id} has no prepared image on this node')
    return RuntimeOutcome(status='supported', requirement=requirement, detection=None, selection=selection,
                          image=prepared[selection.image_id], reason=f'runtime supported by matrix row {selection.image_id}')


def select_runtime(inputs: RuntimeInputs, catalog: RuntimeCatalog) -> RuntimeOutcome:
    """Detect, select and resolve the prepared image: the chain's runtime stage in every mode. A build file the
    case omitted for size is an unresolved input, so the selection is undetermined rather than guessed."""
    requirement = detect(inputs.files, inputs.language, root=inputs.root, parents=inputs.parents)
    if inputs.omitted:
        unread = tuple(f'{path} omitted from the chain inputs (over {MAX_INPUT_BYTES} encoded bytes in total), not read'[:240]
                       for path in inputs.omitted)
        requirement = f'{requirement}; {unread[0]}'[:240] if isinstance(requirement, str) else \
            requirement.model_copy(update={'unresolved': (requirement.unresolved + unread)[:64]})
    selection = None if isinstance(requirement, str) else select(requirement, catalog.matrix)
    return runtime_outcome(requirement, selection, catalog.prepared)


def toolchain(selection: Supported, matrix: Matrix, prepared: Mapping[str, str]) -> Toolchain:
    row = next(r for r in matrix.images if r.id == selection.image_id)
    return Toolchain(toolchain_id=row.id, image=prepared[row.id], language=row.language,
                     runtime=f'{row.runtime.name} {row.runtime.version}',
                     tools=tuple(f'{name} {version}' for name, version in sorted(row.tools.items())))


def environment_input(requirement: RuntimeRequirement | str, selection: Selection | None, matrix: Matrix,
                      prepared: Mapping[str, str], **fields) -> EnvironmentInput | RuntimeOutcome:
    """The agent input with exactly the selected toolchain, or the outcome (with its blocker) that replaces the
    agent run.

    `fields` are the remaining `EnvironmentInput` fields (commit, source_private, source_files, policy_profile)."""
    outcome = runtime_outcome(requirement, selection, prepared)
    if outcome.status != 'supported':
        return outcome
    return EnvironmentInput(toolchains=(toolchain(selection, matrix, prepared),), **fields)


def check_ready(result: ReadyEnvironment, selection: Supported, prepared: Mapping[str, str]) -> None:
    """Refuse a ready environment that left the selected image or used a framework the selection did not admit."""
    if result.toolchain_id != selection.image_id or result.toolchain_image != prepared[selection.image_id]:
        raise ValueError('ready environment does not use the selected toolchain image')
    admitted = {AGENT_FRAMEWORK.get(c.name) for c in selection.checks if c.kind == 'test_framework' and c.satisfied}
    if result.framework not in admitted:
        raise ValueError(f'framework {result.framework!r} is not one the selection admitted ({sorted(a for a in admitted if a)})')
