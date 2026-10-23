"""Docker implementation of the trusted sandbox port.

Native CLI helpers create hardened containers, replay builds, freeze source, run offline probes and reconcile
labelled resources. The application owns each container's lifecycle; no separate workspace abstraction is retained.
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
from typing import Literal

from pydantic_ai.workspaces import (
    WorkspaceError,
    WorkspaceUnavailableError,
)

from corsair.ports.sandbox import LABEL, RUN_LABEL, Exec, SandboxExists, SandboxSpec, sandbox_name

PROVIDER = "docker"
HARDENED = ("--cap-drop=ALL", "--security-opt=no-new-privileges")
CONTROL_TIMEOUT_S = 120.0
"""Bound on one docker control-plane call (create, inspect, cp, rm), never on a workload command."""


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
    """None keeps the image's build user; sealed probes are explicitly run as 1000:1000."""
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


def docker(
    *args: str, input: bytes | None = None, timeout: float | None = CONTROL_TIMEOUT_S
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["docker", *args], input=input, capture_output=True, timeout=timeout, check=False)


def image_id(reference: str, *, container: bool = False) -> str | None:
    """The local image id (``sha256:...``) of an image reference, or of the image a container was created from.
    None when Docker cannot say: provenance stays unknown rather than failing the caller."""
    args = (
        ("inspect", "--format", "{{.Image}}", reference)
        if container
        else ("image", "inspect", "--format", "{{.Id}}", reference)
    )
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
        raise WorkspaceError(
            f"docker inspect {name} failed: {result.stderr.decode(errors='replace')[-2000:]}"
        )
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
        raise WorkspaceError(
            f"cannot read the container user: {result.stderr.decode(errors='replace')[-2000:]}"
        )
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


def copy_tree_in(
    name: str, source: Path, destination: str, uid: int, gid: int, timeout: float | None = 1800
) -> None:
    """Copy a host directory's contents into an existing container directory, owned by ``uid:gid``.

    Symlinks are copied as links, never followed, so a link in the tree cannot pull host files in.
    """
    source = Path(source)
    if not source.is_dir():
        raise FileNotFoundError(source)

    def owned(entry: tarfile.TarInfo) -> tarfile.TarInfo:
        entry.uid, entry.gid, entry.uname, entry.gname = uid, gid, "", ""
        return entry

    process = subprocess.Popen(
        ["docker", "cp", "-a", "-", f"{name}:{destination}"], stdin=PIPE, stdout=DEVNULL, stderr=PIPE
    )
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
        raise WorkspaceError(
            f"copy into {name}:{destination} failed: {stderr.decode(errors='replace')[-2000:]}"
        )


def write_file(name: str, path: str, data: bytes) -> None:
    """Inject a root-owned read-only file at the trusted control-plane boundary."""
    script = (
        'parent=$(dirname "$1"); mkdir -p "$parent"; chmod u+w "$parent"; '
        'rm -f "$1"; cat > "$1"; chmod 444 "$1"; '
        'case "$parent" in /work/.corsair|/work/.corsair/*) chmod 555 "$parent";; esac'
    )
    result = docker(
        "exec", "--user", "0:0", "-i", "-w", "/", name, "sh", "-ec", script, "sh", path, input=data
    )
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


