"""An OpenShell backend for the sandbox port and the agents' PydanticAI workspace, over the pinned SDK and CLI.

The SDK (``openshell`` 0.1.3) creates, lists, waits on, deletes and executes in sandboxes; it has no file transfer
and no policy methods. So:

- **Policy.** The operator's ``none`` / ``build`` documents (``policies/openshell/v2``) are loaded once. The static
  part (filesystem, landlock, process) goes into the create spec so the sandbox never starts under an image default;
  the full document is then set with the pinned CLI (``policy set --wait``, sha256 of the binary checked before every
  call) and observed loaded on the original sandbox id, as the v1 policy gate qualified. ``drop_network`` sets
  ``none`` the same way.
- **Transfer.** Trees and files travel as tar / bytes over exec stdin, in bounded chunks, staged under ``/tmp`` and
  then extracted by the sandbox user. The archive is built here from ``lstat``, so a symlink is a link entry and is
  never followed; devices and fifos are refused. This keeps the data path on the SDK and keeps the symlink rule in
  code this module owns (the CLI upload's symlink handling was never qualified).
- **Exec.** Every command runs once, never retried. The gateway's synthetic exit 124 (its execution timeout, which
  does not prove the remote process stopped) is ``timed_out``; a lost, not-Ready or replaced sandbox, or a transport
  error after dispatch, is ``container_failed``. Callers remove the sandbox after either.
- **Identity.** Names and labels are made valid for OpenShell deterministically (``native_name``, ``label_value``).
  Each created sandbox's gateway id and image ref are recorded under ``state_dir``; ``remove`` refuses a sandbox
  whose id changed, deletes by name, waits for the original id and returns True only on an observed NOT_FOUND.
- **Environments.** OpenShell cannot snapshot, so ``seal_environment`` writes a manifest and ``open_environment``
  replays it into a fresh sandbox.

Nothing here is live-qualified: the module is tested offline against ``tests/v2/openshell_fake.py``. See
``tests/v2/test_workspace_openshell.py`` for the live tests and the gaps only a gateway can settle.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import posixpath
import re
import shlex
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import grpc
import yaml
from pydantic_ai.workspaces import (
    CommandResult,
    SupportsCommands,
    WorkspaceBackend,
    WorkspaceCommand,
    WorkspaceError,
    WorkspaceOutputLimitError,
    WorkspaceRef,
    WorkspaceTimeoutError,
    WorkspaceUnavailableError,
)
from pydantic_ai.workspaces.protocol import validate_timeout

from .port import LABEL, RUN_LABEL, Exec, SandboxExists, SandboxSpec

if TYPE_CHECKING:
    from ..contracts import Environment, Recipe

PROVIDER = "openshell"
CONTROL_TIMEOUT_S = 120.0
"""Bound on one SDK control call (create, get, list, delete) and on one CLI call."""
POLICY_WAIT_S = 120
EXEC_DEFAULT_TIMEOUT_S = 3600
"""``exec_once`` without a timeout is still bounded: the gateway gets this execution timeout."""
CONTROL_EXEC_S = 300
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
STDIN_CHUNK_BYTES = 1024 * 1024
"""One exec's stdin. gRPC's default message cap is 4 MiB and the gateway's own stdin buffer is unqualified
(exit 74 is its overflow), so larger payloads are staged in chunks."""
MAX_TRANSFER_BYTES = 512 * 1024 * 1024
RESOURCES = {"limits": {"cpu": "2", "memory": "4Gi"}}
"""Mirrors the Docker backend's 2 CPUs / 4 GiB, in the nested shape the v1 recovery gate used."""
WORKDIR = "/sandbox"
"""OpenShell's native workdir: the root ``include_workdir`` makes writable and the root v1 qualified transfers
into. The toolchain images run as uid 10001 and have no ``/work``, so trusted code works here instead."""
GATEWAY_TIMEOUT_EXIT = 124
STDIN_OVERFLOW_EXIT = 74
MISSING_EXIT = 3

POLICY_FIELDS = frozenset({"version", "landlock", "filesystem_policy", "process", "network_policies"})
_DIGEST_REF = re.compile(r"^docker\.io/library/[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$")
_ENDPOINT = re.compile(r"^[A-Za-z0-9.-]+:[0-9]{1,5}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
NAME_LIMIT = 19
"""OpenShell 0.1.3's gateway refuses longer sandbox names (``name exceeds maximum length (51 > 19)``, RIG0 live run)."""
_NAME = re.compile(r"^[a-z](?:[-a-z0-9]{0,17}[a-z0-9])?$")
_LABEL_VALUE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9._-]{0,61}[A-Za-z0-9])?)?$")
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
_LABEL_KEY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")

# Records the command's pid so a timeout or cancellation can kill its process group inside the sandbox.
_WRAPPER = 'echo $$ > "$1" 2>/dev/null; shift; exec "$@"'
_KILL = 'pid=$(cat "$1" 2>/dev/null) && { kill -9 "-$pid" || kill -9 "$pid"; } 2>/dev/null; rm -f "$1"'
_READ = f'if [ -f "$1" ] && [ ! -L "$1" ]; then exec cat -- "$1"; else exit {MISSING_EXIT}; fi'


# --- names, labels and policy documents (pure) --------------------------------------------------------------------


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def native_name(name: str) -> str:
    """A valid OpenShell sandbox name (a DNS label of at most ``NAME_LIMIT`` = 19 characters) for a port name.

    A name that is already valid maps to itself, so the mapping is idempotent and every method accepts either form.
    Any other name becomes ``cv2-`` plus the first 15 hex digits (60 bits) of its sha256: deterministic, so a retried
    create finds the same identity. Two port names collide with probability about n^2 / 2^61 for n live names
    (under 1e-6 below a million), and a collision can only surface as ``SandboxExists`` or a label mismatch, never
    as adopting another run's sandbox, because the full port name is also a label (``NAME_LABEL``)."""
    if _NAME.fullmatch(name):
        return name
    return f"cv2-{_digest(name)[:15]}"


