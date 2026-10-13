"""SPEC-0042 hand-off to the environment agent (SPEC-0029): the selected matrix row becomes the agent's only
toolchain, an unselected requirement stops before the agent runs, and a ready result is checked against the
selection. Deterministic; no model, sandbox or SDK types.

`prepared` maps a matrix row id to the prepared image reference (`repository@sha256:...`) from the operator's
image receipt (`tests/qualification/prepare_toolchains.py`); a selected row without a prepared image stops too.
"""
from dataclasses import dataclass
from typing import Mapping

from corsair.core.blockers import Blocker
from corsair.agents.environment.contracts import EnvironmentInput, ReadyEnvironment, Toolchain
from corsair.nodes.runtime.contracts import RuntimeRequirement, Selection, Supported
from corsair.nodes.runtime.matrix import Matrix

# Environment agent framework table names (agents/environment/frameworks.py) per runner-table framework name.
AGENT_FRAMEWORK = {'pytest': 'pytest', 'junit5': 'junit5', 'junit4': 'junit4'}


@dataclass(frozen=True)
class RuntimeStop:
    """The environment agent does not run: no qualified, prepared image fits the project."""
    requirement: RuntimeRequirement | str
    selection: Selection | None
    reason: str
    diagnostic: Blocker


def toolchain(selection: Supported, matrix: Matrix, prepared: Mapping[str, str]) -> Toolchain:
    row = next(r for r in matrix.images if r.id == selection.image_id)
    return Toolchain(toolchain_id=row.id, image=prepared[row.id], language=row.language,
                     runtime=f'{row.runtime.name} {row.runtime.version}',
                     tools=tuple(f'{name} {version}' for name, version in sorted(row.tools.items())))


def environment_input(requirement: RuntimeRequirement | str, selection: Selection | None, matrix: Matrix,
                      prepared: Mapping[str, str], **fields) -> EnvironmentInput | RuntimeStop:
    """The agent input with exactly the selected toolchain, or the stop that replaces the agent run.

    `fields` are the remaining `EnvironmentInput` fields (commit, source_private, source_files, policy_profile)."""
    evidence = tuple(f"{e.path}:{e.line}" for c in requirement.components for e in (*c.evidence, *c.unparsed)) if isinstance(requirement, RuntimeRequirement) else ()
    def stop(reason, code, summary, actions, owner="operator"):
        return RuntimeStop(requirement, selection, reason, Blocker(
            code=code, summary=summary, certainty="observed", owner=owner, actions=tuple(actions), evidence=evidence))

    if isinstance(requirement, str) or selection is None:
        return stop('no runtime requirement: ' + (requirement if isinstance(requirement, str) else 'not selected'),
                    'runtime_undetermined', 'No actionable runtime selection is available.',
                    ['Inspect the project root and saved build files; resolve missing or unread declarations before selecting an image.',
                     'Run runtime detection and selection again; do not choose a default or nearby runtime.'], 'developer')
    if selection.status != 'supported':
        detail = '; '.join(f'{n.name} {n.preferred or n.allowed}' for n in selection.needs) if selection.status == 'unsupported' \
            else '; '.join(selection.missing)
        if selection.status == 'undetermined':
            return stop(f'runtime undetermined: {detail}', 'runtime_undetermined', 'Runtime declarations are missing, conflicting or unread.',
                        ['Inspect selection.missing and the cited source declarations.',
                         'Supply the missing metadata or correct parser/input support; rerun selection before adding an image.'], 'developer')
        requirements = '; '.join(f'{c.kind} {c.name} {c.allowed}' for c in requirement.components)
        framework_only = all(n.kind == 'test_framework' for n in selection.needs)
        return stop(f'runtime unsupported: {detail}', 'framework_unqualified' if framework_only else 'image_unavailable',
                    'No qualified framework runner matches.' if framework_only else 'No qualified base-image row satisfies the project.',
                    [f'Required components for {requirement.language}: {requirements}.',
                     'Inspect selection.needs and selection.rejected for exact version ranges and per-image mismatches; preferred versions are suggestions, not qualification.',
                     'Qualify the framework/runner on the matching image and register its exact tested version set.' if framework_only else
                     'Add a digest-pinned image with the required runtime/build tools; build and qualify it before registering it in deploy/runtime-matrix.yaml.',
                     'Follow .claude/skills/corsair-base-image/SKILL.md; preserve project constraints and qualify framework support as well.'])
    if selection.image_id not in prepared:
        return stop(f'matrix row {selection.image_id} has no prepared image on this node',
                    'image_not_prepared', f'Qualified image {selection.image_id} is not prepared on this node.',
                    ['Use the existing row and toolchain preparation/load runbook; verify the node image receipt and digest.',
                     'Do not create a replacement row or use the base-image digest as the prepared application image.'])
    return EnvironmentInput(toolchains=(toolchain(selection, matrix, prepared),), **fields)


def check_ready(result: ReadyEnvironment, selection: Supported, prepared: Mapping[str, str]) -> None:
    """Refuse a ready environment that left the selected image or used a framework the selection did not admit."""
    if result.toolchain_id != selection.image_id or result.toolchain_image != prepared[selection.image_id]:
        raise ValueError('ready environment does not use the selected toolchain image')
    admitted = {AGENT_FRAMEWORK.get(c.name) for c in selection.checks if c.kind == 'test_framework' and c.satisfied}
    if result.framework not in admitted:
        raise ValueError(f'framework {result.framework!r} is not one the selection admitted ({sorted(a for a in admitted if a)})')
