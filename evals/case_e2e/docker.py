"""Image-only Docker ports for a benchmark case: the environment stage's setup sandbox and the revision runners.

Stand-ins for the OpenShell ports until SPEC-0026 dependency provisioning reaches the sandbox: the selected
toolchain's prepared image under plain Docker, capabilities dropped, the commit's own blobs. Only the environment
stage's sandbox reaches a registry; every test run is offline in a fresh container. Image evidence, not sandbox
qualification.
"""
from contextlib import ExitStack
import os
from pathlib import Path
from typing import Literal, Mapping

from corsair.agents.environment.contracts import Toolchain
from corsair.composition.direct import PreparedSandbox
from tests.qualification.image_case import WORK, DockerCase, docker, require_setup, write_setup

from .frameworks import Harness

SCRATCH = "/tmp/corsair-scratch"


def registry_access(names: tuple[str, ...]) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Network, environment and read-only mounts for registry access during setup: the host's network only when the
    host itself reaches the registry through the variables `names` (a proxy, its CA file), else the bridge."""
    env = tuple(f"{name}={os.environ[name]}" for name in names if os.environ.get(name))
    files = tuple((value, value) for name in names if (value := os.environ.get(name, "")).startswith("/")
                  and Path(value).is_file())
    return ("host" if env else "bridge"), env, files


class DockerPreparation:
    """The environment stage's sandbox: the selected row's local image with the baseline tree copied to the
    workspace and registry access, released (container removed, removal confirmed) after the stage."""

    def __init__(self, images: Mapping[str, str], tree: Path, commit: str, harness: Harness, timeout: int):
        self.images, self.tree, self.commit, self.harness, self.timeout = images, tree, commit, harness, timeout

    def prepare(self, toolchain: Toolchain, operation) -> PreparedSandbox:
        network, env, mounts = registry_access(self.harness.registry_env)
        sandbox = DockerCase(self.images[toolchain.toolchain_id], self.tree, self.commit, self.timeout,
                             kind="case-environment", docker=docker, mounts=mounts, env=("HOME=/tmp", *env),
                             network=network)
        sandbox.__enter__()
        copied = docker("exec", sandbox.container, "/bin/sh", "-ec", f"cp -R /src {WORK}; mkdir -p {SCRATCH}")
        if copied.returncode != 0:
            sandbox.__exit__(None, None, None)
            raise RuntimeError(f"environment sandbox workspace copy failed: {copied.stderr[-512:]!r}")
        return PreparedSandbox(sandbox, sandbox.handle(operation), SCRATCH)

    def release(self, sandbox: PreparedSandbox, operation) -> Literal["confirmed", "unconfirmed"]:
        sandbox.execution.__exit__(None, None, None)
        return sandbox.execution.cleanup


def install(harness: Harness, image: str, tree: Path, commit: str, dependencies: Path, evidence: Path) -> dict:
    """The revision's own dependencies, installed once with registry access into a fresh directory; the receipt
    binds them to this image, commit and lockfile. Raises when setup fails."""
    dependencies.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    code = harness.setup(image, tree, dependencies.resolve(), evidence)
    if code != 0:
        raise RuntimeError(f"dependency setup for {commit} exited {code}; see {evidence}")
    write_setup(dependencies, dict(harness.setup_identity(image, tree, commit), exit=0))
    return require_setup(dependencies, harness.setup_identity(image, tree, commit))


class DockerRunners:
    """Operator runners: each call is a fresh offline container of its revision's tree and installed dependencies,
    the framework row's runner adapter on top. Development and baseline runs use the baseline revision."""

    def __init__(self, harness: Harness, image: str, revisions: Mapping[str, tuple[Path, Path, str]], store,
                 timeout: int, evidence: Path, stack: ExitStack):
        self.harness, self.image, self.revisions, self.store = harness, image, revisions, store
        self.timeout, self.evidence, self.stack, self.calls = timeout, evidence, stack, 0

    def __call__(self, purpose):
        tree, dependencies, commit = self.revisions["candidate" if purpose == "candidate" else "baseline"]
        require_setup(dependencies, self.harness.setup_identity(self.image, tree, commit))
        self.calls += 1
        logs = self.evidence / f"{self.calls}-{purpose}"
        logs.mkdir(parents=True)
        case = self.stack.enter_context(self.harness.workspace(self.image, tree, dependencies, commit, self.timeout, logs))
        return self.harness.runner(case, case, self.store, self.harness.config)