def exec_once(
    name: str,
    argv: Sequence[str],
    *,
    workdir: str,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    trusted: bool = False,
) -> Exec:
    """Run ``argv`` once, never retried. On timeout the docker client is killed; the caller removes the container,
    which kills whatever the command left running."""
    environment = [arg for key, value in (env or {}).items() for arg in ("-e", f"{key}={value}")]
    try:
        user = ["--user", "0:0"] if trusted else []
        result = subprocess.run(
            ["docker", "exec", *user, "-w", workdir, *environment, name, *argv],
            stdin=DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
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


# --- the trusted Sandboxes port ---------------------------------------------------------------------------------

ENV_LOG_LABEL = f"{LABEL}.env.log"
ENV_KEY_LABEL = f"{LABEL}.env.key"


class DockerSandboxes:
    """The ``Sandboxes`` port over the helpers above. An environment is a committed image labelled with its key and
    build-log digest; ``build`` network is the default bridge, removed before the baseline."""

    provider = PROVIDER
    workdir = "/work"

    def __init__(self, probe_user: str = "1000:1000") -> None:
        """``probe_user`` is the unprivileged uid:gid every probe runs as. Frozen source retains the root build
        owner's identity; /tmp is writable, while kernel support files remain root-owned/read-only."""
        identity = probe_user.split(":") if isinstance(probe_user, str) else []
        if len(identity) != 2 or not all(part.isdigit() for part in identity) or int(identity[0]) == 0:
            raise ValueError("probe_user must be a non-root numeric uid:gid")
        self.probe_user = probe_user
        self._owners: dict[str, tuple[int, int]] = {}  # uid, gid read once per created container

    @property
    def cache_identity(self) -> str:
        return f"docker:cap-drop=ALL:no-new-privileges:probe={self.probe_user}"

    @staticmethod
    def _config(spec: SandboxSpec) -> DockerConfig:
        return DockerConfig(
            image=spec.image,
            labels=spec.labels,
            workdir=spec.workdir,
            network="bridge" if spec.network == "build" else "none",
        )

    def create(self, spec: SandboxSpec) -> str:
        name = create(self._config(spec), adopt=False)
        self._owners[name] = uid, gid = owner(name)
        make_workdir(name, spec.workdir, uid, gid)
        return name

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        uid, gid = self._owners.get(name) or owner(name)
        copy_tree_in(name, source, destination, uid, gid)

    def write_file(self, name: str, path: str, data: bytes) -> None:
        write_file(name, path, data)

    def source_unchanged(self, name: str, source: Path) -> bool:
        from corsair.domain.case import tree_manifest

        support = exec_once(
            name,
            [
                "sh",
                "-c",
                "test ! -L /work/.corsair && { test ! -e /work/.corsair || test -d /work/.corsair; }",
            ],
            workdir="/",
            trusted=True,
            timeout=30,
        )
        if support.exit_code != 0:
            return False
        expected = tree_manifest(source, directories=True)
        manifest = f"/work/.corsair/source-{uuid.uuid4().hex}.json"
        write_file(name, manifest, json.dumps(expected).encode())
        code = (
            "import hashlib,json,os,stat,sys; from pathlib import Path; "
            "root=Path('/work'); expected=json.loads(Path(sys.argv[1]).read_text()); "
            "actual=[]\n"
            "for relative,_,_ in expected:\n"
            " p=root/relative; s=p.lstat(); mode=s.st_mode\n"
            " if stat.S_ISLNK(mode): kind,data='120000',os.readlink(p).encode()\n"
            " elif stat.S_ISREG(mode): kind,data=('100755' if mode & 0o111 else '100644'),p.read_bytes()\n"
            " elif stat.S_ISDIR(mode): kind,data='040000',b''\n"
            " else: raise ValueError('unsupported original source type')\n"
            " actual.append([relative,kind,hashlib.sha256(data).hexdigest()])\n"
            "assert actual==expected, 'original source changed'\n"
        )
        result = exec_once(name, ["python", "-c", code, manifest], workdir="/", trusted=True, timeout=120)
        return result.exit_code == 0

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        return copy_out(name, paths)

    def exec_once(
        self,
        name: str,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        trusted: bool = False,
    ) -> Exec:
        return exec_once(name, argv, workdir=workdir, env=env, timeout=timeout, trusted=trusted)

    def drop_network(self, name: str) -> None:
        detached = docker("network", "disconnect", "--force", "bridge", name)
        if detached.returncode != 0:
            raise WorkspaceError(detached.stderr.decode(errors="replace"))

    def image_id(self, name: str) -> str | None:
        return image_id(name, container=True)

    def resolve_image(self, reference: str) -> str | None:
        return image_id(reference)

    def remove(self, name: str) -> bool:
        self._owners.pop(name, None)
        return remove(name)

    def labelled(self, run_id: str | None = None) -> list[str]:
        filters = ["--filter", f"label={LABEL}=1"] + (
            ["--filter", f"label={RUN_LABEL}={run_id}"] if run_id else []
        )
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

    def seal_environment(
        self,
        name: str,
        tag: str,
        key: str,
        log_sha256: str,
        writable: Sequence[str] = (),
        *,
        image_defaults: Sequence[str] = (),
    ) -> None:
        # Probes use a different, unprivileged uid. Source and kernel support stay builder-owned/read-only;
        # results go to /tmp. The probe cannot reopen files because it is not the source owner.
        if owner(name)[0] == int(self.probe_user.split(":")[0]):
            raise WorkspaceError(
                "build owner and probe uid must differ; otherwise a probe could reopen frozen source"
            )
        frozen = exec_once(name, ["chmod", "-R", "a-w", "/work"], workdir="/", timeout=120)
        if frozen.exit_code != 0:
            raise WorkspaceError(
                f"cannot freeze compiled source: {frozen.stderr.decode(errors='replace')[-500:]}"
            )
        for path in writable:
            # The root remains owner-writable until the kernel's reserved probe directory exists.
            opened = exec_once(name, ["chmod", "u+w", "/work"], workdir="/", timeout=120)
            if opened.exit_code != 0:
                raise WorkspaceError("cannot prepare the probe directory")
            made = exec_once(
                name,
                ["sh", "-c", 'test ! -L "$1" && mkdir -p "$1" && chmod 555 "$1"', "sh", path],
                workdir="/",
                timeout=120,
            )
            if made.exit_code != 0:
                raise WorkspaceError(
                    f"cannot prepare writable {path}: {made.stderr.decode(errors='replace')[-500:]}"
                )
        closed = exec_once(name, ["chmod", "a-w", "/work"], workdir="/", timeout=120)
        if closed.exit_code != 0:
            raise WorkspaceError("cannot freeze the source root")
        committed = docker(
            "commit",
            "--change",
            f"LABEL {ENV_KEY_LABEL}={key} {ENV_LOG_LABEL}={log_sha256}",
            *(argument for change in image_defaults for argument in ("--change", change)),
            name,
            tag,
            timeout=1800,
        )
        if committed.returncode != 0:
            raise WorkspaceError(f"docker commit failed: {committed.stderr.decode(errors='replace')[-1000:]}")

    def open_environment(self, image: str, workdir: str, sandbox_labels: Mapping[str, str]) -> str:
        name = create(
            DockerConfig(
                image=image, workdir=workdir, network="none", labels=sandbox_labels, user=self.probe_user
            ),
            adopt=False,
        )
        self._owners[name] = owner(name)
        return name

    def workspace_state(self, name: str) -> dict[str, tuple[str, str]] | None:
        """Bounded size/mtime inventory for observability, not security evidence or a content digest."""
        script = (
            "find /work -type d \\( -name .git -o -name node_modules -o -name .venv \\) -prune -o "
            "-type f -printf '%P\\0%s\\0%T@\\0' | head -c 1048576"
        )
        result = self.exec_once(name, ["sh", "-c", script], workdir="/", timeout=30)
        if result.exit_code != 0 or len(result.stdout) >= 1048576:
            return None
        parts = result.stdout.decode(errors="replace").split("\0")[:-1]
        if len(parts) % 3:
            return None
        return {parts[i]: (parts[i + 1], parts[i + 2]) for i in range(0, len(parts), 3)}
