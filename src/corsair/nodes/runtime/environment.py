"""SPEC-0042 hand-off to the environment agent (SPEC-0029) and SPEC-0060 runtime stage of the chain: the selected
matrix row becomes the agent's only toolchain, an unselected requirement stops before the agent runs, and a ready
result is checked against the selection. Deterministic; no model, sandbox or SDK types.

`prepared` maps a matrix row id to the prepared image reference (`repository@sha256:...`) from the operator's
image receipt (`tests/qualification/prepare_toolchains.py`); a selected row without a prepared image stops too.
"""
from dataclasses import dataclass
import re
from typing import Mapping

from corsair.agents.environment.contracts import EnvironmentInput, ReadyEnvironment, Toolchain
from corsair.nodes.runtime.contracts import RuntimeInputs, RuntimeOutcome, RuntimeRequirement, Selection, Supported
from corsair.nodes.runtime.detect import detect
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


def runtime_outcome(requirement: RuntimeRequirement | str, selection: Selection | None,
                    prepared: Mapping[str, str]) -> RuntimeOutcome:
    """The typed result of selection: supported with the prepared image, or the status and reason that stop."""
    if isinstance(requirement, str):
        return RuntimeOutcome(status='undetermined', requirement=None, detection=requirement[:240], selection=None,
                              image=None, reason=f'no runtime requirement: {requirement}'[:2048])
    if selection is None:
        return RuntimeOutcome(status='undetermined', requirement=requirement, detection=None, selection=None,
                              image=None, reason='no runtime requirement: not selected')
    if selection.status != 'supported':
        detail = '; '.join(f'{n.name} {n.preferred or n.allowed}' for n in selection.needs) if selection.status == 'unsupported' \
            else '; '.join(selection.missing)
        return RuntimeOutcome(status=selection.status, requirement=requirement, detection=None, selection=selection,
                              image=None, reason=f'runtime {selection.status}: {detail}'[:2048])
    if selection.image_id not in prepared:
        return RuntimeOutcome(status='not_prepared', requirement=requirement, detection=None, selection=selection,
                              image=None, reason=f'matrix row {selection.image_id} has no prepared image on this node')
    return RuntimeOutcome(status='supported', requirement=requirement, detection=None, selection=selection,
                          image=prepared[selection.image_id], reason=f'runtime supported by matrix row {selection.image_id}')


def select_runtime(inputs: RuntimeInputs, catalog: RuntimeCatalog) -> RuntimeOutcome:
    """Detect, select and resolve the prepared image: the chain's runtime stage in every mode."""
    requirement = detect(inputs.files, inputs.language, root=inputs.root, parents=inputs.parents)
    selection = None if isinstance(requirement, str) else select(requirement, catalog.matrix)
    return runtime_outcome(requirement, selection, catalog.prepared)


def toolchain(selection: Supported, matrix: Matrix, prepared: Mapping[str, str]) -> Toolchain:
    row = next(r for r in matrix.images if r.id == selection.image_id)
    return Toolchain(toolchain_id=row.id, image=prepared[row.id], language=row.language,
                     runtime=f'{row.runtime.name} {row.runtime.version}',
                     tools=tuple(f'{name} {version}' for name, version in sorted(row.tools.items())))


def environment_input(requirement: RuntimeRequirement | str, selection: Selection | None, matrix: Matrix,
                      prepared: Mapping[str, str], **fields) -> EnvironmentInput | RuntimeOutcome:
    """The agent input with exactly the selected toolchain, or the outcome that replaces the agent run.

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
