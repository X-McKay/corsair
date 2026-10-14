"""Native OpenShell v0.1.3 sandbox boundary for Corsair v2.

This module deliberately has no host-process workload fallback.  Lifecycle is
performed through the official OpenShell CLI/curated SDK, while the Store holds
intent and result receipts before and after every side effect.  Docker-backed
OpenShell remains an explicitly *unqualified* profile until a frozen native
qualification certificate binds the effective policy/runtime tuple.
"""
from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
import os
import re
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import grpc
from openshell import (
    DeletionOutcome,
    ExecChunk,
    ExecResult,
    SandboxClient,
)
from openshell import __version__ as SDK_VERSION

from .contracts import (
    ArtifactRef,
    CommandResult,
    OperatorConfig,
    SourceSnapshot,
    WorkspaceLease,
    confined_path,
    digest,
)
from .source import SourceService
from .storage import Store, _private_directory

_OPEN_SHELL_VERSION = "0.1.3"
_MAX_CLI_OUTPUT = 256 * 1024
_MAX_REPORT_BYTES = 256 * 1024
_OUTPUT_EXCERPT_BYTES = 16 * 1024
_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SandboxBoundaryError(RuntimeError):
    """The native boundary could not safely establish the requested effect."""


@dataclass(frozen=True)
class _CliResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limited: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded_text(data: bytes, limit: int) -> str:
    return data[:limit].decode("utf-8", "replace")


def _excerpt(value: str) -> str:
    """Keep Temporal-facing command text compact without dropping retained evidence."""
    return value.encode("utf-8", "replace")[:_OUTPUT_EXCERPT_BYTES].decode("utf-8", "replace")


def _phase(value: Any) -> str:
    """Return the curated status phase without importing generated protobuf APIs."""
    status = getattr(value, "status", None)
    phase = getattr(status, "phase", "")
    if type(phase) is int:
        # Curated v0.1.3 SandboxStatusRef exports an int, not a Python enum.
        # SANDBOX_PHASE_READY is 2 in the pinned published wire schema.
        return "ready" if phase == 2 else f"native_phase_{phase}"
    if hasattr(phase, "name"):
        phase = phase.name
    return str(phase).removeprefix("SANDBOX_PHASE_").lower()


def _error_code(error: BaseException) -> str | None:
    code = error.code() if callable(getattr(error, "code", None)) else None
    return getattr(code, "name", None)


def _is_not_found(error: BaseException) -> bool:
    return isinstance(error, grpc.RpcError) and error.code() == grpc.StatusCode.NOT_FOUND


def _is_policy_denial(error: BaseException) -> bool:
    if not isinstance(error, grpc.RpcError):
        return False
    if error.code() == grpc.StatusCode.PERMISSION_DENIED:
        return True
    info = getattr(error, "error_info", None)
    return getattr(info, "reason", "") in {"POLICY_DENIED", "SANDBOX_POLICY_DENIED"}


def _operation_id(kind: str, *parts: str) -> str:
    rendered = digest({"kind": kind, "parts": list(parts)})
    return f"openshell.{kind}.{rendered[:48]}"


def _run_bounded(argv: tuple[str, ...], *, timeout: float, output_limit: int = _MAX_CLI_OUTPUT,
                 file_size_limit: int | None = None, cwd: Path | None = None) -> _CliResult:
    """Run one literal native CLI argv with bounded retained stdout/stderr.

    The OpenShell CLI is used for create/upload/download because the selected
    curated SDK has no public transfer/policy-spec construction surface.  This
    helper never invokes a shell and stops a CLI that exceeds either wall time
    or its retained output envelope.
    """
    if not argv or any(not isinstance(item, str) or not item or "\0" in item for item in argv):
        raise ValueError("Native command requires a literal nonempty argv")
    if not 0 < timeout <= 900 or not 1024 <= output_limit <= 4 * 1024 * 1024:
        raise ValueError("Native command bounds are outside the accepted envelope")

    if file_size_limit is not None:
        limiter = shutil.which("prlimit")
        if not limiter:
            raise SandboxBoundaryError("Native transfers require util-linux prlimit for safe file-size bounds")
        argv = (limiter, f"--fsize={file_size_limit}:{file_size_limit}", "--", *argv)

    started = time.monotonic()
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                               close_fds=True, start_new_session=True)
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    for stream, kind in ((process.stdout, "stdout"), (process.stderr, "stderr")):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, kind)
    stdout, stderr = bytearray(), bytearray()
    timed_out = output_limited = False
    try:
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = stdout if key.data == "stdout" else stderr
                allowed = output_limit - len(stdout) - len(stderr)
                if allowed <= 0 or len(chunk) > allowed:
                    if allowed > 0:
                        target.extend(chunk[:allowed])
                    output_limited = True
                    break
                target.extend(chunk)
            if output_limited:
                break
        if timed_out or output_limited:
            os.killpg(process.pid, signal.SIGKILL)
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        returncode = process.wait(timeout=5)
        timed_out = True
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return _CliResult(returncode, bytes(stdout), bytes(stderr), timed_out, output_limited)


