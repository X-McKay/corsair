"""A Docker workspace: the native PydanticAI ``WorkspaceBackend`` over the docker CLI, plus the small synchronous
container helpers trusted code (build replay, probe execution, the reconciler) uses directly.

One long-lived container per workspace, created on first use with a deterministic name derived from its labels,
every capability dropped, no new privileges, no network unless configured, and CPU, memory and PID limits. The
backend never removes its container when a run ends; the owner calls ``destroy()`` (or the reconciler sweeps it).
File operations use PydanticAI's shell fallback, so commands and files always see one filesystem.
"""
from __future__ import annotations

import io
import json
import posixpath
import subprocess
import tarfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import DEVNULL, PIPE
from typing import TYPE_CHECKING, Literal

import anyio
import anyio.abc
from pydantic_ai.workspaces import (CommandResult, SupportsCommands, WorkspaceBackend, WorkspaceCommand,
                                    WorkspaceError, WorkspaceOutputLimitError, WorkspaceRef, WorkspaceTimeoutError,
                                    WorkspaceUnavailableError)
from pydantic_ai.workspaces.protocol import validate_timeout

from .port import LABEL, RUN_LABEL, Exec, SandboxExists, SandboxSpec, labels, sandbox_name

if TYPE_CHECKING:
    from ..contracts import Environment, Recipe

PROVIDER = "docker"
HARDENED = ("--cap-drop=ALL", "--security-opt=no-new-privileges")
CONTROL_TIMEOUT_S = 120.0
"""Bound on one docker control-plane call (create, inspect, cp, rm), never on a workload command."""
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
DRAIN_GRACE_S = 5.0

# Records the command's pid (a session leader under docker exec) so a timeout or cancellation can kill its whole
# process group inside the container; killing the docker client alone leaves the process running.
_WRAPPER = 'echo $$ > "$1" 2>/dev/null; shift; exec "$@"'


@dataclass(frozen=True)
class DockerConfig:
    """Everything needed to create one container, as data. Building it does no I/O."""

    image: str
    labels: Mapping[str, str] = field(default_factory=dict)
    network: Literal["none", "bridge"] = "none"
    cpus: float | None = 2.0
    memory: str | None = "4g"
    pids: int | None = 1024
    workdir: str = "/work"
    user: str | None = None
    """None keeps the image's own user (the corsair-* toolchain images run as 10001:10001)."""
    env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.network not in ("none", "bridge"):
            raise ValueError("network must be 'none' or 'bridge'")
        if not self.workdir.startswith("/") or posixpath.normpath(self.workdir) != self.workdir:
            raise ValueError("workdir must be an absolute, normalized path")

    @property
    def name(self) -> str:
        """Deterministic: the same labels always name the same container, so a retried create finds it."""
        return sandbox_name(self.labels)


# --- synchronous helpers ----------------------------------------------------------------------------------------


def docker(*args: str, input: bytes | None = None, timeout: float | None = CONTROL_TIMEOUT_S
           ) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["docker", *args], input=input, capture_output=True, timeout=timeout, check=False)