def label_value(value: str) -> str:
    """A valid Kubernetes label value. Valid values are kept; others (case ids carry ``:`` ``#`` ``/``) become a slug
    plus a digest of the original, so distinct values stay distinct."""
    if _LABEL_VALUE.fullmatch(value):
        return value
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")[:50].strip("-._")
    return f"{slug}-{_digest(value)[:12]}" if slug else _digest(value)[:12]


NAME_LABEL = f"{LABEL}.name"
"""The full port name of a sandbox, sanitized like any label value (the native name is only its digest)."""


def native_labels(sandbox_labels: Mapping[str, str], name: str | None = None) -> dict[str, str]:
    found = {LABEL: "1"}
    for key, value in sandbox_labels.items():
        if not _LABEL_KEY.fullmatch(key):
            raise ValueError(f"not a valid label key: {key!r}")
        found[key] = label_value(value)
    if name is not None:
        found[NAME_LABEL] = label_value(name)
    return found


def check_policy(document: Any, kind: str) -> dict:
    """Refuse a document outside the qualified shape: unknown fields, landlock not a hard requirement, a ``none``
    document with any network grant, or a grant that is not enforced, names a wildcard host or a non-443 port."""
    if not isinstance(document, dict) or not set(document) <= POLICY_FIELDS:
        raise ValueError(f"{kind} policy has fields outside {sorted(POLICY_FIELDS)}")
    if (document.get("landlock") or {}).get("compatibility") != "hard_requirement":
        raise ValueError(f"{kind} policy must make landlock a hard requirement")
    filesystem = document.get("filesystem_policy")
    if not isinstance(filesystem, dict) or not isinstance(filesystem.get("read_write"), list):
        raise ValueError(f"{kind} policy needs a filesystem_policy with read_write paths")
    if filesystem.get("include_workdir") is not True:
        raise ValueError(f"{kind} policy must include the sandbox workdir ({WORKDIR}), as v1 qualified")
    network = document.get("network_policies") or {}
    if not isinstance(network, dict):
        raise ValueError(f"{kind} policy network_policies must be a mapping")
    if kind == "none" and network:
        raise ValueError("the none policy must grant no network")
    for rule_name, rule in network.items():
        if not isinstance(rule, dict) or not isinstance(rule.get("endpoints"), list) or not rule["endpoints"]:
            raise ValueError(f"{kind} policy rule {rule_name!r} must be a mapping with endpoints")
        for endpoint in rule["endpoints"]:
            if not isinstance(endpoint, dict):
                raise ValueError(f"{kind} policy rule {rule_name!r} has an endpoint that is not a mapping")
            host = endpoint.get("host")
            if (not isinstance(host, str) or not _HOST.fullmatch(host) or endpoint.get("port") != 443
                    or endpoint.get("protocol") != "rest" or endpoint.get("enforcement") != "enforce"):
                raise ValueError(f"{kind} policy endpoint {host!r} must be an exact host on 443, rest, enforced")
            rules = endpoint.get("rules")
            if not isinstance(rules, list) or not rules or not all(
                    isinstance(item, dict) and set(item) == {"allow"} and isinstance(item["allow"], dict)
                    and item["allow"].get("method") == "GET" for item in rules):
                raise ValueError(f"{kind} policy endpoint {host!r} must allow GET only")
    return document


def _empty(value: Any) -> bool:
    return value is None or value == {} or value == [] or value == ""


def loads_requested(native: Mapping, requested: Mapping) -> bool:
    """Whether the gateway's effective policy is the requested document: every field the document sets is equal, an
    absent ``network_policies`` is empty, and the gateway adds nothing but its own ``process`` defaults (v1 gate).
    A field the document does not set may appear only empty (the readback may print ``network_middlewares: {}``);
    a non-empty one, known to the pinned ``SandboxPolicy`` or not, is authority nobody requested."""
    for key, value in native.items():
        if key not in requested and key not in ("process", "network_policies") and not _empty(value):
            return False
    expected = {"network_policies": {}} | dict(requested)
    return all(native.get(key, {} if key == "network_policies" else None) == value
               for key, value in expected.items())