def _exec_worker(connection: Any, gateway: str, workspace: str, name: str, sandbox_id: str,
                 command: tuple[str, ...], workdir: str | None, timeout_seconds: int,
                 output_limit: int, memory_limit: int) -> None:
    """Isolate the SDK's unbounded ``ExecResult`` buffering in a capped process."""
    dispatched = False
    try:
        # The selected SDK joins remote output before returning an ExecResult.
        # Keep that risk outside the durable worker and below a fixed process
        # address-space ceiling; a worker loss is an unknown remote effect.
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        with SandboxClient.from_active_cluster(cluster=gateway, timeout=float(timeout_seconds + 10),
                                               auto_refresh=True, write_back=True, insecure=False) as client:
            current = client.get(name, workspace=workspace)
            if current.id != sandbox_id or current.name != name or current.workspace != workspace or _phase(current) != "ready":
                connection.send(("preflight", {"ok": False, "detail": "sandbox identity or Ready phase changed"}))
                return
            connection.send(("preflight", {"ok": True}))
            dispatched = True
            captured = 0
            result = None
            # exec_stream also buffers internally, but yielding lets us close
            # the native client at the cap instead of awaiting an unbounded
            # complete ExecResult. Closing transport does not prove remote stop.
            for event in client.exec_stream(name, command, workspace=workspace, workdir=workdir,
                                            timeout_seconds=timeout_seconds, no_login_shell=True):
                if isinstance(event, ExecChunk):
                    captured += len(event.data)
                    if captured > output_limit:
                        connection.send(("result", {"kind": "output_limit", "exit_code": None,
                                                     "stdout": "", "stderr": "",
                                                     "detail": "Native stream exceeded output cap; remote effect remains unknown"}))
                        return
                elif isinstance(event, ExecResult):
                    result = event
            if result is None:
                raise SandboxBoundaryError("Native stream ended without a terminal result")
        stdout = result.stdout.encode("utf-8", "replace")
        stderr = result.stderr.encode("utf-8", "replace")
        if len(stdout) + len(stderr) > output_limit:
            connection.send(("result", {"kind": "output_limit", "exit_code": result.exit_code,
                                         "stdout": "", "stderr": "", "detail": "native output exceeded retained envelope"}))
            return
        connection.send(("result", {"kind": "completed", "exit_code": result.exit_code,
                                     "stdout": result.stdout, "stderr": result.stderr, "detail": ""}))
    except BaseException as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome; child must report all transport failures
        connection.send(("error", {"dispatched": dispatched, "type": type(error).__name__,
                                   "code": _error_code(error), "detail": str(error)[:2048],
                                   "policy_denied": _is_policy_denial(error)}))
    finally:
        connection.close()


