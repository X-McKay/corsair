"""The operator's per-framework harness table: the selected framework row's runner picks the runner adapter, its
config and the image-only Docker harness that installs dependencies and gives each run a fresh revision workspace.

Keyed by the matrix framework row's `runner` path (deploy/runtime-matrix.yaml), so a case reaches the runner its
own build files selected, never pytest's by default. A language joins by adding one row whose functions follow its
`tests/qualification/<language>_image_case.py` module; a selected framework with no row stops the case before any
model request.
"""
from dataclasses import dataclass
from typing import Any, Callable

from corsair.adapters.jest_runner import JestRunner
from corsair.nodes.runtime.matrix import FrameworkRow
from tests.qualification import node_image_case


@dataclass(frozen=True)
class Harness:
    runner: type  # A TestRunner adapter: runner(workspace, execution, store, config)
    config: Any
    # Installs the commit's own dependencies with registry access into a fresh directory; returns the exit status.
    setup: Callable[..., int]  # (image, tree, dependencies, evidence)
    setup_identity: Callable[..., dict]  # (image, tree, commit): what a dependency directory was installed for
    # The offline container of one revision: (image, tree, dependencies, commit, timeout, evidence) -> DockerCase
    workspace: Callable[..., Any]
    # Host variables passed to setup and the environment stage's sandbox only when set (a proxy and its CA file).
    registry_env: tuple[str, ...]
    # Declared to the planner and author; the environment stage observes the rest.
    scratch_location: str
    observation_facilities: tuple[str, ...]


HARNESSES = {
    "src/corsair/adapters/jest_runner.py": Harness(
        runner=JestRunner, config=node_image_case.CONFIG, setup=node_image_case.setup,
        setup_identity=node_image_case.setup_identity, workspace=node_image_case.workspace,
        registry_env=node_image_case.SETUP_ENV,
        scratch_location="A fresh directory the test creates under os.tmpdir(); fixtures must not be created elsewhere",
        observation_facilities=("Native Jest JSON report: outcome, failure message and failing line per test",)),
}


def harness(row: FrameworkRow) -> Harness:
    """The harness for the selected framework row's runner; refused when no harness serves that runner yet."""
    try:
        return HARNESSES[row.runner]
    except KeyError:
        raise ValueError(f"no case harness for the {row.name} runner {row.runner} yet") from None
