"""OpenShell sandbox adapter for a locally configured Docker compute gateway.

Sandbox lifecycle and untrusted commands always use the public OpenShell SDK.  OpenShell
v0.1.5 deliberately has no snapshot or file APIs, so the narrow trusted control-plane
operations below address only the Docker *workload* container after validating its gateway
sandbox id and isolation-role label.  They never target a gateway or supervisor container.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import ipaddress
import json
import math
import os
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import grpc
import yaml
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct
from openshell import SandboxClient, TlsConfig
from openshell._proto import openshell_pb2, sandbox_pb2
from pydantic_ai.workspaces import WorkspaceError

from corsair.adapters.sandbox import docker as native
from corsair.ports.sandbox import LABEL, RUN_LABEL, Exec, SandboxExists, SandboxSpec

PROVIDER = "openshell"
WORKDIR = "/work"
PROBE_UID = 1000
BUILD_UID = 1001
PROBE_USER = f"{PROBE_UID}:{PROBE_UID}"
BUILD_USER = f"{BUILD_UID}:{BUILD_UID}"
_WORKLOAD_ID_LABEL = "openshell.ai/sandbox-id"
_WORKLOAD_ROLE_LABEL = "openshell.ai/isolation-role"
_WORKLOAD_ROLE = "sandbox"
_MAX_GATEWAY_NAME = 19
_RUNTIME_READ_ONLY = (
    "/usr",
    "/bin",
    "/lib",
    "/lib64",
    "/proc",
    "/dev/urandom",
    "/app",
    "/etc",
    "/opt",
    "/var/log",
)
_SANDBOX_READ_WRITE = (WORKDIR, "/tmp", "/dev/null")
_BUILD_ROOT = "/tmp/corsair-build"
_BUILD_DIRECTORIES = (
    "corsair-build/home",
    "corsair-build/python",
    "corsair-build/npm",
    "corsair-build/gradle",
    "corsair-build/maven",
    "corsair-build/m2",
    "corsair-build/gems",
    "corsair-build/bundle",
    "corsair-build/perl5/lib/perl5",
)
_BUILD_ENVIRONMENT = {
    "HOME": f"{_BUILD_ROOT}/home",
    "PIP_TARGET": f"{_BUILD_ROOT}/python",
    "PYTHONPATH": f"{_BUILD_ROOT}/python",
    "npm_config_cache": f"{_BUILD_ROOT}/npm",
    "npm_config_prefix": f"{_BUILD_ROOT}/npm",
    "GRADLE_USER_HOME": f"{_BUILD_ROOT}/gradle",
    "MAVEN_USER_HOME": f"{_BUILD_ROOT}/maven",
    "MAVEN_OPTS": f"-Dmaven.repo.local={_BUILD_ROOT}/m2",
    "GEM_HOME": f"{_BUILD_ROOT}/gems",
    "GEM_PATH": f"{_BUILD_ROOT}/gems:/usr/local/bundle",
    "BUNDLE_APP_CONFIG": f"{_BUILD_ROOT}/bundle/config",
    "BUNDLE_USER_CACHE": f"{_BUILD_ROOT}/bundle",
    "PERL_LOCAL_LIB_ROOT": f"{_BUILD_ROOT}/perl5",
    "PERL_MB_OPT": f"--install_base {_BUILD_ROOT}/perl5",
    "PERL_MM_OPT": f"INSTALL_BASE={_BUILD_ROOT}/perl5",
    "PERL5LIB": f"{_BUILD_ROOT}/perl5/lib/perl5",
}


class OpenShellSandboxes:
    """A fail-closed OpenShell adapter limited to the gateway's Docker driver.

    ``client`` is caller-owned.  Without one, each operation creates and closes an SDK
    client, so this adapter neither opens a gateway connection nor reads registration state
    in its constructor.  A build policy must be explicitly operator supplied; there is no
    registry or binary-identity auto-approval.
    """

    provider = PROVIDER
    workdir = WORKDIR

    def __init__(
        self,
        *,
        workspace: str = "default",
        endpoint: str | None = None,
        gateway: str | None = None,
        build_policy: Mapping[str, Any] | None = None,
        build_policy_path: Path | None = None,
        cpu: str = "2",
        memory: str = "4Gi",
        cli: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        ready_timeout: float = 300.0,
        delete_timeout: float = 60.0,
    ) -> None:
        if not workspace:
            raise ValueError("workspace must be non-empty")
        if build_policy is not None and build_policy_path is not None:
            raise ValueError("build_policy and build_policy_path are mutually exclusive")
        if endpoint is None and gateway is None:
            endpoint = os.environ.get("CORSAIR_OPENSHELL_GATEWAY_ENDPOINT")
        if endpoint is not None:
            self._endpoint, self._endpoint_url = self._validate_direct_endpoint(endpoint)
        else:
            self._endpoint = self._endpoint_url = None
        self.workspace = workspace
        self.gateway = gateway
        self.cpu, self.memory = cpu, memory
        self._cli = cli
        self._client = client
        self._client_factory = client_factory
        self._command_runner = command_runner
        self._ready_timeout = ready_timeout
        self._delete_timeout = delete_timeout
        self._build_policy = dict(build_policy) if build_policy is not None else None
        self._build_policy_path = Path(build_policy_path) if build_policy_path is not None else None
        self._reviewed_policy_document: dict[str, Any] | None = None
        self._policy_hash: str | None = None
        self._gateway_checked = False
        self._refs: dict[str, Any] = {}
        self._labels: dict[str, dict[str, str]] = {}
        self._users: dict[str, str] = {}
        self._workloads: dict[str, str] = {}
        self._prepared: set[str] = set()
        self._trusted_support: dict[str, set[str]] = {}
        self._native = native.DockerSandboxes(probe_user=PROBE_USER)

    @property
    def cache_identity(self) -> str:
        """Lazy cache binding for the provider, policy review, identity, and limits."""
        policy = self._reviewed_policy_hash() if self._build_policy_configured() else "unconfigured"
        return (
            f"openshell:docker:workspace={self.workspace}:probe={PROBE_USER}:build={BUILD_USER}:"
            f"cpu={self.cpu}:memory={self.memory}:workdir={WORKDIR}:"
            f"cap-drop=ALL:no-new-privileges:network=none:layout=2:build-policy={policy}"
        )

    @staticmethod
    def _is_loopback(endpoint: str) -> bool:
        if endpoint.startswith("unix:"):
            return True
        host = urlparse(f"//{endpoint}").hostname
        if host is None or host.lower() == "localhost":
            return host is not None
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    @classmethod
    def _validate_direct_endpoint(cls, raw: str) -> tuple[str, str]:
        parsed = urlparse(raw if "://" in raw or raw.startswith("unix:") else f"//{raw}")
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError("OpenShell endpoint must not contain userinfo, a query, or a fragment")
        if raw.startswith("unix:"):
            return raw, raw
        host = parsed.hostname
        if not host:
            raise ValueError("OpenShell endpoint must name a host")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        endpoint = f"{host}:{port}"
        if parsed.scheme not in ("", "http", "https"):
            raise ValueError("OpenShell endpoint must be http, https, or host:port")
        if parsed.scheme != "https" and not cls._is_loopback(endpoint):
            raise ValueError("plaintext OpenShell endpoint must be loopback or unix")
        return endpoint, raw if "://" in raw else f"http://{endpoint}"

    def _build_policy_configured(self) -> bool:
        return (
            self._build_policy is not None
            or self._build_policy_path is not None
            or bool(os.environ.get("CORSAIR_OPENSHELL_BUILD_POLICY"))
        )

    def _reviewed_policy(self) -> dict[str, Any]:
        if self._reviewed_policy_document is not None:
            return copy.deepcopy(self._reviewed_policy_document)
        if self._build_policy is not None:
            payload = self._build_policy
        else:
            path = self._build_policy_path or (
                Path(os.environ["CORSAIR_OPENSHELL_BUILD_POLICY"])
                if os.environ.get("CORSAIR_OPENSHELL_BUILD_POLICY")
                else None
            )
            if path is None:
                raise WorkspaceError(
                    "OpenShell build network requires CORSAIR_OPENSHELL_BUILD_POLICY or build_policy; "
                    "automatic registry approvals are forbidden"
                )
            try:
                payload = yaml.safe_load(path.read_text())
            except (OSError, yaml.YAMLError) as error:
                raise WorkspaceError(f"cannot read reviewed OpenShell build policy: {error}") from error
        if not isinstance(payload, Mapping):
            raise WorkspaceError("reviewed OpenShell build policy must be a mapping")
        document = copy.deepcopy(dict(payload))
        # The SDK protobuf calls this field ``filesystem``; the official CLI's
        # reviewed YAML grammar calls it ``filesystem_policy``.  Accept the
        # latter at this boundary but never guess at unknown aliases.
        if "filesystem_policy" in document:
            if "filesystem" in document:
                raise WorkspaceError("reviewed OpenShell build policy cannot contain both filesystem aliases")
            document["filesystem"] = document.pop("filesystem_policy")
        self._reviewed_policy_document = document
        return copy.deepcopy(document)

    def _reviewed_policy_hash(self) -> str:
        if self._policy_hash is None:
            payload = json_format.MessageToDict(
                self._policy(build=True, user=BUILD_USER), preserving_proto_field_name=True
            )
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            self._policy_hash = hashlib.sha256(encoded).hexdigest()
        return self._policy_hash

    @staticmethod
    def _network_policy_is_explicit(policy: Any) -> bool:
        if not policy.network_policies:
            return False
        return all(rule.endpoints and rule.binaries for rule in policy.network_policies.values())

    def _policy(self, *, build: bool, user: str) -> Any:
        policy = sandbox_pb2.SandboxPolicy(version=1)
        if build:
            json_format.ParseDict(self._reviewed_policy(), policy, ignore_unknown_fields=False)
            if not self._network_policy_is_explicit(policy):
                raise WorkspaceError(
                    "reviewed OpenShell build policy must name explicit endpoints and binary identities"
                )
        # The policy is authored in the SDK request.  A rejected identity is a hard error;
        # the adapter never falls back to an image user or weaker filesystem policy.
        uid, gid = user.split(":", 1)
        policy.filesystem.CopyFrom(
            sandbox_pb2.FilesystemPolicy(
                include_workdir=True, read_only=_RUNTIME_READ_ONLY, read_write=_SANDBOX_READ_WRITE
            )
        )
        policy.landlock.CopyFrom(sandbox_pb2.LandlockPolicy(compatibility="hard_requirement"))
        policy.process.CopyFrom(sandbox_pb2.ProcessPolicy(run_as_user=uid, run_as_group=gid))
        if not build:
            policy.ClearField("network_policies")
            policy.ClearField("network_middlewares")
        return policy

    @staticmethod
    def _gateway_name(logical_name: str) -> str:
        """Map Corsair's deterministic logical identity to Docker driver's 19-byte name space."""
        return "c-" + hashlib.sha256(logical_name.encode()).hexdigest()[: _MAX_GATEWAY_NAME - 2]

    def _spec(self, spec: SandboxSpec, *, user: str) -> Any:
        if spec.workdir != WORKDIR:
            raise WorkspaceError(f"OpenShell local Docker adapter requires workdir {WORKDIR}")
        labels = {LABEL: "1", **dict(spec.labels)}
        resources = Struct()
        resources.update({"limits": {"cpu": self.cpu, "memory": self.memory}})
        return openshell_pb2.SandboxSpec(
            template=openshell_pb2.SandboxTemplate(image=spec.image, labels=labels, resources=resources),
            policy=self._policy(build=spec.network == "build", user=user),
            command=["sleep", "infinity"],
        )

    @contextlib.contextmanager
    def _sdk(self) -> Iterator[Any]:
        if self._client is not None:
            yield self._client
            return
        if self._client_factory is not None:
            client = self._client_factory()
        elif self._endpoint is not None:
            client = SandboxClient(
                self._endpoint,
                tls=TlsConfig() if self._endpoint_url and self._endpoint_url.startswith("https://") else None,
            )
        else:
            self._assert_registered_transport()
            client = SandboxClient.from_active_cluster(
                cluster=self.gateway or os.environ.get("OPENSHELL_GATEWAY")
            )
        try:
            yield client
        finally:
            client.close()

    def _assert_registered_transport(self) -> None:
        # Verify registration before constructing an SDK client or invoking the CLI.  The
        # public SDK deliberately does not expose its resolved endpoint, so do not reach into
        # client internals (and do not accidentally close a caller-owned client on failure).
        cluster = self.gateway or os.environ.get("OPENSHELL_GATEWAY")
        if cluster is None:
            active = (
                Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
                / "openshell/active_gateway"
            )
            try:
                cluster = active.read_text().strip()
            except OSError as error:
                raise WorkspaceError("cannot verify registered OpenShell gateway transport") from error
        metadata = (
            Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            / "openshell/gateways"
            / cluster
            / "metadata.json"
        )
        try:
            registered = json.loads(metadata.read_text())["gateway_endpoint"]
            parsed = urlparse(registered)
            host = parsed.hostname
            if parsed.scheme not in ("http", "https") or not host:
                raise ValueError("invalid gateway endpoint")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WorkspaceError("cannot verify registered OpenShell gateway transport") from error
        if self._is_loopback(f"{host}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"):
            return
        if parsed.scheme != "https":
            raise WorkspaceError("remote OpenShell gateway must use TLS")

    def _cli_args(self) -> list[str]:
        args: list[str] = []
        if self.gateway:
            args += ["--gateway", self.gateway]
        elif self._endpoint_url:
            args += ["--gateway-endpoint", self._endpoint_url]
        args += ["--workspace", self.workspace]
        return args

    def _run_cli(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        binary = self._cli or os.environ.get("CORSAIR_OPENSHELL_CLI", "openshell")
        timeout = 30.0
        if "--wait" in args:
            try:
                timeout = float(args[args.index("--timeout") + 1]) + 30.0
            except (ValueError, IndexError):
                timeout = 90.0
        try:
            return self._command_runner(
                [binary, *self._cli_args(), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise WorkspaceError(f"OpenShell CLI unavailable: {error}") from error

    def _require_docker_gateway(self) -> None:
        if self._gateway_checked:
            return
        if self._client is None and self._client_factory is None and self._endpoint is None:
            self._assert_registered_transport()
        result = self._run_cli(["gateway", "info", "-o", "json"])
        if result.returncode != 0:
            raise WorkspaceError(f"cannot inspect OpenShell gateway: {result.stderr[-1000:]}")
        try:
            names = [item["name"] for item in json.loads(result.stdout)["compute_drivers"]]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise WorkspaceError("OpenShell gateway info did not report compute drivers") from error
        if names != ["docker"]:
            raise WorkspaceError(
                f"OpenShell adapter requires exactly the docker compute driver, got {names!r}"
            )
        self._gateway_checked = True

    @staticmethod
    def _grpc_code(error: BaseException) -> Any:
        return getattr(error, "code", lambda: None)()

    def _record(self, logical_name: str, ref: Any, labels: Mapping[str, str]) -> None:
        if not logical_name or not getattr(ref, "id", "") or not getattr(ref, "name", ""):
            raise WorkspaceError("OpenShell returned an invalid sandbox identity")
        previous = self._refs.get(logical_name)
        if previous is not None and (previous.id != ref.id or previous.name != ref.name):
            raise WorkspaceError("OpenShell returned a replacement sandbox for a recorded identity")
        self._refs[logical_name] = ref
        self._labels[logical_name] = {LABEL: "1", **dict(labels)}

    def _create(self, spec: SandboxSpec, *, user: str) -> str:
        self._require_docker_gateway()
        logical_name = spec.name
        name = self._gateway_name(logical_name)
        if any(ref.name == name and known != logical_name for known, ref in self._refs.items()):
            raise SandboxExists(f"OpenShell sandbox name {name} collides with a held Corsair identity")
        expected = {LABEL: "1", **dict(spec.labels)}
        with self._sdk() as client:
            try:
                created = client.create(
                    workspace=self.workspace, spec=self._spec(spec, user=user), name=name, labels=expected
                )
            except BaseException as error:
                if self._grpc_code(error) == grpc.StatusCode.ALREADY_EXISTS:
                    raise SandboxExists(f"OpenShell sandbox {logical_name} already exists") from error
                # A create timeout is never retried.  One GET distinguishes a held identity
                # from an unresolved admission failure, but neither is adopted or removed.
                try:
                    existing = client.get(name, workspace=self.workspace)
                except BaseException:
                    raise WorkspaceError(
                        f"OpenShell create for {logical_name} is uncertain; it was not retried"
                    ) from error
                if getattr(existing, "id", ""):
                    raise SandboxExists(f"OpenShell sandbox {logical_name} may have been created") from error
                raise WorkspaceError(f"OpenShell create failed: {error}") from error
            if not getattr(created, "id", "") or created.name != name:
                raise WorkspaceError("CreateSandbox did not return the requested name and non-empty id")
            if any(created.labels.get(key) != value for key, value in expected.items()):
                raise WorkspaceError("CreateSandbox returned labels different from the requested identity")
            self._record(logical_name, created, spec.labels)
            self._users[logical_name] = user
            ready = client.wait_ready(name, workspace=self.workspace, timeout_seconds=self._ready_timeout)
            if ready.id != created.id or ready.name != name:
                raise WorkspaceError("OpenShell wait_ready returned a replacement sandbox")
            self._record(logical_name, ready, spec.labels)
        self._workload(logical_name, expected_user=user)
        if user == BUILD_USER:
            # Do this before any model command.  A builder can mutate its own cache afterwards,
            # but cannot redirect a later privileged archive copy through a replacement link.
            self._prepare_builder_paths(logical_name)
        return logical_name

    def create(self, spec: SandboxSpec) -> str:
        return self._create(spec, user=BUILD_USER)

    def _inspect_workload(self, ref: Any, labels: Mapping[str, str], expected_user: str) -> str:
        listed = native.docker(
            "ps",
            "--all",
            "--filter",
            f"label={_WORKLOAD_ID_LABEL}={ref.id}",
            "--filter",
            f"label={_WORKLOAD_ROLE_LABEL}={_WORKLOAD_ROLE}",
            "--format",
            "{{.ID}}",
        )
        candidates = listed.stdout.decode(errors="replace").split()
        verified: list[str] = []
        for candidate in candidates:
            raw = native.docker("inspect", "--format", "{{json .}}", candidate)
            if raw.returncode != 0:
                continue
            try:
                info = json.loads(raw.stdout)
                got = info["Config"]["Labels"] or {}
                host = info["HostConfig"]
                container_id = info["Id"]
                security = set(host.get("SecurityOpt") or [])
                user = info["Config"].get("User")
                pids = host.get("PidsLimit")
                memory = host.get("Memory")
                cpu = host.get("NanoCpus")
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            expected = {
                LABEL: "1",
                **dict(labels),
                _WORKLOAD_ID_LABEL: ref.id,
                _WORKLOAD_ROLE_LABEL: _WORKLOAD_ROLE,
            }
            if any(got.get(key) != value for key, value in expected.items()):
                continue
            if (
                host.get("NetworkMode") != "none"
                or set(host.get("CapDrop") or []) != {"ALL"}
                or host.get("CapAdd") not in (None, [])
                or "no-new-privileges:true" not in security
                or user != expected_user
                or not isinstance(pids, int)
                or pids <= 0
                or pids > 256
                or memory != self._memory_bytes()
                or cpu != self._nano_cpus()
            ):
                raise WorkspaceError(
                    "OpenShell workload failed local Docker isolation or resource-limit verification"
                )
            verified.append(container_id)
        if len(verified) != 1:
            raise WorkspaceError(
                f"expected one verified OpenShell workload for sandbox id {ref.id}, found {len(verified)}"
            )
        return verified[0]

    def _memory_bytes(self) -> int:
        units = {
            "b": 1,
            "k": 1000,
            "kb": 1000,
            "ki": 1024,
            "kib": 1024,
            "m": 1000**2,
            "mb": 1000**2,
            "mi": 1024**2,
            "mib": 1024**2,
            "g": 1000**3,
            "gb": 1000**3,
            "gi": 1024**3,
            "gib": 1024**3,
        }
        matched = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([A-Za-z]*)", self.memory.strip())
        if matched is None:
            raise WorkspaceError(f"unsupported OpenShell Docker memory limit {self.memory!r}")
        try:
            return int(Decimal(matched.group(1)) * units[matched.group(2).lower() or "b"])
        except (InvalidOperation, KeyError):
            raise WorkspaceError(f"unsupported OpenShell Docker memory limit {self.memory!r}") from None

    def _nano_cpus(self) -> int:
        value = self.cpu.strip().lower()
        try:
            if value.endswith("m"):
                return int(Decimal(value[:-1]) * 1_000_000)
            return int(Decimal(value) * 1_000_000_000)
        except InvalidOperation:
            raise WorkspaceError(f"unsupported OpenShell Docker CPU limit {self.cpu!r}") from None

    def _verified_ref(self, name: str) -> Any:
        ref = self._refs.get(name)
        labels = self._labels.get(name)
        if ref is None or labels is None:
            raise WorkspaceError(f"unknown OpenShell sandbox identity {name}; refusing access")
        try:
            with self._sdk() as client:
                current = client.get(ref.name, workspace=self.workspace)
        except BaseException as error:
            if self._grpc_code(error) in (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAVAILABLE):
                raise WorkspaceError(
                    f"OpenShell sandbox {name} is unavailable; refusing local Docker access"
                ) from error
            raise WorkspaceError(
                f"cannot verify OpenShell sandbox {name} before local Docker access"
            ) from error
        if current.id != ref.id or current.name != ref.name:
            raise WorkspaceError("OpenShell sandbox identity changed; refusing local Docker access")
        if any(current.labels.get(key) != value for key, value in labels.items()):
            raise WorkspaceError("OpenShell sandbox labels changed; refusing local Docker access")
        self._refs[name] = current
        return current

    def _workload(self, name: str, *, expected_user: str | None = None) -> str:
        ref = self._verified_ref(name)
        labels = self._labels.get(name)
        user = expected_user or self._users.get(name)
        if labels is None or user is None:
            raise WorkspaceError(
                f"unknown OpenShell sandbox command identity {name}; refusing local Docker access"
            )
        if expected_user is not None and self._users.get(name) != expected_user:
            raise WorkspaceError("OpenShell sandbox was created for a different command identity")
        # The container's mutable name is never a trusted handle.  Re-inspect the gateway
        # identity and return Docker's immutable container ID on every privileged operation.
        workload = self._inspect_workload(ref, labels, user)
        previous = self._workloads.get(name)
        if previous is not None and previous != workload:
            raise WorkspaceError(
                "OpenShell workload container identity changed; refusing privileged Docker access"
            )
        self._workloads[name] = workload
        # DockerSandboxes' archive helper owns trusted source and support files as the builder,
        # never root and never the probe uid.  Its privileged host operation does not execute
        # model code.
        self._native._owners[workload] = (BUILD_UID, BUILD_UID)
        return workload

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        self._native.copy_tree_in(self._workload(name), source, destination)

    def _prepare_builder_paths(self, name: str) -> None:
        """Pre-create standard user-local package homes before a non-root build command runs."""
        if name in self._prepared:
            return
        with tempfile.TemporaryDirectory(prefix="corsair-openshell-") as directory:
            source = Path(directory)
            for relative in _BUILD_DIRECTORIES:
                (source / relative).mkdir(parents=True, exist_ok=True)
            for path in source.rglob("*"):
                if path.is_dir():
                    path.chmod(0o755)
            self._native.copy_tree_in(self._workload(name, expected_user=BUILD_USER), source, "/tmp")
        self._prepared.add(name)

    @staticmethod
    def _prepend_path(prefix: str, value: str | None) -> str:
        """Add a kernel-owned search path without discarding a caller's path value."""
        return prefix if not value else f"{prefix}:{value}"

    def _command_environment(self, name: str, env: Mapping[str, str] | None) -> dict[str, str]:
        """Provide non-root build homes and make their Python installs visible to a probe."""
        command_env = dict(env or {})
        python_target = _BUILD_ENVIRONMENT["PYTHONPATH"]
        if self._users.get(name) == BUILD_USER:
            command_env = {**_BUILD_ENVIRONMENT, **command_env}
            # The build must install the replayed project outside immutable source, and any
            # caller PYTHONPATH remains useful for a submitted toolchain command.
            command_env["PIP_TARGET"] = _BUILD_ENVIRONMENT["PIP_TARGET"]
            command_env["PYTHONPATH"] = self._prepend_path(python_target, (env or {}).get("PYTHONPATH"))
        elif self._users.get(name) == PROBE_USER:
            # A probe is a fresh SDK process, so it must be able to import the project placed
            # by a builder in PIP_TARGET.  Do not replace framework-provided probe paths.
            command_env["PYTHONPATH"] = self._prepend_path(python_target, command_env.get("PYTHONPATH"))
        return command_env

    @staticmethod
    def _support_relative(path: str) -> PurePosixPath:
        """Accept one canonical descendant of the kernel-owned support directory."""
        candidate = PurePosixPath(path)
        root = PurePosixPath(WORKDIR) / ".corsair"
        if (
            not candidate.is_absolute()
            or str(candidate) != path
            or any(part in (".", "..") for part in candidate.parts)
        ):
            raise WorkspaceError("OpenShell support file path must be canonical")
        try:
            relative = candidate.relative_to(root)
        except ValueError as error:
            raise WorkspaceError(
                "OpenShell only admits trusted support files beneath /work/.corsair"
            ) from error
        if not relative.parts:
            raise WorkspaceError("OpenShell support file path must name a file")
        return relative

    def write_file(self, name: str, path: str, data: bytes) -> None:
        relative = self._support_relative(path)
        # Docker's daemon archive path is a trusted control-plane operation.  OpenShell drops
        # every container capability, including CAP_FOWNER, so the native root-write helper
        # cannot chmod a builder-owned directory.  Archive ownership remains 1001:1001 and the
        # probe is 1000:1000, so the 0444 support file and 0755 parent remain non-writable to a
        # probe even after a fresh image is opened.
        with tempfile.TemporaryDirectory(prefix="corsair-openshell-") as directory:
            source = Path(directory)
            target = source / ".corsair" / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(data)
            target.chmod(0o444)
            self._native.copy_tree_in(self._workload(name), source, WORKDIR)
        self._trusted_support.setdefault(name, set()).add(relative.as_posix())

    def source_unchanged(self, name: str, source: Path) -> bool:
        from corsair.domain.case import tree_manifest

        workload = self._workload(name, expected_user=BUILD_USER)
        trusted = self._trusted_support.get(name, set())
        expected_support = {entry for entry in trusted if re.fullmatch(r"source-[0-9a-f]{32}\.json", entry)}
        if "build.sh" in trusted:
            expected_support.add("build.sh")
        support_code = (
            "import json,os,stat,sys; root='/work/.corsair'; expected=set(json.loads(sys.argv[1]))\n"
            "try: mode=os.lstat(root).st_mode\n"
            "except FileNotFoundError: raise SystemExit(0 if not expected else 1)\n"
            "if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode): raise SystemExit(1)\n"
            "actual=set(os.listdir(root))\n"
            "if actual != expected: raise SystemExit(1)\n"
            "for entry in actual:\n"
            " mode=os.lstat(os.path.join(root,entry)).st_mode\n"
            " if not stat.S_ISREG(mode) or stat.S_ISLNK(mode): raise SystemExit(1)\n"
        )
        support = self._native.exec_once(
            workload,
            ["python", "-I", "-c", support_code, json.dumps(sorted(expected_support))],
            workdir="/",
            trusted=True,
            timeout=30,
        )
        if support.exit_code != 0:
            return False
        expected = tree_manifest(source, directories=True)
        manifest = f"{WORKDIR}/.corsair/source-{uuid.uuid4().hex}.json"
        self.write_file(name, manifest, json.dumps(expected).encode())
        code = (
            "import hashlib,json,os,stat,sys; root='/work'; expected=json.load(open(sys.argv[1])); actual=[]\n"
            "for relative,_,_ in expected:\n"
            " p=os.path.join(root,relative); s=os.lstat(p); mode=s.st_mode\n"
            " if stat.S_ISLNK(mode): kind,data='120000',os.readlink(p).encode()\n"
            " elif stat.S_ISREG(mode): kind,data=('100755' if mode & 0o111 else '100644'),open(p,'rb').read()\n"
            " elif stat.S_ISDIR(mode): kind,data='040000',b''\n"
            " else: raise ValueError('unsupported original source type')\n"
            " actual.append([relative,kind,hashlib.sha256(data).hexdigest()])\n"
            "assert actual==expected, 'original source changed'\n"
        )
        result = self._native.exec_once(
            workload, ["python", "-I", "-c", code, manifest], workdir="/", trusted=True, timeout=120
        )
        return result.exit_code == 0

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        return self._native.copy_out(self._workload(name), paths)

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
        if trusted:
            return self._native.exec_once(
                self._workload(name), argv, workdir=workdir, env=env, timeout=timeout, trusted=True
            )
        ref = self._verified_ref(name)
        command_env = self._command_environment(name, env)
        try:
            with self._sdk() as client:
                result = client.exec(
                    ref.name,
                    list(argv),
                    workspace=self.workspace,
                    workdir=workdir,
                    env=command_env or None,
                    timeout_seconds=math.ceil(timeout) if timeout is not None else None,
                    no_login_shell=True,
                )
        except BaseException as error:
            if self._grpc_code(error) == grpc.StatusCode.DEADLINE_EXCEEDED:
                return Exec(None, b"", b"", timed_out=True)
            if self._grpc_code(error) in (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAVAILABLE):
                return Exec(None, b"", str(error).encode(), container_failed=True)
            raise WorkspaceError(f"OpenShell exec failed: {error}") from error
        return Exec(result.exit_code, result.stdout.encode(), result.stderr.encode())

    def drop_network(self, name: str) -> None:
        ref = self._verified_ref(name)
        policy = self._policy(build=False, user=BUILD_USER)
        payload = json_format.MessageToDict(policy, preserving_proto_field_name=True)
        payload["filesystem_policy"] = payload.pop("filesystem")
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8") as policy_file:
            yaml.safe_dump(payload, policy_file, sort_keys=True)
            policy_file.flush()
            result = self._run_cli(
                ["policy", "set", ref.name, "--policy", policy_file.name, "--wait", "--timeout", "60"]
            )
        if result.returncode != 0:
            raise WorkspaceError(f"OpenShell policy set failed: {result.stderr[-1000:]}")
        with self._sdk() as client:
            current = client.get(ref.name, workspace=self.workspace)
        if (
            current.id != ref.id
            or current.name != ref.name
            or current.current_policy_version <= ref.current_policy_version
        ):
            raise WorkspaceError(
                "OpenShell did not confirm the offline policy version on the created sandbox"
            )
        self._refs[name] = current

    def image_id(self, name: str) -> str | None:
        return self._native.image_id(self._workload(name))

    def resolve_image(self, reference: str) -> str | None:
        return self._native.resolve_image(reference)

    def find_environment(self, tag: str, key: str) -> str | None:
        return self._native.find_environment(tag, key)

    def seal_environment(
        self, name: str, tag: str, key: str, log_sha256: str, writable: Sequence[str] = ()
    ) -> None:
        workload = self._workload(name)
        if self._users.get(name) != BUILD_USER:
            raise WorkspaceError("only a non-root OpenShell builder can seal an environment")

        def static(argv: Sequence[str]) -> None:
            result = self.exec_once(name, argv, workdir="/", timeout=120)
            if result.exit_code != 0:
                raise WorkspaceError(f"cannot seal source: {result.stderr.decode(errors='replace')[-500:]}")

        # These SDK commands have only fixed adapter-owned arguments; no producer-controlled
        # command executes through the trusted Docker path.  The builder owns /work and can
        # change its modes without CAP_FOWNER, unlike a capability-stripped uid-0 Docker exec.
        static(["chmod", "-R", "a-w", _BUILD_ROOT])
        static(["chmod", "-R", "a-w", WORKDIR])
        for path in writable:
            static(["chmod", "u+w", WORKDIR])
            static(["sh", "-c", 'test ! -L "$1" && mkdir -p "$1" && chmod 555 "$1"', "sh", path])
        static(["chmod", "a-w", WORKDIR])
        committed = native.docker(
            "commit",
            "--change",
            f"LABEL {native.ENV_KEY_LABEL}={key} {native.ENV_LOG_LABEL}={log_sha256}",
            "--change",
            "WORKDIR /tmp",
            "--change",
            "ENTRYPOINT []",
            "--change",
            "CMD []",
            "--change",
            f"USER {BUILD_USER}",
            workload,
            tag,
            timeout=1800,
        )
        if committed.returncode != 0:
            raise WorkspaceError(f"docker commit failed: {committed.stderr.decode(errors='replace')[-1000:]}")

    def open_environment(self, image: str, workdir: str, sandbox_labels: Mapping[str, str]) -> str:
        if workdir != WORKDIR:
            raise WorkspaceError(f"OpenShell local Docker adapter requires workdir {WORKDIR}")
        return self._create(
            SandboxSpec(image=image, labels=sandbox_labels, network="none", workdir=workdir), user=PROBE_USER
        )

    def workspace_state(self, name: str) -> dict[str, tuple[str, str]] | None:
        return self._native.workspace_state(self._workload(name))

    def labelled(self, run_id: str | None = None) -> list[str]:
        selector = f"{LABEL}=1" + (f",{RUN_LABEL}={run_id}" if run_id else "")
        with self._sdk() as client:
            listed = client.list_all(workspace=self.workspace, label_selector=selector)
            names: list[str] = []
            for item in listed:
                current = client.get(item.name, workspace=self.workspace)
                if current.id == item.id and current.labels.get(LABEL) == "1":
                    # List results expose native short names.  Reconciliation only needs an
                    # exact reference for deletion; no lossy hash inversion is attempted.
                    self._record(current.name, current, current.labels)
                    names.append(current.name)
        return sorted(names)

    def remove(self, name: str) -> bool:
        expected = self._refs.get(name)
        if expected is None:
            return False
        try:
            with self._sdk() as client:
                current = client.get(expected.name, workspace=self.workspace)
                if current.id != expected.id or current.name != expected.name:
                    return False
                receipt = client.delete(expected.name, workspace=self.workspace, allow_missing=False)
                if getattr(receipt, "sandbox_id", None) != expected.id:
                    return False
                client.wait_deleted(
                    expected.name,
                    workspace=self.workspace,
                    timeout_seconds=self._delete_timeout,
                    expected_sandbox_id=expected.id,
                )
                try:
                    client.get(expected.name, workspace=self.workspace)
                except BaseException as error:
                    if self._grpc_code(error) == grpc.StatusCode.NOT_FOUND:
                        self._refs.pop(name, None)
                        self._labels.pop(name, None)
                        self._users.pop(name, None)
                        self._workloads.pop(name, None)
                        self._prepared.discard(name)
                        self._trusted_support.pop(name, None)
                        return True
                    return False
                return False  # A same-name replacement makes SDK wait_deleted insufficient.
        except BaseException:
            return False