class Sandbox:
    """Corsair's explicit, receipt-backed OpenShell lifecycle boundary.

    ``Sandbox`` accepts only a v2 operator config and v2 Store.  Every workload
    command reaches OpenShell; no Docker, subprocess, SSH, or local-execution
    substitute exists in this class.
    """

    def __init__(self, config: OperatorConfig, store: Store):
        if not isinstance(config, OperatorConfig) or not isinstance(store, Store):
            raise ValueError("Sandbox requires v2 OperatorConfig and Store")  # noqa: TRY004 - invalid admission is consistently ValueError
        self.config, self.store = config, store
        self.profile = config.sandbox
        self._policy_path, self._policy_sha256 = self._read_policy(self.profile.policy_path)
        policy = self._policy_path.read_bytes()
        if _sha256(policy) != self._policy_sha256:
            raise SandboxBoundaryError("Operator policy changed during admission")
        self._policy_ref = self.store.put(policy)
        policy_root = _private_directory(self.store.root / "operator-policies")
        self._policy_path = policy_root / (self._policy_sha256 + ".yaml")
        try:
            descriptor = os.open(self._policy_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        except FileExistsError:
            if self._policy_path.is_symlink() or self._policy_path.read_bytes() != policy:
                raise SandboxBoundaryError("Frozen operator policy identity mismatch")
        else:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(policy)
                stream.flush()
                os.fsync(stream.fileno())
        self._gateway = self._registered_gateway(self.profile.gateway)
        self._cli = self._find_cli(self.profile.cli_path)
        self._cli_sha256 = _sha256(self._cli.read_bytes())
        self._cli_version: str | None = None
        self._known_leases: dict[tuple[str, int], WorkspaceLease] = {}
        self._stage_root = _private_directory(self.store.root / "openshell-stage")
        self._download_root = _private_directory(self.store.root / "openshell-download")

    @staticmethod
    def _read_policy(value: str) -> tuple[Path, str]:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("OpenShell policy path must be absolute")
        try:
            info = os.lstat(path)
        except FileNotFoundError as error:
            raise ValueError("OpenShell policy file is absent") from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > 4 * 1024 * 1024:
            raise ValueError("OpenShell policy must be a bounded regular non-symlink file")
        data = path.read_bytes()
        return path, _sha256(data)

    @staticmethod
    def _registered_gateway(value: str | None) -> str:
        if not value:
            raise ValueError("An explicit registered OpenShell mTLS gateway name is required")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
            raise ValueError("OpenShell gateway must be a registered gateway name, not an endpoint URL")
        return value

    @staticmethod
    def _find_cli(explicit: str | None = None) -> Path:
        found = explicit or shutil.which("openshell")
        candidates = (Path(found),) if found else ()
        for candidate in candidates:
            try:
                info = os.lstat(candidate)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and os.access(candidate, os.X_OK):
                return candidate
        raise SandboxBoundaryError("OpenShell CLI is unavailable; configure sandbox.cli_path or PATH")

    def _cli_argv(self, *arguments: str) -> tuple[str, ...]:
        # Resolve the named native registration, including its mTLS certificate
        # bundle. Do not substitute a direct endpoint or disable TLS checks.
        return (str(self._cli), "--color", "never", "--workspace", self.profile.workspace,
                "--gateway", self._gateway, *arguments)

    def _invoke_cli(self, *arguments: str, timeout: float = 60, output_limit: int = _MAX_CLI_OUTPUT,
                    file_size_limit: int | None = None, cwd: Path | None = None) -> _CliResult:
        return _run_bounded(self._cli_argv(*arguments), timeout=timeout, output_limit=output_limit,
                            file_size_limit=file_size_limit, cwd=cwd)

    def _sdk(self) -> SandboxClient:
        return SandboxClient.from_active_cluster(cluster=self._gateway, timeout=30.0,
                                                 auto_refresh=True, write_back=True, insecure=False)

    @property
    def _profile_digest(self) -> str:
        return digest({"name": self.profile.name, "workspace": self.profile.workspace,
                       "workspace_root": self.profile.workspace_root, "gateway": self._gateway,
                       "image": self.profile.image, "policy_sha256": self._policy_sha256,
                       "sdk_version": SDK_VERSION, "cli_sha256": self._cli_sha256})

    def _name(self, run_id: str, generation: int) -> str:
        if not isinstance(run_id, str) or not run_id or len(run_id) > 128 or not isinstance(generation, int) or generation < 1:
            raise ValueError("A bounded run_id and positive generation are required")
        # Docker-driver hostnames leave only 19 characters on this release.
        # 80 name bits plus exact UUID and full durable request binding prevent
        # a name collision from authorizing use of a different resource.
        raw = hashlib.sha256(f"{run_id}\0{generation}".encode()).digest()
        name = "cv2" + base64.b32encode(raw).decode().lower()[:16]
        if not _NAME.fullmatch(name):
            raise ValueError("Unable to form a valid deterministic sandbox name")
        return name

    def _labels(self, run_id: str, generation: int, source_manifest: ArtifactRef) -> dict[str, str]:
        # Native label values have a 63-character limit; full SHA-256 values
        # stay in immutable Store receipts, not truncated evidence identities.
        return {"corsair.run": _sha256(run_id.encode())[:48], "corsair.generation": str(generation),
                "corsair.profile": self._profile_digest[:48], "corsair.source_manifest": source_manifest.sha256[:48],
                "corsair.workspace": self.profile.workspace}

    def _assert_lease(self, lease: WorkspaceLease, *, require_ready: bool = True) -> Any:
        if not isinstance(lease, WorkspaceLease) or lease.image != self.profile.image or lease.policy_sha256 != self._policy_sha256:
            raise SandboxBoundaryError("Lease is not for this immutable operator profile")
        expected = self._labels(lease.run_id, lease.generation, self._lease_source_manifest(lease))
        with self._sdk() as client:
            current = client.get(lease.name, workspace=self.profile.workspace)
        if current.id != lease.sandbox_id or current.name != lease.name or current.workspace != self.profile.workspace:
            raise SandboxBoundaryError("Sandbox UUID/name/workspace identity changed")
        if dict(current.labels) != expected:
            raise SandboxBoundaryError("Sandbox labels do not match the exact lease claim")
        if require_ready and _phase(current) != "ready":
            raise SandboxBoundaryError("Sandbox is not in the exact Ready phase")
        return current

    def _lease_source_manifest(self, lease: WorkspaceLease) -> ArtifactRef:
        prior = self.store.operation(_operation_id("create", lease.run_id, str(lease.generation)))
        if not prior or type(prior.get("source_manifest")) is not dict:
            prior = next((e["payload"] for e in self.store.events(lease.run_id)
                          if e["kind"] == "sandbox.create.intent" and
                          e["payload"].get("name") == lease.name), None)
        if not prior or type(prior.get("source_manifest")) is not dict:
            raise SandboxBoundaryError("No durable source-manifest intent exists for this lease")
        try:
            return ArtifactRef.model_validate(prior["source_manifest"])
        except Exception as error:
            raise SandboxBoundaryError("Lease source-manifest receipt is malformed") from error

    def _complete(self, operation_id: str, value: dict[str, Any]) -> None:
        self.store.complete_operation(operation_id, value)

    def _event(self, run_id: str, kind: str, payload: dict[str, Any], operation_id: str) -> None:
        # Runs are registered by the parent engine.  Operation records remain
        # authoritative when a direct component invocation has no run record.
        event_id = f"{operation_id}.event.{digest({'kind': kind, 'payload': payload})[:16]}"
        try:
            self.store.event(run_id, kind, payload, operation_id=event_id)
        except ValueError as error:
            if "Unknown run_id" not in str(error):
                raise

    def acquire(self, run_id: str, generation: int, source_manifest: ArtifactRef) -> WorkspaceLease:
        """Create exactly one deterministic native sandbox and return its UUID-bound lease."""
        if not isinstance(source_manifest, ArtifactRef):
            raise ValueError("A v2 source-manifest ArtifactRef is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        self.store.get(source_manifest)  # retained immutable bytes must exist before intent
        name = self._name(run_id, generation)
        labels = self._labels(run_id, generation, source_manifest)
        operation_id = _operation_id("create", run_id, str(generation))
        request = {"name": name, "workspace": self.profile.workspace, "labels": labels,
                   "image": self.profile.image, "policy_sha256": self._policy_sha256,
                   "policy_ref": self._policy_ref.model_dump(mode="json"),
                   "source_manifest": source_manifest.model_dump(mode="json")}
        claim = self.store.claim_operation(operation_id, digest(request))
        if claim == "recorded":
            recorded = self.store.operation(operation_id) or {}
            if type(recorded.get("lease")) is not dict:
                raise SandboxBoundaryError("Recorded create receipt does not contain a lease")
            lease = WorkspaceLease.model_validate(recorded["lease"])
            self._assert_lease(lease)
            self._known_leases[(lease.run_id, lease.generation)] = lease
            return lease
        if claim == "uncertain":
            # A lost CLI response may have created the deterministic resource.
            # Reconcile by exact current identity; never create a replacement.
            try:
                with self._sdk() as client:
                    current = client.get(name, workspace=self.profile.workspace)
                if current.name != name or current.workspace != self.profile.workspace or dict(current.labels) != labels or not current.id:
                    raise SandboxBoundaryError("Uncertain create resolved to a mismatched sandbox")
                lease = WorkspaceLease(name=name, sandbox_id=current.id, run_id=run_id, generation=generation,
                                       image=self.profile.image, policy_sha256=self._policy_sha256)
                self._complete(operation_id, {"status": "reconciled", "lease": lease.model_dump(mode="json"),
                                              "source_manifest": source_manifest.model_dump(mode="json")})
                self._known_leases[(run_id, generation)] = lease
                return lease
            except Exception as error:
                raise SandboxBoundaryError("Create effect is uncertain; no replacement will be dispatched") from error
        self._event(run_id, "sandbox.create.intent", request, operation_id)
        try:
            # `--from` is the official v0.1.3 CLI spelling for the digest-pinned
            # image.  No provider, mount, forwarding, service, or driver config
            # is supplied.  The static main process exists only to keep the
            # sandbox dispatchable for SDK exec calls.
            arguments: list[str] = ["sandbox", "create", "--name", name, "--from", self.profile.image,
                                    "--policy", str(self._policy_path), "--detach", "--no-tty", "--no-auto-providers",
                                    "--restart-policy", "never", "--memory", str(self.profile.memory_bytes),
                                    "--output", "json"]
            for key, value in labels.items():
                arguments.extend(("--label", f"{key}={value}"))
            arguments.extend(("--", "/bin/sh", "-c", "while :; do sleep 3600; done"))
            created = self._invoke_cli(*arguments, timeout=self.profile.readiness_timeout_seconds)
            if created.timed_out or created.output_limited:
                raise SandboxBoundaryError("Native create response is incomplete; effect is uncertain")
            if created.returncode != 0:
                raise SandboxBoundaryError("Native create failed before an acknowledged lease: " + _bounded_text(created.stderr, 2048))
            with self._sdk() as client:
                ready = client.wait_ready(name, workspace=self.profile.workspace,
                                          timeout_seconds=float(self.profile.readiness_timeout_seconds))
                current = client.get(name, workspace=self.profile.workspace)
            if _phase(ready) != "ready" or _phase(current) != "ready":
                raise SandboxBoundaryError("Native wait did not establish Ready phase")
            if current.name != name or current.workspace != self.profile.workspace or dict(current.labels) != labels or not current.id:
                raise SandboxBoundaryError("Native create identity does not match its claim")
            lease = WorkspaceLease(name=name, sandbox_id=current.id, run_id=run_id, generation=generation,
                                   image=self.profile.image, policy_sha256=self._policy_sha256)
            receipt = {"status": "created", "lease": lease.model_dump(mode="json"),
                       "source_manifest": source_manifest.model_dump(mode="json"), "cli_stdout_sha256": _sha256(created.stdout),
                       "cli_stderr_sha256": _sha256(created.stderr), "profile_sha256": self._profile_digest}
            self._complete(operation_id, receipt)
            self._event(run_id, "sandbox.create.result", receipt, operation_id)
            self._known_leases[(run_id, generation)] = lease
            return lease
        except Exception as error:
            # The intent is already durable.  Complete it as uncertain so a
            # future invocation is forced through the reconciliation branch.
            self._complete(operation_id, {"status": "unknown_effect", "source_manifest": source_manifest.model_dump(mode="json"),
                                          "detail": str(error)[:2048]})
            raise

    def stage(self, lease: WorkspaceLease, snapshot: SourceSnapshot, overlays: dict[str, bytes]) -> dict[str, Any]:
        """Materialize and transfer only the captured source plus bounded probe overlays."""
        if not isinstance(snapshot, SourceSnapshot) or snapshot.manifest != self._lease_source_manifest(lease):
            raise SandboxBoundaryError("Staged snapshot does not bind to the acquired source manifest")
        self._assert_lease(lease)
        overlay_identity = {path: _sha256(data) for path, data in sorted(overlays.items())}
        request = {"lease": lease.model_dump(mode="json"), "manifest": snapshot.manifest.model_dump(mode="json"),
                   "overlays": overlay_identity, "destination": self.profile.workspace_root}
        operation_id = _operation_id("stage", lease.run_id, str(lease.generation), digest(request))
        claim = self.store.claim_operation(operation_id, digest(request))
        if claim == "recorded":
            return self.store.operation(operation_id) or {}
        if claim == "uncertain":
            raise SandboxBoundaryError("Upload effect is uncertain; staged source will not be uploaded again")
        self._event(lease.run_id, "sandbox.stage.intent", request, operation_id)
        local = self._stage_root / operation_id.replace(".", "-")
        try:
            if local.exists():
                raise SandboxBoundaryError("Fresh native staging directory unexpectedly already exists")
            hashes = {item.path: item.artifact.sha256 for item in snapshot.files}
            hashes.update(overlay_identity)
            receipt_path = f".corsair-input-{digest(request)[:16]}/inputs.sha256"
            if any(p == receipt_path or p.startswith(receipt_path.split('/')[0] + '/') for p in hashes):
                raise SandboxBoundaryError("Source collides with the reserved native input receipt")
            expected_bytes = "".join(f"{sha}  ./{path}\n" for path, sha in sorted(hashes.items())).encode()
            transfer_overlays = {**overlays, receipt_path: expected_bytes}
            SourceService(self.store).materialize(snapshot, local, transfer_overlays)
            # Named directory uploads preserve their basename. The pinned CLI
            # deliberately treats the literal '.' as content-only transfer.
            transfer = self._invoke_cli("sandbox", "upload", lease.name, ".", self.profile.workspace_root,
                                        "--no-git-ignore", timeout=self.config.budget.stage_timeout_seconds, cwd=local)
            if transfer.timed_out or transfer.output_limited:
                raise SandboxBoundaryError("Native upload response is incomplete; effect is uncertain")
            if transfer.returncode != 0:
                raise SandboxBoundaryError("Native upload failed: " + _bounded_text(transfer.stderr, 2048))
            # An SDK execution is the post-transfer native receipt.  It does
            # not make target-authored files trustworthy; it confirms only that
            # the fixed intended workdir is present and dispatchable.
            inventory = self.execute(lease, ("sha256sum", "--check", "--strict", "--status", "--", receipt_path),
                                     _operation_id("stage-inventory", operation_id), workdir=self.profile.workspace_root)
            if inventory.status != "completed" or inventory.exit_code != 0:
                raise SandboxBoundaryError("Native input hash verification did not confirm every staged source/probe byte")
            receipt = {"status": "completed", "operation_id": operation_id, "source_manifest": snapshot.manifest.model_dump(mode="json"),
                       "overlay_sha256": overlay_identity, "remote_root": self.profile.workspace_root,
                       "input_hash_manifest": self.store.put(expected_bytes).model_dump(mode="json"),
                       "cli_sha256": self._cli_sha256, "upload_stdout_sha256": _sha256(transfer.stdout),
                       "upload_stderr_sha256": _sha256(transfer.stderr), "inventory": inventory.model_dump(mode="json")}
            self._complete(operation_id, receipt)
            self._event(lease.run_id, "sandbox.stage.result", receipt, operation_id)
            return receipt
        except Exception as error:
            self._complete(operation_id, {"status": "unknown_effect", "detail": str(error)[:2048],
                                          "source_manifest": snapshot.manifest.model_dump(mode="json")})
            raise

    def _command_result(self, *, operation_id: str, sandbox_id: str, status: str, duration_seconds: float,
                        exit_code: int | None = None, stdout: str = "", stderr: str = "", detail: str = "") -> CommandResult:
        """Create a compact receipt and retain the complete bounded output bytes.

        OpenShell returns strings, so UTF-8 replacement is the only available
        stable byte representation at this curated SDK boundary.  The worker
        has already enforced ``Budget.max_output_bytes`` before this point.
        """
        stdout_bytes, stderr_bytes = stdout.encode("utf-8", "replace"), stderr.encode("utf-8", "replace")
        if len(stdout_bytes) + len(stderr_bytes) > self.config.budget.max_output_bytes:
            raise SandboxBoundaryError("SDK worker returned output beyond the retained envelope")
        return CommandResult(operation_id=operation_id, sandbox_id=sandbox_id, status=status, exit_code=exit_code,
                             stdout=_excerpt(stdout), stderr=_excerpt(stderr),
                             stdout_ref=self.store.put(stdout_bytes), stderr_ref=self.store.put(stderr_bytes),
                             duration_seconds=duration_seconds, detail=detail[:2048])

    def execute(self, lease: WorkspaceLease, argv: tuple[str, ...], operation_id: str,
                workdir: str | None = None) -> CommandResult:
        """Execute one literal argv once through a memory-capped SDK worker."""
        if (not isinstance(argv, tuple) or not argv or len(argv) > 128 or any(not isinstance(arg, str) or not arg or "\0" in arg
                                                                               or len(arg.encode()) > 8192 for arg in argv)
                or sum(len(arg.encode()) + 1 for arg in argv) > 16 * 1024):
            raise ValueError("A bounded literal argv tuple is required")
        if workdir is not None and (not workdir.startswith(self.profile.workspace_root + "/") and workdir != self.profile.workspace_root):
            raise ValueError("Workdir must remain below the configured sandbox workspace root")
        request = {"lease": lease.model_dump(mode="json"), "argv": list(argv), "workdir": workdir,
                   "timeout_seconds": self.config.budget.command_timeout_seconds}
        claim = self.store.claim_operation(operation_id, digest(request))
        if claim == "recorded":
            recorded = self.store.operation(operation_id) or {}
            if type(recorded.get("result")) is dict:
                return CommandResult.model_validate(recorded["result"])
            raise SandboxBoundaryError("Recorded execution receipt is malformed")
        if claim == "uncertain":
            return self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="unknown",
                                        duration_seconds=0, detail="Prior execution dispatch is uncertain and was not retried")
        self._event(lease.run_id, "sandbox.exec.intent", request, operation_id)
        started = time.monotonic()
        try:
            self._assert_lease(lease)
        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
            result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="not_dispatched",
                                          duration_seconds=time.monotonic() - started, detail=str(error)[:2048])
            self._complete(operation_id, {"result": result.model_dump(mode="json")})
            return result
        parent, child = multiprocessing.get_context("spawn").Pipe(duplex=False)
        process: multiprocessing.Process | None = None
        try:
            # The worker needs room for gRPC/Python overhead but cannot consume
            # the worker's full operator memory merely because OpenShell buffers
            # output.  This cap is a host safety boundary, not an OpenShell
            # security qualification claim.
            # gRPC allocates address-space arenas for native threads; the
            # streaming limit bounds actual output, this caps abnormal growth.
            worker_memory = 2 * 1024 * 1024 * 1024
            process = multiprocessing.get_context("spawn").Process(
                target=_exec_worker,
                args=(child, self._gateway, self.profile.workspace, lease.name, lease.sandbox_id, argv, workdir,
                      self.config.budget.command_timeout_seconds, self.config.budget.max_output_bytes, worker_memory),
            )
            process.start()
            child.close()
            deadline = started + self.config.budget.command_timeout_seconds + 15
            preflight = False
            message: tuple[str, dict[str, Any]] | None = None
            while time.monotonic() < deadline:
                if parent.poll(max(0.001, deadline - time.monotonic())):
                    message = parent.recv()
                    if message[0] == "preflight":
                        if not message[1].get("ok"):
                            break
                        preflight = True
                        continue
                    break
                if process.exitcode is not None:
                    break
            duration = time.monotonic() - started
            if message is None or message[0] == "preflight":
                result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id,
                                              status="unknown" if preflight else "not_dispatched", duration_seconds=duration,
                                              detail="Native SDK worker ended without a terminal execution receipt")
            elif message[0] == "result":
                payload = message[1]
                if payload["kind"] == "output_limit":
                    result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="output_limit",
                                                  exit_code=payload["exit_code"], duration_seconds=duration, detail=payload["detail"])
                elif payload["exit_code"] == 124:
                    result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="unknown",
                                                  exit_code=124, stdout=payload["stdout"], stderr=payload["stderr"],
                                                  duration_seconds=duration, detail="OpenShell timeout exit 124 has unknown remote effect")
                else:
                    result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="completed",
                                                  exit_code=payload["exit_code"], stdout=payload["stdout"], stderr=payload["stderr"],
                                                  duration_seconds=duration)
            else:
                payload = message[1]
                status = "policy_denied" if payload.get("policy_denied") and not payload.get("dispatched") else \
                         ("unknown" if payload.get("dispatched") else "not_dispatched")
                result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status=status,
                                              duration_seconds=duration,
                                              detail=f"{payload.get('type')}/{payload.get('code')}: {payload.get('detail')}")
        except (EOFError, OSError) as error:
            result = self._command_result(operation_id=operation_id, sandbox_id=lease.sandbox_id, status="unknown",
                                          duration_seconds=time.monotonic() - started,
                                          detail=f"Native SDK transport worker loss: {type(error).__name__}")
        finally:
            if process is not None:
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
                process.close()
            parent.close()
            child.close()
        self._complete(operation_id, {"result": result.model_dump(mode="json")})
        self._event(lease.run_id, "sandbox.exec.result", result.model_dump(mode="json"), operation_id)
        return result

    def _source_paths(self, lease: WorkspaceLease) -> frozenset[str]:
        manifest = self.store.get_json(self._lease_source_manifest(lease))
        if type(manifest) is not dict or type(manifest.get("files")) is not list:
            raise SandboxBoundaryError("Source manifest artifact is malformed")
        paths = []
        for item in manifest["files"]:
            if type(item) is not dict or type(item.get("path")) is not str:
                raise SandboxBoundaryError("Source manifest file list is malformed")
            paths.append(item["path"])
        return frozenset(paths)

    def _remote_stat_hash(self, lease: WorkspaceLease, relative_path: str, observation: str) -> tuple[int, str]:
        remote = self.profile.workspace_root.rstrip("/") + "/" + relative_path
        stat_result = self.execute(lease, ("stat", "--printf=%F %s", "--", remote),
                                   _operation_id("read-stat", lease.sandbox_id, relative_path, observation), workdir=self.profile.workspace_root)
        if stat_result.status != "completed" or stat_result.exit_code != 0:
            raise SandboxBoundaryError("Native stat refused the requested opaque file")
        parts = stat_result.stdout.strip().rsplit(" ", 1)
        if len(parts) != 2 or parts[0] != "regular file" or not parts[1].isdigit():
            raise SandboxBoundaryError("Requested remote path is not a regular file")
        size = int(parts[1])
        hash_result = self.execute(lease, ("sha256sum", "--", remote),
                                   _operation_id("read-hash", lease.sandbox_id, relative_path, observation), workdir=self.profile.workspace_root)
        match = re.fullmatch(r"([0-9a-f]{64})  .+\n?", hash_result.stdout)
        if hash_result.status != "completed" or hash_result.exit_code != 0 or match is None:
            raise SandboxBoundaryError("Native file hash receipt is invalid")
        return size, match.group(1)

    def _collect_file(self, lease: WorkspaceLease, relative_path: str, max_bytes: int, *, permitted: Iterable[str]) -> bytes:
        confined_path(relative_path)
        permitted_set = frozenset(permitted)
        if relative_path not in permitted_set:
            raise SandboxBoundaryError("Remote collection is restricted to a frozen source/report allowlist")
        if not isinstance(max_bytes, int) or not 1 <= max_bytes <= min(self.config.budget.max_output_bytes, 4 * 1024 * 1024):
            raise ValueError("Opaque native file collection max_bytes is outside the configured bound")
        request = {"lease": lease.model_dump(mode="json"), "path": relative_path, "max_bytes": max_bytes,
                   "allowlist_sha256": digest(sorted(permitted_set))}
        operation_id = _operation_id("download", lease.sandbox_id, digest(request))
        claim = self.store.claim_operation(operation_id, digest(request))
        if claim == "recorded":
            recorded = self.store.operation(operation_id) or {}
            try:
                return self.store.get(ArtifactRef.model_validate(recorded["artifact"]))
            except Exception as error:
                raise SandboxBoundaryError("Recorded native file collection receipt is malformed") from error
        if claim == "uncertain":
            raise SandboxBoundaryError("Native download effect is uncertain and will not be replayed")
        self._assert_lease(lease)
        self._event(lease.run_id, "sandbox.download.intent", request, operation_id)
        destination = self._download_root / operation_id.replace(".", "-")
        try:
            destination.mkdir(mode=0o700)
            before_size, before_hash = self._remote_stat_hash(lease, relative_path, operation_id + ".before")
            if before_size > max_bytes:
                raise SandboxBoundaryError("Remote regular file exceeds its predeclared byte bound")
            remote = self.profile.workspace_root.rstrip("/") + "/" + relative_path
            downloaded = self._invoke_cli("sandbox", "download", lease.name, remote, str(destination), timeout=60,
                                          output_limit=_MAX_CLI_OUTPUT, file_size_limit=max_bytes)
            if downloaded.timed_out or downloaded.output_limited or downloaded.returncode != 0:
                raise SandboxBoundaryError("Native file download is incomplete or failed")
            candidate = destination / Path(relative_path).name
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
                raise SandboxBoundaryError("Downloaded object is not a bounded regular non-symlink file")
            fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                with os.fdopen(fd, "rb", closefd=True) as stream:
                    data = stream.read(max_bytes + 1)
            finally:
                # os.fdopen has closed it on the normal path; retain a defensive
                # no-op handling for an exception before its context entry.
                try:
                    os.close(fd)
                except OSError:
                    pass
            if len(data) != info.st_size or len(data) > max_bytes or _sha256(data) != before_hash:
                raise SandboxBoundaryError("Downloaded bytes differ from the confirmed remote pre-transfer hash")
            after_size, after_hash = self._remote_stat_hash(lease, relative_path, operation_id + ".after")
            if (after_size, after_hash) != (before_size, before_hash):
                raise SandboxBoundaryError("Remote file changed during native collection")
            artifact = self.store.put(data, expected_sha256=before_hash)
            receipt = {"artifact": artifact.model_dump(mode="json"), "remote_sha256": before_hash,
                       "remote_size": before_size, "path": relative_path}
            self._complete(operation_id, receipt)
            self._event(lease.run_id, "sandbox.download.result", receipt, operation_id)
            return data
        except Exception as error:
            self._complete(operation_id, {"status": "unknown_effect", "path": relative_path, "detail": str(error)[:2048]})
            raise

    def read_file(self, lease: WorkspaceLease, relative_path: str, max_bytes: int) -> bytes:
        """Collect one exact captured-source regular file with remote hash confirmation."""
        return self._collect_file(lease, relative_path, max_bytes, permitted=self._source_paths(lease))

    def read_predeclared_report(self, lease: WorkspaceLease, relative_path: str, max_bytes: int = _MAX_REPORT_BYTES) -> bytes:
        """Internal native-test path: collect only its frozen recipe report path."""
        return self._collect_file(lease, relative_path, max_bytes, permitted=(relative_path,))

    def inspect(self, lease: WorkspaceLease) -> dict[str, Any]:
        current = self._assert_lease(lease, require_ready=False)
        return {"sandbox_id": current.id, "name": current.name, "workspace": current.workspace,
                "phase": _phase(current), "labels": dict(current.labels), "image": lease.image,
                "policy_sha256": lease.policy_sha256, "profile_sha256": self._profile_digest}

    def release(self, lease: WorkspaceLease) -> str:
        """Delete only the currently verified UUID; never retry an uncertain delete."""
        operation_id = _operation_id("delete", lease.run_id, str(lease.generation), lease.sandbox_id)
        request = {"lease": lease.model_dump(mode="json"), "workspace": self.profile.workspace}
        claim = self.store.claim_operation(operation_id, digest(request))
        if claim == "recorded":
            return str((self.store.operation(operation_id) or {}).get("cleanup", "unknown"))
        if claim == "uncertain":
            # Inspection may establish that the exact object disappeared, but a
            # still-present object is deliberately not deleted a second time.
            try:
                with self._sdk() as client:
                    current = client.get(lease.name, workspace=self.profile.workspace)
                cleanup = "unknown" if current.id == lease.sandbox_id else "confirmed"
            except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                cleanup = "confirmed" if _is_not_found(error) else "unknown"
            self._complete(operation_id, {"cleanup": cleanup, "reconciled": True})
            return cleanup
        self._event(lease.run_id, "sandbox.delete.intent", request, operation_id)
        cleanup = "unknown"
        try:
            self._assert_lease(lease, require_ready=False)
            with self._sdk() as client:
                deletion = client.delete(lease.name, workspace=self.profile.workspace, allow_missing=False)
                if deletion.sandbox_id != lease.sandbox_id:
                    raise SandboxBoundaryError("Native delete did not acknowledge the leased sandbox UUID")
                if deletion.outcome in (DeletionOutcome.COMPLETED, DeletionOutcome.ALREADY_ABSENT):
                    cleanup = "confirmed"
                elif deletion.outcome == DeletionOutcome.ACCEPTED:
                    try:
                        client.wait_deleted(lease.name, workspace=self.profile.workspace, expected_sandbox_id=lease.sandbox_id,
                                            timeout_seconds=60)
                        try:
                            replacement = client.get(lease.name, workspace=self.profile.workspace)
                            cleanup = "unknown" if replacement.id != lease.sandbox_id else "pending"
                        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                            cleanup = "confirmed" if _is_not_found(error) else "unknown"
                    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                        cleanup = "pending"
                else:
                    cleanup = "unknown"
        except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
            cleanup = "unknown"
        receipt = {"cleanup": cleanup, "sandbox_id": lease.sandbox_id}
        self._complete(operation_id, receipt)
        self._event(lease.run_id, "sandbox.delete.result", receipt, operation_id)
        self._known_leases.pop((lease.run_id, lease.generation), None)
        return cleanup

    def reconcile(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """Inspect persisted ownership after restart and clean newly recovered leases.

        An uncertain workload command or deletion is never redispatched. A
        first deletion is permitted only after exact persisted labels and any
        previously recorded UUID match the currently observed object.
        """
        results: list[dict[str, Any]] = []
        run_ids = [run_id] if run_id is not None else [r["run_id"] for r in self.store.runs()]
        for logical_id in run_ids:
            intents = [e["payload"] for e in self.store.events(logical_id) if e["kind"] == "sandbox.create.intent"]
            for intent in intents:
                result = {"run_id": logical_id, "name": intent.get("name"), "cleanup": "unknown",
                          "state": "unknown_effect", "runtime_gc": "not_established"}
                try:
                    generation = int(intent["labels"]["corsair.generation"])
                    manifest = ArtifactRef.model_validate(intent["source_manifest"])
                    if (intent["name"] != self._name(logical_id, generation) or
                            intent["labels"] != self._labels(logical_id, generation, manifest) or
                            intent["image"] != self.profile.image or intent["policy_sha256"] != self._policy_sha256):
                        raise SandboxBoundaryError("Reconciliation requires the original exact operator profile")
                    receipt = self.store.operation(_operation_id("create", logical_id, str(generation))) or {}
                    prior = WorkspaceLease.model_validate(receipt["lease"]) if receipt.get("lease") else None
                    with self._sdk() as client:
                        try:
                            current = client.get(intent["name"], workspace=self.profile.workspace)
                        except Exception as error:
                            if not _is_not_found(error):
                                raise
                            current = None
                    result["generation"] = generation
                    if current is None:
                        result.update(state="gateway_absent", cleanup="confirmed", sandbox_id=prior.sandbox_id if prior else None)
                    else:
                        if (current.name != intent["name"] or current.workspace != self.profile.workspace or
                                dict(current.labels) != intent["labels"] or (prior and current.id != prior.sandbox_id)):
                            raise SandboxBoundaryError("Observed resource does not match the persisted UUID/ownership claim")
                        lease = prior or WorkspaceLease(name=current.name, sandbox_id=current.id, run_id=logical_id,
                            generation=generation, image=self.profile.image, policy_sha256=self._policy_sha256)
                        result["sandbox_id"] = lease.sandbox_id
                        _operation_id("delete", logical_id, str(generation), lease.sandbox_id)
                        if any(e["kind"] == "sandbox.delete.intent" and e["payload"].get("lease", {}).get("sandbox_id") == lease.sandbox_id
                               for e in self.store.events(logical_id)):
                            # Persisted dispatch may still be running remotely.
                            # Inspect only; do not issue another delete request.
                            result.update(state="delete_pending_or_unknown", cleanup="pending")
                        else:
                            self._event(logical_id, "sandbox.lease.recovered", {"lease": lease.model_dump(mode="json")},
                                        _operation_id("recover-lease", lease.sandbox_id))
                            result.update(state="first_identity_checked_cleanup", cleanup=self.release(lease))
                except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                    result["detail"] = f"{type(error).__name__}/{_error_code(error)}: {str(error)[:1024]}"
                self._event(logical_id, "sandbox.reconcile.result", result,
                            _operation_id("reconcile-observation", digest(result)))
                results.append(result)
        return results

    def health(self) -> dict[str, Any]:
        """Report actual local prerequisites and native health without claiming readiness."""
        cli = _run_bounded((str(self._cli), "--version"), timeout=10, output_limit=4096)
        cli_version = _bounded_text(cli.stdout, 1024).strip() if cli.returncode == 0 else None
        self._cli_version = cli_version
        health: dict[str, Any] = {"sdk_version": SDK_VERSION, "expected_release": _OPEN_SHELL_VERSION,
                                  "cli_version": cli_version, "cli_sha256": self._cli_sha256,
                                  "gateway": self._gateway, "policy_sha256": self._policy_sha256,
                                  "image": self.profile.image, "workspace": self.profile.workspace,
                                  "prerequisites": {"cli_aligned": cli_version == f"openshell {_OPEN_SHELL_VERSION}",
                                                    "policy_regular": True, "registered_gateway": self._gateway,
                                                    "kvm_present": Path("/dev/kvm").exists()},
                                  "qualified": False}
        try:
            with self._sdk() as client:
                native = client.health()
            # The health protobuf shape is intentionally not a public Corsair
            # contract; retain only its ordinary public fields when present.
            health["gateway_version"] = str(getattr(native, "version", "")) or None
            health["gateway_healthy"] = True
        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
            health["gateway_healthy"] = False
            health["gateway_error"] = f"{type(error).__name__}/{_error_code(error)}: {str(error)[:1024]}"
        health["qualified"] = self.qualified()
        return health

    def profile_identity(self) -> dict[str, Any]:
        """Return the frozen profile identity used in all lifecycle receipts."""
        return {"profile_sha256": self._profile_digest, "name": self.profile.name, "workspace": self.profile.workspace,
                "workspace_root": self.profile.workspace_root, "gateway": self._gateway, "image": self.profile.image,
                "policy_sha256": self._policy_sha256, "sdk_version": SDK_VERSION, "cli_sha256": self._cli_sha256,
                "expected_release": _OPEN_SHELL_VERSION}

    def qualified(self) -> bool:
        """Validate a frozen, effective-policy-bound native qualification certificate.

        A Docker/local profile has no implicit certificate.  A certificate must
        bind the exact SDK, CLI hash, profile, image, base-policy and *observed*
        effective-policy/runtime identities; presence of a file or a version
        string alone cannot make the backend qualified.
        """
        path_value = self.profile.qualification_path
        if not path_value:
            return False
        path = Path(path_value).expanduser()
        try:
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > 1024 * 1024:
                return False
            certificate = json.loads(path.read_bytes())
        except (OSError, ValueError, UnicodeError):
            return False
        if type(certificate) is not dict or certificate.get("qualified") is not True:
            return False
        required = {"sdk_version": SDK_VERSION, "cli_sha256": self._cli_sha256,
                    "profile_sha256": self._profile_digest, "image": self.profile.image,
                    "policy_sha256": self._policy_sha256}
        if any(certificate.get(key) != value for key, value in required.items()):
            return False
        return (isinstance(certificate.get("effective_policy_sha256"), str)
                and bool(re.fullmatch(r"[0-9a-f]{64}", certificate["effective_policy_sha256"]))
                and isinstance(certificate.get("runtime"), dict)
                and all(isinstance(certificate["runtime"].get(key), str) and certificate["runtime"][key]
                        for key in ("gateway_version", "supervisor_image", "runtime_image", "kernel")))
