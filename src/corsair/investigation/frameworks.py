"""The one table of per-framework facts, keyed by the framework row runtime selection fixed (the matrix framework
row's name, deploy/runtime-matrix.yaml). Code reads this table and never branches on a language; images stay plain
pinned runtimes and hold none of it.

An entry gives the runner adapter and its config, the setup step that installs the project's own dependencies from
its manifests with registry access (the framework comes from the project's lockfile, never the image), where those
dependencies live in the tree and which lockfiles bind them, the scratch and observation facilities declared to the
planner, and the operator's witness recorders. A framework without witness recorders reaches planning and stops
there (SPEC-0040 needs a listed facility); one without a setup step cannot run on the image-only route yet.
"""
from dataclasses import dataclass
import shlex
from typing import Any

from corsair.adapters.docker_image import WORK
from corsair.adapters.jest_runner import JestRunner, JestRunnerConfig
from corsair.adapters.pytest_runner import PytestRunner
from corsair.agents.test_planning.contracts import WitnessFacility


@dataclass(frozen=True)
class Harness:
    runner: type  # A TestRunner adapter: runner(workspace, execution, store, config)
    config: Any = None  # The image-only route's runner config; None: that route is not built for this framework
    setup: tuple[str, ...] = ()  # argv run in a copy of the tree with registry access; no test body runs
    dependencies: str | None = None  # Tree-relative directory setup fills, copied into every run's workspace
    lockfiles: tuple[str, ...] = ()  # What the installed dependencies are bound to (with the image and commit)
    registry_env: tuple[str, ...] = ()  # Host variables passed to setup when set (a proxy and its CA file)
    scratch_location: str = ""
    observation_facilities: tuple[str, ...] = ()
    witness_facilities: tuple[WitnessFacility, ...] = ()

    @property
    def setup_script(self) -> str:
        return shlex.join(self.setup)


HARNESSES: dict[str, Harness] = {
    # The fixture and the OpenShell route build their own pytest config (reviewed workspace, witness probe).
    "pytest": Harness(runner=PytestRunner),
    "jest": Harness(
        runner=JestRunner,
        config=JestRunnerConfig(command=("/usr/local/bin/node", "node_modules/jest/bin/jest.js", "--ci"),
                                workspace_root=WORK, report_path="/tmp/corsair-jest.json"),
        # The upstream node image's own npm; scripts never run.
        setup=("/usr/local/bin/node", "/usr/local/lib/node_modules/npm/bin/npm-cli.js", "--ignore-scripts",
               "--no-audit", "--no-update-notifier", "--cache", "/tmp/npm", "ci"),
        dependencies="node_modules", lockfiles=("package-lock.json",),
        registry_env=("HTTPS_PROXY", "https_proxy", "NODE_EXTRA_CA_CERTS"),
        scratch_location="A fresh directory the test creates under os.tmpdir(); fixtures must not be created elsewhere",
        observation_facilities=("Native Jest JSON report: outcome, failure message and failing line per test",)),
}


class NoHarness(ValueError):
    """The selected framework has no entry, or no image-only route; refused before any model request."""


def harness(framework: str, *, route: bool = False) -> Harness:
    """The entry for a framework row; with `route`, refused unless the image-only route is built for it."""
    entry = HARNESSES.get(framework)
    if entry is None:
        raise NoHarness(f"no harness entry for the {framework} framework yet")
    if route and (entry.config is None or not entry.setup):
        raise NoHarness(f"no image-only route for the {framework} framework yet")
    return entry