def image_id(reference: str, *, container: bool = False) -> str | None:
    """The local image id (``sha256:...``) of an image reference, or of the image a container was created from.
    None when Docker cannot say: provenance stays unknown rather than failing the caller."""
    args = ("inspect", "--format", "{{.Image}}", reference) if container else (
        "image", "inspect", "--format", "{{.Id}}", reference)
    try:
        found = docker(*args, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = found.stdout.decode(errors="replace").strip()
    return value if found.returncode == 0 and value.startswith("sha256:") else None


def docker_available() -> bool:
    try:
        return docker("info", "--format", "{{.ServerVersion}}", timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_args(config: DockerConfig) -> list[str]:
    """The ``docker run`` argv for a long-lived, hardened container (``--init`` reaps exec'd processes)."""
    args = ["run", "-d", "--init", "--name", config.name, "--label", f"{LABEL}=1"]
    for key, value in sorted(config.labels.items()):
        args += ["--label", f"{key}={value}"]
    args += [f"--network={config.network}", *HARDENED]
    if config.cpus is not None:
        args.append(f"--cpus={config.cpus}")
    if config.memory is not None:
        args += [f"--memory={config.memory}", f"--memory-swap={config.memory}"]
    if config.pids is not None:
        args.append(f"--pids-limit={config.pids}")
    if config.user is not None:
        args += ["--user", config.user]
    return [*args, "--entrypoint", "sleep", config.image, "infinity"]


def running(name: str) -> bool:
    """Whether the container exists and runs. Any other answer (gone, stopped, dead) means unavailable."""
    result = docker("inspect", "--format", "{{.State.Running}}", name)
    if result.returncode != 0:
        if b"no such" in result.stderr.lower():
            return False
        raise WorkspaceError(f"docker inspect {name} failed: {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout.strip() == b"true"


def container_labels(name: str) -> dict[str, str] | None:
    result = docker("inspect", "--format", "{{json .Config.Labels}}", name)
    return (json.loads(result.stdout) or {}) if result.returncode == 0 else None


ContainerExists = SandboxExists
"""A container already holds this identity (the port's ``SandboxExists``)."""


def create(config: DockerConfig, *, adopt: bool = True) -> str:
    """Create and start the container. With ``adopt`` (the workspace backend), a container already holding this name
    is adopted only if its labels match, so a retried create after an uncertain first attempt finds the same
    identity instead of a second one. Trusted one-shot code passes ``adopt=False`` and gets ``ContainerExists``."""
    result = docker(*run_args(config))
    if result.returncode != 0:
        existing = container_labels(config.name)
        if existing is not None and not adopt:
            raise ContainerExists(f"container {config.name} already exists")
        expected = {LABEL: "1", **config.labels}
        if existing is None or any(existing.get(key) != value for key, value in expected.items()):
            raise WorkspaceError(f"docker run failed: {result.stderr.decode(errors='replace')[-2000:]}")
        if not running(config.name):
            raise WorkspaceUnavailableError(f"container {config.name} exists but is not running")
    return config.name


def owner(name: str) -> tuple[int, int]:
    """The uid and gid commands run as, so copied files belong to that user and stay writable."""
    result = docker("exec", "-w", "/", name, "sh", "-c", "id -u; id -g")
    if result.returncode != 0:
        raise WorkspaceError(f"cannot read the container user: {result.stderr.decode(errors='replace')[-2000:]}")
    uid, gid = result.stdout.split()
    return int(uid), int(gid)


def make_workdir(name: str, workdir: str, uid: int, gid: int) -> None:
    """Create ``workdir`` owned by the container user. ``docker cp`` runs in the daemon, so it needs no capability
    the hardened container lacks."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        entry = tarfile.TarInfo(workdir.strip("/"))
        entry.type, entry.mode, entry.uid, entry.gid = tarfile.DIRTYPE, 0o755, uid, gid
        archive.addfile(entry)
    result = docker("cp", "-a", "-", f"{name}:/", input=buffer.getvalue())
    if result.returncode != 0:
        raise WorkspaceError(f"cannot create {workdir}: {result.stderr.decode(errors='replace')[-2000:]}")


def copy_tree_in(name: str, source: Path, destination: str, uid: int, gid: int,
                 timeout: float | None = 1800) -> None:
    """Copy a host directory's contents into an existing container directory, owned by ``uid:gid``.

    Symlinks are copied as links, never followed, so a link in the tree cannot pull host files in.
    """
    source = Path(source)
    if not source.is_dir():
        raise FileNotFoundError(source)

    def owned(entry: tarfile.TarInfo) -> tarfile.TarInfo:
        entry.uid, entry.gid, entry.uname, entry.gname = uid, gid, "", ""
        return entry

    process = subprocess.Popen(["docker", "cp", "-a", "-", f"{name}:{destination}"], stdin=PIPE, stdout=DEVNULL,
                               stderr=PIPE)
    try:
        assert process.stdin is not None and process.stderr is not None
        with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
            for path in sorted(source.rglob("*")):
                archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False, filter=owned)
        process.stdin.close()
        process.wait(timeout=timeout)
        stderr = process.stderr.read()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if process.returncode != 0:
        raise WorkspaceError(f"copy into {name}:{destination} failed: {stderr.decode(errors='replace')[-2000:]}")


def write_file(name: str, path: str, data: bytes) -> None:
    """Write one file as the container user, creating its parents, so it stays theirs."""
    result = docker("exec", "-i", "-w", "/", name, "sh", "-c", 'mkdir -p "$(dirname "$1")" && cat > "$1"', "sh", path,
                    input=data)
    if result.returncode != 0:
        raise WorkspaceError(f"cannot write {path}: {result.stderr.decode(errors='replace')[-2000:]}")


def copy_out(name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
    """Read declared regular files out of the container; a missing or non-regular path maps to None."""
    found: dict[str, bytes | None] = {}
    for path in paths:
        result = docker("cp", f"{name}:{path}", "-")
        data = None
        if result.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
                member = archive.next()
                if member is not None and member.isfile():
                    extracted = archive.extractfile(member)
                    data = extracted.read() if extracted else None
        found[path] = data
    return found


def exec_once(name: str, argv: Sequence[str], *, workdir: str, env: Mapping[str, str] | None = None,
              timeout: float | None = None) -> Exec:
    """Run ``argv`` once, never retried. On timeout the docker client is killed; the caller removes the container,
    which kills whatever the command left running."""
    environment = [arg for key, value in (env or {}).items() for arg in ("-e", f"{key}={value}")]
    try:
        result = subprocess.run(["docker", "exec", "-w", workdir, *environment, name, *argv], stdin=DEVNULL,
                                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        return Exec(None, error.stdout or b"", error.stderr or b"", timed_out=True)
    if result.returncode != 0 and not running(name):
        return Exec(None, result.stdout, result.stderr, container_failed=True)
    return Exec(result.returncode, result.stdout, result.stderr)


def remove(name: str) -> bool:
    """Remove the container and confirm it is gone. False means cleanup is unconfirmed."""
    try:
        docker("rm", "--force", "--volumes", name)
        absent = docker("inspect", "--format", "{{.Id}}", name)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return absent.returncode != 0 and b"no such" in absent.stderr.lower()


# --- the native WorkspaceBackend --------------------------------------------------------------------------------


class DockerWorkspace(WorkspaceBackend, SupportsCommands):
    """A PydanticAI workspace backed by one long-lived Docker container.

    Built without I/O. The first operation creates the container (or, given a ref, attaches to it and raises
    ``WorkspaceUnavailableError`` if it is gone). The ref is the container name and is recorded as soon as the
    create returns. Nothing here removes the container except ``destroy()``.
    """

    def __init__(self, config: DockerConfig, ref: WorkspaceRef | None = None):
        if ref is not None and ref.provider != PROVIDER:
            raise ValueError(f"not a docker workspace ref: {ref!r}")
        self.config = config
        self._ref = ref
        self._ready = False
        self._attached = ref is not None
        self._lock = anyio.Lock()

    @property
    def ref(self) -> WorkspaceRef | None:
        return self._ref

    @property
    def name(self) -> str:
        return self._ref.id if self._ref is not None else self.config.name

    async def _ensure(self) -> str:
        if self._ready:
            return self.name
        async with self._lock:
            if self._ready:
                return self.name
            if self._attached:
                if not await anyio.to_thread.run_sync(running, self.name):
                    raise WorkspaceUnavailableError(f"container {self.name} is gone")
            else:
                if self._ref is None:
                    # Shielded so a cancelled caller still records the ref of the container it created.
                    with anyio.CancelScope(shield=True):
                        name = await anyio.to_thread.run_sync(create, self.config)
                        self._ref = WorkspaceRef(provider=PROVIDER, id=name)
                await anyio.to_thread.run_sync(self._prepare)
            self._ready = True
        return self.name

    def _prepare(self) -> None:
        if not running(self.name):
            raise WorkspaceUnavailableError(f"container {self.name} is gone")
        uid, gid = owner(self.name)
        make_workdir(self.name, self.config.workdir, uid, gid)

    async def working_dir(self) -> str:
        await self._ensure()
        return self.config.workdir

    async def run(self, command: WorkspaceCommand, *, shell: bool = False, env: Mapping[str, str] | None = None,
                  timeout: float | None = None) -> CommandResult:
        validate_timeout(timeout)
        if isinstance(command, str):
            if not shell:
                raise TypeError("a string command requires shell=True; pass an argv sequence otherwise")
            argv = ["sh", "-c", command]
        elif shell:
            raise TypeError("an argv sequence cannot be combined with shell=True; pass a single command string")
        else:
            argv = list(command)
        name = await self._ensure()
        deadline = None if timeout is None else anyio.current_time() + timeout
        pidfile = f"/tmp/.corsair-exec-{uuid.uuid4().hex}"
        merged = {**self.config.env, **(env or {})}
        environment = [arg for key, value in merged.items() for arg in ("-e", f"{key}={value}")]
        process = await anyio.open_process(
            ["docker", "exec", "-w", self.config.workdir, *environment, name, "sh", "-c", _WRAPPER, "sh", pidfile,
             *argv], stdin=DEVNULL, stdout=PIPE, stderr=PIPE)
        stdout, stderr = bytearray(), bytearray()
        try:
            exit_code = await self._collect(process, stdout, stderr, deadline)
        except BaseException as error:
            with anyio.CancelScope(shield=True):
                await self._kill(name, pidfile, process)
            if isinstance(error, TimeoutError):
                raise WorkspaceTimeoutError(f"command timed out after {timeout:g}s and was killed",
                                            stdout=stdout.decode(errors="replace"),
                                            stderr=stderr.decode(errors="replace")) from error
            raise
        await process.aclose()
        if exit_code != 0 and not await anyio.to_thread.run_sync(running, name):
            raise WorkspaceUnavailableError(f"container {name} is gone")
        return CommandResult(exit_code=exit_code, stdout=stdout.decode(errors="replace"),
                             stderr=stderr.decode(errors="replace"))

    @staticmethod
    async def _collect(process: anyio.abc.Process, stdout: bytearray, stderr: bytearray, deadline: float | None
                       ) -> int:
        assert process.stdout is not None and process.stderr is not None
        overflowed = False

        async def drain(stream: anyio.abc.ByteReceiveStream, buffer: bytearray) -> None:
            nonlocal overflowed
            async for chunk in stream:
                buffer.extend(chunk)
                if len(stdout) + len(stderr) > MAX_OUTPUT_BYTES:
                    overflowed = True
                    group.cancel_scope.cancel()

        with anyio.fail_after(None if deadline is None else max(0.0, deadline - anyio.current_time())):
            async with anyio.create_task_group() as group:
                group.start_soon(drain, process.stdout, stdout)
                group.start_soon(drain, process.stderr, stderr)
            if overflowed:
                raise WorkspaceOutputLimitError("command output exceeded its cap", limit=MAX_OUTPUT_BYTES,
                                                stdout=stdout.decode(errors="replace"),
                                                stderr=stderr.decode(errors="replace"))
            return await process.wait()

    @staticmethod
    async def _kill(name: str, pidfile: str, process: anyio.abc.Process) -> None:
        """Best effort: kill the command's process group in the container, then the local docker client."""
        script = 'pid=$(cat "$1" 2>/dev/null) && { kill -9 "-$pid" || kill -9 "$pid"; } 2>/dev/null; rm -f "$1"'
        with anyio.move_on_after(30):
            await anyio.to_thread.run_sync(lambda: docker("exec", "-w", "/", name, "sh", "-c", script, "sh", pidfile,
                                                          timeout=30))
        if process.returncode is None:
            process.kill()
        with anyio.move_on_after(DRAIN_GRACE_S):
            await process.wait()
        await process.aclose()

    # --- owner operations, outside the protocol ---

    async def copy_in(self, source: Path, destination: str | None = None) -> None:
        """Copy a host directory tree into the workspace (by default into the working directory)."""
        name = await self._ensure()
        uid, gid = await anyio.to_thread.run_sync(owner, name)
        await anyio.to_thread.run_sync(copy_tree_in, name, source, destination or self.config.workdir, uid, gid)

    async def copy_out(self, paths: Sequence[str]) -> dict[str, bytes | None]:
        """Read declared files out of the workspace; missing paths map to None."""
        name = await self._ensure()
        return await anyio.to_thread.run_sync(copy_out, name, list(paths))

    async def destroy(self) -> bool:
        """Remove the container. Returns whether its absence was confirmed (False is ``cleanup_unconfirmed``)."""
        return await anyio.to_thread.run_sync(remove, self.name)


# --- the trusted Sandboxes port ---------------------------------------------------------------------------------

ENV_LOG_LABEL = f"{LABEL}.env.log"
ENV_KEY_LABEL = f"{LABEL}.env.key"


class DockerSandboxes:
    """The ``Sandboxes`` port over the helpers above. An environment is a committed image labelled with its key and
    build-log digest; ``build`` network is the default bridge, removed before the baseline."""

    provider = PROVIDER

    @staticmethod
    def _config(spec: SandboxSpec) -> DockerConfig:
        return DockerConfig(image=spec.image, labels=spec.labels, workdir=spec.workdir,
                            network="bridge" if spec.network == "build" else "none")

    def create(self, spec: SandboxSpec) -> str:
        name = create(self._config(spec), adopt=False)
        uid, gid = owner(name)
        make_workdir(name, spec.workdir, uid, gid)
        return name

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        uid, gid = owner(name)
        copy_tree_in(name, source, destination, uid, gid)

    def write_file(self, name: str, path: str, data: bytes) -> None:
        write_file(name, path, data)

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        return copy_out(name, paths)

    def exec_once(self, name: str, argv: Sequence[str], *, workdir: str, env: Mapping[str, str] | None = None,
                  timeout: float | None = None) -> Exec:
        return exec_once(name, argv, workdir=workdir, env=env, timeout=timeout)

    def drop_network(self, name: str) -> None:
        detached = docker("network", "disconnect", "--force", "bridge", name)
        if detached.returncode != 0:
            raise WorkspaceError(detached.stderr.decode(errors="replace"))

    def image_id(self, name: str) -> str | None:
        return image_id(name, container=True)

    def remove(self, name: str) -> bool:
        return remove(name)

    def labelled(self, run_id: str | None = None) -> list[str]:
        filters = ["--filter", f"label={LABEL}=1"] + (["--filter", f"label={RUN_LABEL}={run_id}"] if run_id else [])
        listed = docker("ps", "--all", "--no-trunc", *filters, "--format", "{{.Names}}")
        if listed.returncode != 0:
            raise RuntimeError(f"cannot list containers: {listed.stderr.decode(errors='replace')[-2000:]}")
        return sorted(listed.stdout.decode().split())

    def find_environment(self, tag: str, key: str) -> str | None:
        cached = docker("image", "inspect", "--format", "{{json .Config.Labels}}", tag)
        if cached.returncode != 0:
            return None
        found = json.loads(cached.stdout) or {}
        return found.get(ENV_LOG_LABEL, "") if found.get(ENV_KEY_LABEL) == key else None

    def seal_environment(self, name: str, tag: str, key: str, log_sha256: str, *, recipe: Recipe,
                         tree_source: Path, base_image: str) -> None:
        committed = docker("commit", "--change", f"LABEL {ENV_KEY_LABEL}={key} {ENV_LOG_LABEL}={log_sha256}", name,
                           tag, timeout=1800)
        if committed.returncode != 0:
            raise WorkspaceError(f"docker commit failed: {committed.stderr.decode(errors='replace')[-1000:]}")

    def open_environment(self, environment: Environment, sandbox_labels: Mapping[str, str]) -> str:
        return create(DockerConfig(image=environment.image, workdir=environment.workdir, network="none",
                                   labels=sandbox_labels), adopt=False)

    def agent_workspace(self, image: str, sandbox_labels: Mapping[str, str]) -> DockerWorkspace:
        return DockerWorkspace(DockerConfig(image=image, labels=sandbox_labels, network="bridge"))