def _covered(path: str, roots: Sequence[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def _writable(path: str, document: Mapping) -> bool:
    """Whether the policy lets the command user write ``path``: a ``read_write`` root, or the native workdir that
    ``include_workdir`` grants."""
    filesystem = document["filesystem_policy"]
    return _covered(path, filesystem["read_write"]) or bool(
        filesystem.get("include_workdir") and _covered(path, [WORKDIR]))


# --- operator configuration ---------------------------------------------------------------------------------------


def _absolute(value: Any, what: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/") or posixpath.normpath(value) != value:
        raise ValueError(f"{what} must be an absolute, normalized path")
    return Path(value)


def _exact_keys(value: Any, keys: set[str], what: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{what} must have exactly the keys {sorted(keys)}")
    return value


@dataclass(frozen=True)
class OpenShellConfig:
    """The operator's OpenShell configuration (``CORSAIR_OPENSHELL_CONFIG``), validated strictly. Policies and the
    image map are read once here; an image without a digest-pinned mapping is an error, never a fallback."""

    endpoint: str
    ca: Path
    cert: Path
    key: Path
    workspace: str
    gateway: str
    cli_path: Path
    cli_sha256: str
    cli_env: Mapping[str, str]
    images: Mapping[str, str]
    policies: Mapping[str, dict]
    state_dir: Path
    ready_seconds: int
    delete_seconds: int

    @classmethod
    def from_json(cls, path: Path) -> OpenShellConfig:
        raw = _exact_keys(json.loads(Path(path).read_text()),
                          {"endpoint", "ca", "cert", "key", "workspace", "gateway", "cli", "cli_env", "images",
                           "policies", "state_dir", "limits"}, "the OpenShell config")
        if not isinstance(raw["endpoint"], str) or not _ENDPOINT.fullmatch(raw["endpoint"]):
            raise ValueError("endpoint must be host:port")
        for field in ("workspace", "gateway"):
            if not isinstance(raw[field], str) or not raw[field]:
                raise ValueError(f"{field} must be a non-empty string")
        cli = _exact_keys(raw["cli"], {"path", "sha256"}, "cli")
        if not isinstance(cli["sha256"], str) or not _SHA256.fullmatch(cli["sha256"]):
            raise ValueError("cli.sha256 must be 64 lowercase hex characters")
        env = raw["cli_env"]
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise ValueError("cli_env must map strings to strings")
        images = json.loads(_absolute(raw["images"], "images").read_text())
        if not isinstance(images, dict) or not images or not all(
                isinstance(tag, str) and tag and isinstance(ref, str) and _DIGEST_REF.fullmatch(ref)
                for tag, ref in images.items()):
            raise ValueError("images must map image tags to docker.io/library/<repo>@sha256:<digest>")
        policies = _exact_keys(raw["policies"], {"none", "build"}, "policies")
        loaded = {kind: check_policy(yaml.safe_load(_absolute(policies[kind], f"policies.{kind}").read_text()), kind)
                  for kind in ("none", "build")}
        for kind in ("version", "filesystem_policy", "landlock", "process"):
            if loaded["none"].get(kind) != loaded["build"].get(kind):
                raise ValueError(f"the none and build policies must agree on {kind}; only network may differ")
        limits = _exact_keys(raw["limits"], {"ready_seconds", "delete_seconds"}, "limits")
        for field, value in limits.items():
            if type(value) is not int or not 1 <= value <= 3600:
                raise ValueError(f"limits.{field} must be an integer between 1 and 3600")
        return cls(endpoint=raw["endpoint"], ca=_absolute(raw["ca"], "ca"), cert=_absolute(raw["cert"], "cert"),
                   key=_absolute(raw["key"], "key"), workspace=raw["workspace"], gateway=raw["gateway"],
                   cli_path=_absolute(cli["path"], "cli.path"), cli_sha256=cli["sha256"], cli_env=dict(env),
                   images=dict(images), policies=loaded, state_dir=_absolute(raw["state_dir"], "state_dir"),
                   ready_seconds=limits["ready_seconds"], delete_seconds=limits["delete_seconds"])


# --- the SDK seam ---------------------------------------------------------------------------------------------------


CliRunner = Callable[[list[str], Mapping[str, str], float], "subprocess.CompletedProcess[bytes]"]


def run_cli(argv: list[str], env: Mapping[str, str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, capture_output=True, env=dict(env), timeout=timeout, check=False)


def _code(error: BaseException) -> grpc.StatusCode | None:
    if not isinstance(error, grpc.RpcError):
        return None
    code = getattr(error, "code", None)
    return code() if callable(code) else None


def _detail(error: BaseException) -> str:
    code = _code(error)
    return f"{type(error).__name__}{f' {code.name}' if code else ''}: {error}"[-2000:]


@dataclass
class _Ran:
    """One exec's raw observation. ``exit_code`` None means no exit event was observed (``error`` says why)."""

    exit_code: int | None
    stdout: bytearray
    stderr: bytearray
    error: BaseException | None = None
    overflowed: bool = False
    elapsed: float = 0.0


_INSTANCES: dict[tuple[Path, int], OpenShellSandboxes] = {}
_INSTANCES_LOCK = threading.Lock()


class OpenShellSandboxes:
    """The ``Sandboxes`` port over the OpenShell SDK and the pinned CLI. ``client`` is a ``SandboxClient`` (or the
    offline double); ``cli`` runs one CLI argv; ``clock`` is monotonic seconds. Building it does no gateway I/O."""

    provider = PROVIDER
    workdir = WORKDIR

    def __init__(self, config: OpenShellConfig, client: Any, *, cli: CliRunner = run_cli,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.client = client
        self._cli_runner = cli
        self._clock = clock
        self._workspace = config.workspace
        self._cli_verified: tuple[str, int, int] | None = None

    @classmethod
    def from_config(cls, path: Path) -> OpenShellSandboxes:
        """One instance (one gRPC channel) per resolved config path and its mtime per process, so a rewritten config
        (``make openshell-config`` after a new port-forward) is read again."""
        from openshell import SandboxClient, TlsConfig

        resolved = Path(path).resolve()
        key = (resolved, resolved.stat().st_mtime_ns)
        with _INSTANCES_LOCK:
            if key not in _INSTANCES:
                config = OpenShellConfig.from_json(resolved)
                client = SandboxClient(config.endpoint, tls=TlsConfig(ca_path=config.ca, cert_path=config.cert,
                                                                      key_path=config.key), timeout=CONTROL_TIMEOUT_S)
                _INSTANCES[key] = cls(config, client)
            return _INSTANCES[key]

    # --- state records ---

    def _record_path(self, name: str) -> Path:
        return self.config.state_dir / "sandboxes" / f"{name}.json"

    def _write_json(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        with os.fdopen(handle, "w") as stream:
            json.dump(value, stream, sort_keys=True)
        os.replace(temporary, path)

    def _record(self, name: str) -> dict | None:
        try:
            return json.loads(self._record_path(name).read_text())
        except FileNotFoundError:
            return None

    # --- native helpers ---

    def _get(self, name: str):
        return self.client.get(name, workspace=self._workspace)

    def _ready_ref(self, name: str):
        """The sandbox as the gateway sees it, refused unless it is ours, the recorded id and Ready."""
        from openshell._proto import openshell_pb2

        native = self._get(name)
        record = self._record(name)
        if native.labels.get(LABEL) != "1" or (record is not None and record["id"] != native.id):
            raise WorkspaceError(f"sandbox {name} is not the one this backend created")
        if native.status.phase != openshell_pb2.SANDBOX_PHASE_READY:
            raise WorkspaceUnavailableError(f"sandbox {name} is not Ready (phase {native.status.phase})")
        return native

    def _image_ref(self, image: str) -> str:
        ref = self.config.images.get(image)
        if ref is None:
            raise WorkspaceError(f"image {image!r} has no digest-pinned mapping in the operator's images map")
        return ref

    def _native_spec(self, image_ref: str, network: str):
        from openshell._proto import openshell_pb2, sandbox_pb2

        document = self.config.policies[network]
        policy = sandbox_pb2.SandboxPolicy(
            version=int(document.get("version", 1)),
            filesystem=sandbox_pb2.FilesystemPolicy(**document["filesystem_policy"]),
            landlock=sandbox_pb2.LandlockPolicy(**document["landlock"]))
        if document.get("process"):
            policy.process.CopyFrom(sandbox_pb2.ProcessPolicy(**document["process"]))
        spec = openshell_pb2.SandboxSpec(template=openshell_pb2.SandboxTemplate(image=image_ref), policy=policy,
                                         restart_policy=openshell_pb2.SANDBOX_RESTART_POLICY_NEVER)
        spec.template.resources.update(RESOURCES)
        return spec

    # --- the pinned CLI ---

    def _cli(self, *args: str) -> bytes:
        binary = self.config.cli_path
        info = binary.stat()
        identity = (str(binary), info.st_mtime_ns, info.st_size)
        if self._cli_verified != identity:  # Re-hashed whenever the file's path, mtime or size changes.
            self._cli_verified = None
            if hashlib.sha256(binary.read_bytes()).hexdigest() != self.config.cli_sha256:
                raise WorkspaceError(f"the OpenShell CLI at {binary} differs from its pinned sha256")
            self._cli_verified = identity
        argv = [str(binary), "--gateway", self.config.gateway, "--workspace", self._workspace, *args]
        try:
            done = self._cli_runner(argv, self.config.cli_env, CONTROL_TIMEOUT_S + POLICY_WAIT_S)
        except subprocess.TimeoutExpired as error:
            raise WorkspaceError(f"openshell {' '.join(args[:2])} timed out; its effect is unknown") from error
        if done.returncode != 0:
            raise WorkspaceError(f"openshell {' '.join(args[:2])} exited {done.returncode}: "
                                 f"{done.stderr.decode(errors='replace')[-2000:]}")
        return done.stdout

    def _apply_policy(self, name: str, kind: str, sandbox_id: str) -> None:
        """Set the operator document with ``--wait`` and observe that exact document loaded on ``sandbox_id``."""
        document = self.config.policies[kind]
        with tempfile.TemporaryDirectory(prefix="corsair-policy-") as scratch:
            path = Path(scratch) / f"{kind}.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=True))
            self._cli("policy", "set", name, "--policy", str(path), "--wait", "--timeout", str(POLICY_WAIT_S))
        actual = json.loads(self._cli("sandbox", "get", name, "-o", "json"))
        full = json.loads(self._cli("policy", "get", name, "--full", "-o", "json"))
        revision = json.loads(self._cli("policy", "get", name, "--rev", str(full["version"]), "--full", "-o",
                                        "json"))
        admission = actual.get("configuration_admission") or {}
        if (actual.get("id") != sandbox_id or actual.get("policy_source") != "sandbox"
                or admission.get("state") != "accepted" or full.get("hash") != admission.get("policy_hash")
                or revision.get("status") != "loaded" or revision.get("hash") != full.get("hash")):
            raise WorkspaceError(f"the {kind} policy was not observed loaded on sandbox {name} ({sandbox_id})")
        if not (loads_requested(actual.get("policy") or {}, document)
                and loads_requested(full.get("policy") or {}, document)):
            raise WorkspaceError(f"the policy loaded on sandbox {name} differs from the operator's {kind} document")

    # --- exec ---

    def _stream(self, name: str, argv: Sequence[str], *, workdir: str, env: Mapping[str, str] | None = None,
                stdin: bytes | None = None, timeout: float, stop_on_overflow: bool = False,
                into: _Ran | None = None) -> _Ran:
        """Dispatch once and collect bytes up to ``MAX_OUTPUT_BYTES``. Beyond it, either stop consuming (the remote
        process is then not proven stopped) or keep draining and discard."""
        from openshell import ExecChunk, ExecResult

        ran = into or _Ran(None, bytearray(), bytearray())
        started = self._clock()
        try:
            stream = self.client.exec_stream(name, list(argv), workspace=self._workspace, workdir=workdir,
                                             env=dict(env or {}), stdin=stdin,
                                             timeout_seconds=max(1, math.ceil(timeout)), no_login_shell=True)
            for item in stream:
                if isinstance(item, ExecChunk):
                    buffer = ran.stdout if item.stream == "stdout" else ran.stderr
                    room = MAX_OUTPUT_BYTES - len(ran.stdout) - len(ran.stderr)
                    buffer.extend(item.data[:max(0, room)])
                    if len(item.data) > room:
                        ran.overflowed = True
                        if stop_on_overflow:
                            close = getattr(stream, "close", None)
                            if close:
                                close()
                            break
                elif isinstance(item, ExecResult):
                    ran.exit_code = item.exit_code
        except Exception as error:  # Transport, gateway or SDK failure after dispatch: delivery is uncertain.
            ran.error = error
        ran.elapsed = self._clock() - started
        return ran

    def _gateway_timed_out(self, ran: _Ran, timeout: float) -> bool:
        """Exit 124 is the gateway's timeout only once the execution timeout has actually elapsed; a program's own
        124 before that is its exit code."""
        return ran.exit_code == GATEWAY_TIMEOUT_EXIT and ran.elapsed >= max(1, math.ceil(timeout)) - 1

    def _control(self, name: str, argv: Sequence[str], *, what: str, stdin: bytes | None = None,
                 workdir: str = "/") -> bytes:
        """A trusted helper command that must succeed; anything else raises naming ``what``."""
        ran = self._stream(name, argv, workdir=workdir, stdin=stdin, timeout=CONTROL_EXEC_S)
        if ran.error is not None:
            raise WorkspaceError(f"{what}: {_detail(ran.error)}") from ran.error
        if ran.exit_code != 0 or ran.overflowed:
            hint = " (the gateway's stdin overflow)" if ran.exit_code == STDIN_OVERFLOW_EXIT and stdin else ""
            raise WorkspaceError(f"{what}: exit {ran.exit_code}{hint}: {ran.stderr.decode(errors='replace')[-2000:]}")
        return bytes(ran.stdout)

    def _push(self, name: str, data: bytes, *, what: str) -> str:
        """Stage ``data`` in the sandbox under ``/tmp`` in chunks; returns the staging directory."""
        if len(data) > MAX_TRANSFER_BYTES:
            raise WorkspaceError(f"{what}: {len(data)} bytes exceeds the {MAX_TRANSFER_BYTES}-byte transfer bound")
        staging = f"/tmp/.corsair-in-{uuid.uuid4().hex}"
        self._control(name, ["sh", "-c", 'umask 077 && mkdir "$1"', "sh", staging], what=f"{what}: staging")
        for index in range(0, max(1, len(data)), STDIN_CHUNK_BYTES):
            self._control(name, ["sh", "-c", 'cat > "$1"', "sh", f"{staging}/{index // STDIN_CHUNK_BYTES:06d}"],
                          stdin=data[index:index + STDIN_CHUNK_BYTES], what=f"{what}: chunk {index}")
        return staging

    # --- the port -----------------------------------------------------------------------------------------------

    def _create_native(self, spec: SandboxSpec) -> tuple[str, str]:
        """Create the sandbox and record its gateway id; returns (name, id). No setup that can fail happens here,
        so a caller can hold the identity before preparing it."""
        if not _writable(spec.workdir, self.config.policies[spec.network]):
            raise WorkspaceError(f"workdir {spec.workdir} is not writable under the operator's {spec.network} policy")
        image_ref = self._image_ref(spec.image)
        name, wanted = native_name(spec.name), native_labels(spec.labels, spec.name)
        try:
            native = self.client.create(workspace=self._workspace, name=name, labels=wanted,
                                        spec=self._native_spec(image_ref, spec.network))
        except grpc.RpcError as error:
            if _code(error) == grpc.StatusCode.ALREADY_EXISTS:
                raise SandboxExists(f"sandbox {name} already exists") from error
            raise WorkspaceError(f"create {name} failed; the sandbox may exist: {_detail(error)}") from error
        if native.name != name or any(native.labels.get(key) != value for key, value in wanted.items()):
            raise WorkspaceError(f"the gateway created {native.name!r} with labels that differ from the request")
        self._write_json(self._record_path(name), {"id": native.id, "image": image_ref, "labels": wanted,
                                                   "network": spec.network, "workdir": spec.workdir})
        return name, native.id

    def _prepare(self, name: str, sandbox_id: str, spec: SandboxSpec) -> None:
        from openshell._proto import openshell_pb2

        try:
            ready = self.client.wait_ready(name, workspace=self._workspace, timeout_seconds=self.config.ready_seconds)
        except Exception as error:
            raise WorkspaceError(f"sandbox {name} did not become Ready: {_detail(error)}") from error
        if ready.id != sandbox_id or ready.status.phase != openshell_pb2.SANDBOX_PHASE_READY:
            raise WorkspaceError(f"sandbox {name} is not the Ready original (phase {ready.status.phase})")
        self._apply_policy(name, spec.network, sandbox_id)
        self._control(name, ["sh", "-c", 'mkdir -p "$1" && test -d "$1" && test -w "$1"', "sh", spec.workdir],
                      what=f"create workdir {spec.workdir}")

    def create(self, spec: SandboxSpec) -> str:
        name, sandbox_id = self._create_native(spec)
        self._prepare(name, sandbox_id, spec)
        return spec.name

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        name = native_name(name)
        source = Path(source)
        if not source.is_dir():
            raise FileNotFoundError(source)
        self._ready_ref(name)
        archive, total = io.BytesIO(), 0
        with tarfile.open(fileobj=archive, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for directory, dirnames, filenames in os.walk(source, followlinks=False):
                dirnames.sort()
                for entry in sorted(dirnames + filenames):
                    path = Path(directory) / entry
                    info = path.lstat()
                    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                        raise WorkspaceError(f"refusing to copy {path}: not a file, directory or symlink")
                    total += info.st_size if stat.S_ISREG(info.st_mode) else 0
                    if total > MAX_TRANSFER_BYTES:  # Checked before reading: a file over the bound is never read.
                        raise WorkspaceError(f"{source} exceeds the {MAX_TRANSFER_BYTES}-byte transfer bound")
                    member = tar.gettarinfo(str(path), arcname=path.relative_to(source).as_posix())
                    member.uid = member.gid = 0
                    member.uname = member.gname = ""
                    if member.isreg():
                        with path.open("rb") as stream:
                            tar.addfile(member, stream)
                    else:
                        tar.addfile(member)
                    if archive.tell() > MAX_TRANSFER_BYTES:
                        raise WorkspaceError(f"{source} exceeds the {MAX_TRANSFER_BYTES}-byte transfer bound")
        staging = self._push(name, archive.getvalue(), what=f"copy {source} into {destination}")
        self._control(name, ["sh", "-c", 'cat "$1"/* | tar -x -f - -C "$2" --no-same-owner && rm -rf "$1"', "sh",
                             staging, destination], what=f"extract into {destination}")

    def write_file(self, name: str, path: str, data: bytes) -> None:
        name = native_name(name)
        self._ready_ref(name)
        write = 'mkdir -p "$(dirname "$1")" && cat > "$1"'
        if len(data) <= STDIN_CHUNK_BYTES:
            self._control(name, ["sh", "-c", write, "sh", path], stdin=data, what=f"write {path}")
            return
        staging = self._push(name, data, what=f"write {path}")
        self._control(name, ["sh", "-c", 'mkdir -p "$(dirname "$2")" && cat "$1"/* > "$2" && rm -rf "$1"', "sh",
                             staging, path], what=f"write {path}")

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        name = native_name(name)
        self._ready_ref(name)
        found: dict[str, bytes | None] = {}
        for path in paths:
            ran = self._stream(name, ["sh", "-c", _READ, "sh", path], workdir="/", timeout=CONTROL_EXEC_S)
            if ran.error is not None or ran.overflowed or ran.exit_code not in (0, MISSING_EXIT):
                raise WorkspaceError(f"cannot read {path}: exit {ran.exit_code}"
                                     f"{' (over the output cap)' if ran.overflowed else ''}"
                                     f"{': ' + _detail(ran.error) if ran.error else ''}")
            found[path] = bytes(ran.stdout) if ran.exit_code == 0 else None
        return found

    def exec_once(self, name: str, argv: Sequence[str], *, workdir: str, env: Mapping[str, str] | None = None,
                  timeout: float | None = None) -> Exec:
        name = native_name(name)
        limit = EXEC_DEFAULT_TIMEOUT_S if timeout is None else timeout
        try:
            self._ready_ref(name)
        except Exception as error:  # Not dispatched: the sandbox is gone, not Ready, replaced or unreachable.
            return Exec(None, b"", f"[sandbox unavailable before dispatch: {_detail(error)}]".encode(),
                        container_failed=True)
        ran = self._stream(name, argv, workdir=workdir, env=env, timeout=limit)
        stdout, stderr = bytes(ran.stdout), bytes(ran.stderr)
        if ran.overflowed:
            stderr += f"\n[output truncated at {MAX_OUTPUT_BYTES} bytes]\n".encode()
        if ran.error is not None:
            if _code(ran.error) == grpc.StatusCode.DEADLINE_EXCEEDED:
                return Exec(None, stdout, stderr, timed_out=True)
            return Exec(None, stdout, stderr + f"\n[{_detail(ran.error)}]\n".encode(), container_failed=True)
        if self._gateway_timed_out(ran, limit):
            return Exec(None, stdout, stderr, timed_out=True)
        if ran.exit_code != 0:
            try:
                self._ready_ref(name)
            except Exception as error:
                return Exec(None, stdout, stderr + f"\n[{_detail(error)}]\n".encode(), container_failed=True)
        return Exec(ran.exit_code, stdout, stderr)

    def drop_network(self, name: str) -> None:
        name = native_name(name)
        self._apply_policy(name, "none", self._ready_ref(name).id)
        record = self._record(name)
        if record is not None:
            self._write_json(self._record_path(name), record | {"network": "none"})

    def image_id(self, name: str) -> str | None:
        """The digest ref recorded at create, while the gateway still holds that sandbox id. The pinned SDK does not
        expose the effective image, so the CLI's view is compared where it reports one."""
        name = native_name(name)
        try:
            record = self._record(name)
            if record is None or self._get(name).id != record["id"]:
                return None
            shown = json.loads(self._cli("sandbox", "get", name, "-o", "json"))
            image = ((shown.get("spec") or {}).get("template") or {}).get("image")
            return record["image"] if image in (None, "", record["image"]) else None
        except Exception:
            return None

    def resolve_image(self, reference: str) -> str | None:
        """The digest ref an image tag maps to (what a sandbox would be created from). A sealed environment tag
        resolves to the base image ref its manifest pinned, since every probe sandbox is created from that. None when
        neither is known; never raises."""
        try:
            found = self.config.images.get(reference)
            if found is None:
                manifest = self._manifest(reference)
                found = manifest.get("base_image_ref") if manifest is not None else None
            return found
        except Exception:
            return None

    def remove(self, name: str) -> bool:
        from openshell import DeletionOutcome

        name = native_name(name)
        try:
            try:
                native = self._get(name)
            except grpc.RpcError as error:
                if _code(error) == grpc.StatusCode.NOT_FOUND:
                    self._record_path(name).unlink(missing_ok=True)
                    return True
                return False
            record = self._record(name)
            if native.labels.get(LABEL) != "1" or (record is not None and record["id"] != native.id):
                return False  # Never delete a sandbox that replaced ours or that this backend did not label.
            deleted = self.client.delete(name, workspace=self._workspace)
            if deleted.sandbox_id not in (None, native.id) or deleted.outcome not in (
                    DeletionOutcome.ACCEPTED, DeletionOutcome.COMPLETED, DeletionOutcome.ALREADY_ABSENT):
                return False
            self.client.wait_deleted(name, workspace=self._workspace, timeout_seconds=self.config.delete_seconds,
                                     expected_sandbox_id=native.id)
            try:
                self._get(name)
            except grpc.RpcError as error:
                if _code(error) == grpc.StatusCode.NOT_FOUND:
                    self._record_path(name).unlink(missing_ok=True)
                    return True
            return False
        except Exception:
            return False

    def labelled(self, run_id: str | None = None) -> list[str]:
        selector = f"{LABEL}=1" + (f",{RUN_LABEL}={label_value(run_id)}" if run_id else "")
        try:
            found = self.client.list_all(workspace=self._workspace, label_selector=selector)
        except grpc.RpcError as error:
            raise RuntimeError(f"cannot list sandboxes: {_detail(error)}") from error
        return sorted(item.name for item in found)

    # --- environments: a sealed manifest, replayed into each fresh sandbox ---

    def _manifest_path(self, tag: str) -> Path:
        return self.config.state_dir / "environments" / f"{_digest(tag)[:32]}.json"

    def _manifest(self, tag: str) -> dict | None:
        try:
            found = json.loads(self._manifest_path(tag).read_text())
        except FileNotFoundError:
            return None
        return found if found.get("tag") == tag else None

    def find_environment(self, tag: str, key: str) -> str | None:
        """None also when the sealed tree is gone or no longer hashes to what was sealed: every open would fail,
        so replay should rebuild instead."""
        from ..intake import tree_sha256

        found = self._manifest(tag)
        if found is None or found.get("key") != key:
            return None
        tree = Path(found.get("tree_source", ""))
        try:
            if not tree.is_dir() or tree_sha256(tree) != found.get("tree_sha256"):
                return None
        except (OSError, ValueError):
            return None
        return found.get("log_sha256", "")

    def seal_environment(self, name: str, tag: str, key: str, log_sha256: str, *, recipe: Recipe,
                         tree_source: Path, base_image: str, setup_timeout: float | None = None,
                         baseline_timeout: float | None = None) -> None:
        from ..build import BASELINE_TIMEOUT_S, SETUP_TIMEOUT_S
        from ..intake import tree_sha256

        base_ref = self._image_ref(base_image)
        recipe_json = recipe.model_dump(mode="json")
        self._write_json(self._manifest_path(tag), {
            "tag": tag, "key": key, "log_sha256": log_sha256, "recipe": recipe_json,
            "recipe_sha256": hashlib.sha256(json.dumps(recipe_json, sort_keys=True).encode()).hexdigest(),
            "tree_source": str(Path(tree_source).resolve()), "tree_sha256": tree_sha256(Path(tree_source)),
            "base_image": base_image, "base_image_ref": base_ref,
            "setup_timeout": SETUP_TIMEOUT_S if setup_timeout is None else setup_timeout,
            "baseline_timeout": BASELINE_TIMEOUT_S if baseline_timeout is None else baseline_timeout})

    def open_environment(self, environment: Environment, sandbox_labels: Mapping[str, str]) -> str:
        from ..contracts import Recipe
        from ..intake import tree_sha256

        manifest = self._manifest(environment.image)
        if manifest is None:
            raise WorkspaceError(f"no sealed environment {environment.image}")
        recipe = Recipe.model_validate(manifest["recipe"])
        if manifest["recipe_sha256"] != environment.recipe_sha256:
            raise WorkspaceError(f"sealed environment {environment.image} holds a different recipe")
        tree = Path(manifest["tree_source"])
        if manifest["tree_sha256"] != tree_sha256(tree) or manifest["tree_sha256"] != environment.tree_sha256:
            raise WorkspaceError(f"the tree of sealed environment {environment.image} changed since it was sealed")
        if self.resolve_image(manifest["base_image"]) != manifest["base_image_ref"]:
            raise WorkspaceError(f"base image {manifest['base_image']} no longer resolves to the sealed "
                                 f"{manifest['base_image_ref']}")
        spec = SandboxSpec(image=manifest["base_image"], labels=sandbox_labels, workdir=environment.workdir,
                           network="build" if recipe.network_during_setup else "none")
        step = "create"
        name, sandbox_id = self._create_native(spec)  # SandboxExists propagates: never remove another attempt's.
        log: list[bytes] = []

        def run(argv: Sequence[str], timeout: float) -> None:
            result = self.exec_once(name, argv, workdir=environment.workdir, timeout=timeout)
            status = ("timed out" if result.timed_out else "sandbox failed" if result.container_failed
                      else f"exit {result.exit_code}")
            log.append(f"$ {shlex.join(argv)}\n".encode() + result.stdout + result.stderr
                       + f"\n[{status}]\n".encode())
            if result.exit_code != 0:
                raise WorkspaceError(f"{status}: {result.stderr.decode(errors='replace')[-1000:]}")

        try:
            self._prepare(name, sandbox_id, spec)
            step = "copy tree"
            self.copy_tree_in(name, tree, environment.workdir)
            for added in recipe.files:
                step = f"write recipe file {added.path}"
                self.write_file(name, posixpath.join(environment.workdir, added.path), added.content.encode())
            for index, argv in enumerate(recipe.setup, 1):
                step = f"setup step {index}"
                run(argv, float(manifest["setup_timeout"]))
            step = "drop network"
            if spec.network == "build":
                self.drop_network(name)
            step = "baseline test"
            run(recipe.baseline_test, float(manifest["baseline_timeout"]))
        except Exception as error:
            digest = self._write_open_log(name, log)
            removed = self.remove(name)
            raise WorkspaceError(f"open_environment {environment.image} failed at {step}: {error} "
                                 f"(open log sha256 {digest}){'' if removed else ' (cleanup unconfirmed)'}"
                                 ) from error
        self._write_open_log(name, log)
        return spec.name

    def _write_open_log(self, name: str, log: list[bytes]) -> str:
        """Keep this open's replay log under ``state_dir/environments/opens``; returns its sha256."""
        data = b"".join(log)
        path = self.config.state_dir / "environments" / "opens" / f"{name}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def agent_workspace(self, image: str, sandbox_labels: Mapping[str, str]) -> OpenShellWorkspace:
        return OpenShellWorkspace(self, SandboxSpec(image=image, labels=sandbox_labels, network="build",
                                                    workdir=self.workdir))


# --- the native WorkspaceBackend ----------------------------------------------------------------------------------


class OpenShellWorkspace(WorkspaceBackend, SupportsCommands):
    """A PydanticAI workspace backed by one OpenShell sandbox, mirroring ``DockerWorkspace``.

    Built without I/O. The first operation creates the sandbox (adopting one that already holds this identity with
    the same labels, so a retried create after an uncertain first attempt finds it) or, given a ref, attaches and
    raises ``WorkspaceUnavailableError`` if it is gone. The ref is recorded as soon as the create returns. Nothing
    here removes the sandbox except ``destroy()``.
    """

    def __init__(self, sandboxes: OpenShellSandboxes, spec: SandboxSpec, ref: WorkspaceRef | None = None):
        if ref is not None and ref.provider != PROVIDER:
            raise ValueError(f"not an openshell workspace ref: {ref!r}")
        self.sandboxes = sandboxes
        self.spec = spec
        self._ref = ref
        self._ready = False
        self._attached = ref is not None
        self._id: str | None = None
        self._lock = anyio.Lock()

    @property
    def ref(self) -> WorkspaceRef | None:
        return self._ref

    @property
    def name(self) -> str:
        return self._ref.id if self._ref is not None else native_name(self.spec.name)

    def _gone(self) -> bool:
        try:
            self.sandboxes._ready_ref(self.name)
        except WorkspaceUnavailableError:
            return True
        except grpc.RpcError as error:
            return _code(error) == grpc.StatusCode.NOT_FOUND
        return False

    def _create_or_adopt(self) -> tuple[str, str]:
        try:
            return self.sandboxes._create_native(self.spec)
        except SandboxExists:
            name = native_name(self.spec.name)
            native = self.sandboxes._get(name)
            wanted = native_labels(self.spec.labels, self.spec.name)
            record = self.sandboxes._record(name)
            if any(native.labels.get(key) != value for key, value in wanted.items()) or (
                    record is not None and record["id"] != native.id):
                raise
            return name, native.id

    async def _ensure(self) -> str:
        if self._ready:
            return self.name
        async with self._lock:
            if self._ready:
                return self.name
            if self._attached:
                if await anyio.to_thread.run_sync(self._gone):
                    raise WorkspaceUnavailableError(f"sandbox {self.name} is gone")
            else:
                if self._ref is None:
                    # Shielded so a cancelled caller still records the ref of the sandbox it created.
                    with anyio.CancelScope(shield=True):
                        name, self._id = await anyio.to_thread.run_sync(self._create_or_adopt)
                        self._ref = WorkspaceRef(provider=PROVIDER, id=name)
                await anyio.to_thread.run_sync(self.sandboxes._prepare, self.name, self._id, self.spec)
            self._ready = True
        return self.name

    async def working_dir(self) -> str:
        await self._ensure()
        return self.spec.workdir

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
        pidfile = f"/tmp/.corsair-exec-{uuid.uuid4().hex}"
        limit = EXEC_DEFAULT_TIMEOUT_S if timeout is None else timeout
        ran = _Ran(None, bytearray(), bytearray())

        def dispatch() -> _Ran:
            return self.sandboxes._stream(name, ["sh", "-c", _WRAPPER, "sh", pidfile, *argv],
                                          workdir=self.spec.workdir, env=env, timeout=limit, stop_on_overflow=True,
                                          into=ran)

        def text(buffer: bytearray) -> str:
            return bytes(buffer).decode(errors="replace")

        try:
            with anyio.fail_after(limit + 15):
                await anyio.to_thread.run_sync(dispatch, abandon_on_cancel=True)
        except BaseException as error:
            with anyio.CancelScope(shield=True):
                await self._kill(name, pidfile)
            if isinstance(error, TimeoutError):
                raise WorkspaceTimeoutError(f"command timed out after {limit:g}s and was killed",
                                            stdout=text(ran.stdout), stderr=text(ran.stderr)) from error
            raise
        if ran.overflowed:
            await self._kill(name, pidfile)
            raise WorkspaceOutputLimitError("command output exceeded its cap", limit=MAX_OUTPUT_BYTES,
                                            stdout=text(ran.stdout), stderr=text(ran.stderr))
        if ran.error is not None:
            if _code(ran.error) == grpc.StatusCode.DEADLINE_EXCEEDED:
                await self._kill(name, pidfile)
                raise WorkspaceTimeoutError(f"command passed its {limit:g}s deadline and was killed",
                                            stdout=text(ran.stdout), stderr=text(ran.stderr)) from ran.error
            if await anyio.to_thread.run_sync(self._gone):
                raise WorkspaceUnavailableError(f"sandbox {name} is gone") from ran.error
            raise WorkspaceError(f"command delivery uncertain: {_detail(ran.error)}") from ran.error
        if self.sandboxes._gateway_timed_out(ran, limit):
            await self._kill(name, pidfile)
            raise WorkspaceTimeoutError(f"command timed out after {limit:g}s", stdout=text(ran.stdout),
                                        stderr=text(ran.stderr))
        assert ran.exit_code is not None
        if ran.exit_code != 0 and await anyio.to_thread.run_sync(self._gone):
            raise WorkspaceUnavailableError(f"sandbox {name} is gone")
        return CommandResult(exit_code=ran.exit_code, stdout=text(ran.stdout), stderr=text(ran.stderr))

    async def _kill(self, name: str, pidfile: str) -> None:
        """Best effort: kill the command's process group in the sandbox. Not proof that it stopped."""
        with anyio.move_on_after(30):
            await anyio.to_thread.run_sync(
                lambda: self.sandboxes._stream(name, ["sh", "-c", _KILL, "sh", pidfile], workdir="/", timeout=30),
                abandon_on_cancel=True)

    # --- owner operations, outside the protocol ---

    async def copy_in(self, source: Path, destination: str | None = None) -> None:
        """Copy a host directory tree into the workspace (by default into the working directory)."""
        name = await self._ensure()
        await anyio.to_thread.run_sync(self.sandboxes.copy_tree_in, name, source, destination or self.spec.workdir)

    async def copy_out(self, paths: Sequence[str]) -> dict[str, bytes | None]:
        """Read declared files out of the workspace; missing paths map to None."""
        name = await self._ensure()
        return await anyio.to_thread.run_sync(self.sandboxes.copy_out, name, list(paths))

    async def destroy(self) -> bool:
        """Remove the sandbox. Returns whether its absence was confirmed (False is ``cleanup_unconfirmed``)."""
        return await anyio.to_thread.run_sync(self.sandboxes.remove, self.name)
