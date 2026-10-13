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
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
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


# The project's Python dependencies, installed into the tree beside the code and constrained to the image's own
# packages (its pinned pytest among them); a project without requirements.txt installs nothing.
PIP_SETUP = ("if [ -f requirements.txt ]; then /usr/local/bin/python3 -m pip freeze > /tmp/corsair-image.txt; "
             "/usr/local/bin/python3 -m pip install --no-input --disable-pip-version-check --no-compile "
             "--target .corsair-deps -c /tmp/corsair-image.txt -r requirements.txt; fi; mkdir -p .corsair-deps")
# Operator-owned pytest argv: no plugins, config or conftest from the workspace; installed dependencies after the code.
PYTEST = ("/usr/bin/env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "PYTHONDONTWRITEBYTECODE=1", "PYTHONPATH=.:.corsair-deps",
          "/usr/local/bin/python3", "-m", "pytest", "-c", "/dev/null", "--rootdir", ".", "--noconftest",
          "--import-mode=importlib", "-p", "no:cacheprovider", "--basetemp", "/tmp/corsair-scratch")

HARNESSES: dict[str, Harness] = {
    # The fixture and the OpenShell route build their own pytest config (reviewed workspace) from the same runner.
    "pytest": Harness(
        runner=PytestRunner,
        config=PytestRunnerConfig(PYTEST, "/tmp/corsair-junit.xml", WORK, witness_record_path="/tmp/corsair-witness.json"),
        setup=("/bin/sh", "-ec", PIP_SETUP), dependencies=".corsair-deps", lockfiles=("requirements.txt",),
        registry_env=("HTTPS_PROXY", "https_proxy", "PIP_INDEX_URL", "PIP_CERT"),
        scratch_location="The per-test pytest tmp_path directory; fixtures must not be created elsewhere",
        observation_facilities=(
            "Native JUnit XML outcomes, failure locations and captured stdout per test",
            "Operator witness probe, not test code: calls, returns, raised exceptions and file opens attributed to "
            "the identified target function during each test's call phase"),
        witness_facilities=(WitnessFacility(
            id="audit_open", kind="file_open",
            description="Python sys.addaudithook 'open' events recording each path the test process opens during the call"),)),
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
