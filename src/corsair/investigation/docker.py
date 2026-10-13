"""The image-only route's ports for an investigation, driven by the framework table: one generic dependency setup,
the environment stage's setup sandbox and the offline revision runners. Stand-ins for the OpenShell ports until
SPEC-0026 dependency provisioning reaches the sandbox; image evidence, not sandbox qualification.
"""
from contextlib import ExitStack
import os
import re
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


# Setup containers (dependency install, the environment stage's sandbox) run on Docker's default bridge, never the
# host's network: model-chosen setup commands must not reach the host's own services. The bridge has no egress
# policy, so the setup network is recorded as unenforced (SETUP_NETWORK).
SETUP_NETWORK = {"network": "bridge", "egress": "unenforced",
                 "note": "Docker default bridge: internet reachable, host network never used, no egress policy"}
CREDENTIALS = re.compile(r"://[^/@\s]*@")


def captured_file(tree: Path, path: str, overlay: Path | None = None) -> bytes | None:
    """A regular file of the operator's capture placed in the sandbox (the commit's tree, then any overlay), never
    read back from the sandbox; None when the capture has none. Paths stay inside the capture."""
    for root in (tree, overlay):
        if root is None:
            continue
        target = (root / path).resolve()
        if target.is_relative_to(root.resolve()) and target.is_file() and not (root / path).is_symlink():
            return target.read_bytes()
    return None


# Above this many files the listing is not handed over (a smoke baseline is then refused), never truncated.
MAX_CAPTURED_PATHS = 100_000


def captured_paths(tree: Path) -> tuple[str, ...] | None:
    """Every file of the commit's capture as the host wrote it (regular files and symlinks), relative to its root,
    sorted, no contents and no overlay; None above MAX_CAPTURED_PATHS, since the smoke rule reads it as complete."""
    paths = []
    for path in tree.rglob("*"):
        if path.is_symlink() or path.is_file():
            paths.append(path.relative_to(tree).as_posix())
            if len(paths) > MAX_CAPTURED_PATHS:
                return None
    return tuple(sorted(paths))


def registry_access(names: tuple[str, ...]) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Network, environment and read-only mounts for registry access during setup: always the bridge, with the
    operator's proxy and CA variables among `names` that are set. A value carrying credentials (`user:pass@`) is
    refused rather than passed into a container the model drives."""
    env = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            continue
        if CREDENTIALS.search(value):
            raise ValueError(f"{name} carries credentials; setup containers never receive them")
        env.append(f"{name}={value}")
    files = tuple((value, value) for name in names if (value := os.environ.get(name, "")).startswith("/")
                  and Path(value).is_file())
    return SETUP_NETWORK["network"], tuple(env), files


def setup_identity(harness: Harness, image: str, tree: Path, commit: str) -> dict:
    """What a dependency directory was installed for: the commit, the image and the lockfiles it installed."""
    return {"commit": commit, "image": image, "lockfiles": {f: sha256(tree / f) for f in harness.lockfiles}}


def install(harness: Harness, image: str, tree: Path, commit: str, dependencies: Path, evidence: Path,
            timeout: int = 1800) -> dict:
    """The revision's own dependencies, installed once with registry access by the framework's setup step into a
    fresh directory; the receipt binds them to this image, commit and lockfiles. Raises when setup fails."""
    dependencies.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    try:
        network, env, mounts = registry_access(harness.registry_env)
    except ValueError as error:
        raise RuntimeError(f"dependency setup refused: {error}") from error
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
        return PreparedSandbox(sandbox, sandbox.handle(operation), SCRATCH,
                               lambda path: captured_file(self.tree, path, self.overlay),
                               lambda: captured_paths(self.tree))

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
