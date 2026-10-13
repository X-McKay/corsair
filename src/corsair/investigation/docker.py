"""The image-only route's ports for an investigation, driven by the framework table: one generic dependency setup,
the environment stage's setup sandbox and the offline revision runners. Stand-ins for the OpenShell ports until
SPEC-0026 dependency provisioning reaches the sandbox; image evidence, not sandbox qualification.
"""
from contextlib import ExitStack
import os
from pathlib import Path
from typing import Literal, Mapping

from corsair.adapters.docker_image import (HARDENED, WORK, DockerCase, docker, require_setup, sha256, user,
                                           write_setup)
from corsair.agents.environment.contracts import Toolchain
from corsair.composition.direct import PreparedSandbox

from .frameworks import Harness

SCRATCH = "/tmp/corsair-scratch"
DEPENDENCIES = "/dependencies"
OVERLAY = "/overlay"


def write_overlay(files, tree: Path, destination: Path) -> Path:
    """SPEC-0071 operator files (smoke tests) into a fresh host directory mounted read-only beside the tree; a path
    the commit already has is refused before any container starts."""
    destination.mkdir(parents=True, exist_ok=False)
    for item in files:
        if (tree / item.path).exists() or (tree / item.path).is_symlink():
            raise ValueError(f"overlay path {item.path} is already in the commit")
        target = destination / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
    return destination


def registry_access(names: tuple[str, ...]) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Network, environment and read-only mounts for registry access during setup: the host's network only when the
    host itself reaches the registry through the variables `names` (a proxy, its CA file), else the bridge."""
    env = tuple(f"{name}={os.environ[name]}" for name in names if os.environ.get(name))
    files = tuple((value, value) for name in names if (value := os.environ.get(name, "")).startswith("/")
                  and Path(value).is_file())
    return ("host" if env else "bridge"), env, files


def setup_identity(harness: Harness, image: str, tree: Path, commit: str) -> dict:
    """What a dependency directory was installed for: the commit, the image and the lockfiles it installed."""
    return {"commit": commit, "image": image, "lockfiles": {f: sha256(tree / f) for f in harness.lockfiles}}


def install(harness: Harness, image: str, tree: Path, commit: str, dependencies: Path, evidence: Path,
            timeout: int = 1800) -> dict:
    """The revision's own dependencies, installed once with registry access by the framework's setup step into a
    fresh directory; the receipt binds them to this image, commit and lockfiles. Raises when setup fails."""
    dependencies.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    network, env, mounts = registry_access(harness.registry_env)
    script = (f"cp -R /src {WORK}; cd {WORK}; {harness.setup_script}; "
              f"cp -R {WORK}/{harness.dependencies} {DEPENDENCIES}/")
    result = docker("run", "--rm", f"--network={network}", *HARDENED, "--user", user(), "-e", "HOME=/tmp",
                    *(arg for pair in env for arg in ("-e", pair)),
                    *(arg for host, target in mounts for arg in ("-v", f"{host}:{target}:ro")),
                    "-v", f"{tree}:/src:ro", "-v", f"{dependencies.resolve()}:{DEPENDENCIES}", image,
                    "/bin/sh", "-ec", script, timeout=timeout)
    (evidence / "setup.stdout").write_bytes(result.stdout)
    (evidence / "setup.stderr").write_bytes(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"dependency setup for {commit} exited {result.returncode}; see {evidence}")
    write_setup(dependencies, dict(setup_identity(harness, image, tree, commit), exit=0))
    return require_setup(dependencies, setup_identity(harness, image, tree, commit))


def workspace(harness: Harness, image: str, tree: Path, dependencies: Path, commit: str, timeout: int,
              evidence: Path | None = None, overlay: Path | None = None) -> DockerCase:
    """The offline container of one revision: a fresh copy of its tree, the environment stage's overlay and the
    dependencies setup installed."""
    mounts = ((dependencies, DEPENDENCIES),) + (((overlay, OVERLAY),) if overlay else ())
    return DockerCase(image, tree, commit, timeout, kind="investigation-run", docker=docker, evidence=evidence,
                      mounts=mounts, env=("HOME=/tmp",),
                      copies=(f"cp -R {OVERLAY}/. {WORK}/; " if overlay else "")
                      + f"cp -R {DEPENDENCIES}/{harness.dependencies} {WORK}/;")


class DockerPreparation:
    """The environment stage's sandbox: the selected row's local image with the vulnerable tree copied to the
    workspace and registry access, released (container removed, removal confirmed) after the stage."""

    def __init__(self, images: Mapping[str, str], tree: Path, commit: str, harness: Harness, timeout: int,
                 overlays: Path):
        self.images, self.tree, self.commit, self.harness, self.timeout = images, tree, commit, harness, timeout
        self.overlays, self.overlay = overlays, None  # The overlay the environment stage saw, for the runners

    def prepare(self, toolchain: Toolchain, operation, *, overlay=()) -> PreparedSandbox:
        network, env, mounts = registry_access(self.harness.registry_env)
        if overlay:
            self.overlay = write_overlay(overlay, self.tree, self.overlays / str(operation))
            mounts = (*mounts, (str(self.overlay), OVERLAY))
        sandbox = DockerCase(self.images[toolchain.toolchain_id], self.tree, self.commit, self.timeout,
                             kind="investigation-environment", docker=docker, mounts=mounts, env=("HOME=/tmp", *env),
                             network=network)
        sandbox.__enter__()
        copy_overlay = f"cp -R {OVERLAY}/. {WORK}/; " if overlay else ""
        copied = docker("exec", sandbox.container, "/bin/sh", "-ec", f"cp -R /src {WORK}; {copy_overlay}mkdir -p {SCRATCH}")
        if copied.returncode != 0:
            sandbox.__exit__(None, None, None)
            raise RuntimeError(f"environment sandbox workspace copy failed: {copied.stderr[-512:]!r}")
        return PreparedSandbox(sandbox, sandbox.handle(operation), SCRATCH)

    def release(self, sandbox: PreparedSandbox, operation) -> Literal["confirmed", "unconfirmed"]:
        sandbox.execution.__exit__(None, None, None)
        return sandbox.execution.cleanup


class DockerRunners:
    """Operator runners: each call is a fresh offline container of its revision's tree and installed dependencies,
    the framework's runner adapter on top. Development and baseline runs use the vulnerable revision."""

    def __init__(self, harness: Harness, image: str, revisions: Mapping[str, tuple[Path, Path, str]], store,
                 timeout: int, evidence: Path, stack: ExitStack, preparation: "DockerPreparation | None" = None):
        self.harness, self.image, self.revisions, self.store = harness, image, revisions, store
        self.preparation = preparation
        self.timeout, self.evidence, self.stack, self.calls = timeout, evidence, stack, 0

    def __call__(self, purpose):
        tree, dependencies, commit = self.revisions["candidate" if purpose == "candidate" else "baseline"]
        require_setup(dependencies, setup_identity(self.harness, self.image, tree, commit))
        self.calls += 1
        logs = self.evidence / f"{self.calls}-{purpose}"
        logs.mkdir(parents=True)
        case = self.stack.enter_context(workspace(self.harness, self.image, tree, dependencies, commit, self.timeout, logs,
                                                    self.preparation.overlay if self.preparation else None))
        return self.harness.runner(case, case, self.store, self.harness.config)
