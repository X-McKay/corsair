"""A deterministic host double of the OpenShell gateway: the ``SandboxClient`` subset the v2 backend calls and the
pinned CLI's policy commands. It returns the SDK's own types (``SandboxRef``, ``ExecChunk``, ``ExecResult``,
``DeletionResult``) and raises ``grpc.RpcError`` with real status codes, so the adapter's logic is exercised offline.

It does not run commands: every exec is answered by ``handler`` (default: exit 0, no output), which tests replace to
script outcomes. So it cannot honestly run the shared ``Sandboxes`` conformance suite, only adapter-logic tests.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import grpc
import yaml
from openshell import DeletionOutcome, DeletionResult, ExecChunk, ExecResult, SandboxError, SandboxRef
from openshell._proto import openshell_pb2
from openshell.sandbox import SandboxStatusRef

READY = openshell_pb2.SANDBOX_PHASE_READY
PROVISIONING = openshell_pb2.SANDBOX_PHASE_PROVISIONING
ERROR = openshell_pb2.SANDBOX_PHASE_ERROR


class FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode, details: str = ""):
        super().__init__(details or code.name)
        self._code, self._details = code, details or code.name

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details


@dataclass
class ExecCall:
    sandbox: str
    command: list[str]
    workdir: str | None
    env: dict[str, str]
    stdin: bytes
    timeout_seconds: int | None
    no_login_shell: bool


@dataclass
class Outcome:
    """What one exec observes. ``error`` is raised after the output (a transport failure after dispatch);
    ``elapsed`` advances the gateway clock; ``gone`` deletes the sandbox while the command runs."""

    exit_code: int | None = 0
    stdout: bytes = b""
    stderr: bytes = b""
    error: BaseException | None = None
    elapsed: float = 0.0
    gone: bool = False


@dataclass
class FakeSandbox:
    id: str
    name: str
    labels: dict[str, str]
    spec: openshell_pb2.SandboxSpec
    phase: int = READY
    revisions: list[dict] = field(default_factory=list)


class FakeGateway:
    """One workspace's sandboxes, in memory. ``calls`` records every SDK and CLI call in order."""

    def __init__(self, workspace: str = "corsair-test"):
        self.workspace = workspace
        self.sandboxes: dict[str, FakeSandbox] = {}
        self.calls: list[tuple] = []
        self.execs: list[ExecCall] = []
        self.handler: Callable[[ExecCall], Outcome] = lambda call: Outcome()
        self.now = 0.0
        self._ids = 0
        # Knobs for failure tests.
        self.create_error: BaseException | None = None
        self.ready_phase = READY
        self.delete_outcome = DeletionOutcome.ACCEPTED
        self.delete_id: str | None = None  # None: the deleted sandbox's own id
        self.survives_delete = False
        self.policy_status = "loaded"
        self.policy_override: dict | None = None
        self.shown_image: str | None = None

    # --- helpers ---

    def clock(self) -> float:
        return self.now

    def _check_workspace(self, workspace: str) -> None:
        assert workspace == self.workspace, f"wrong workspace {workspace!r}"

    def _ref(self, box: FakeSandbox) -> SandboxRef:
        return SandboxRef(id=box.id, name=box.name, workspace=self.workspace,
                          status=SandboxStatusRef(phase=box.phase, current_policy_version=len(box.revisions)),
                          labels=dict(box.labels))

    def _box(self, name: str) -> FakeSandbox:
        if name not in self.sandboxes:
            raise FakeRpcError(grpc.StatusCode.NOT_FOUND, f"sandbox {name} not found")
        return self.sandboxes[name]

    def replace(self, name: str) -> str:
        """Someone else deletes and recreates the name: same labels, a new id."""
        self._ids += 1
        self.sandboxes[name].id = f"replacement-{self._ids}"
        return self.sandboxes[name].id

    # --- the SandboxClient subset ---

    def create(self, *, workspace: str, spec: openshell_pb2.SandboxSpec | None = None, name: str | None = None,
               labels: Mapping[str, str] | None = None) -> SandboxRef:
        self._check_workspace(workspace)
        self.calls.append(("create", name))
        if self.create_error is not None:
            raise self.create_error
        if name in self.sandboxes:
            raise FakeRpcError(grpc.StatusCode.ALREADY_EXISTS, f"sandbox {name} already exists")
        self._ids += 1
        box = FakeSandbox(id=f"sandbox-id-{self._ids}", name=name or f"generated-{self._ids}",
                          labels=dict(labels or {}), spec=spec or openshell_pb2.SandboxSpec(), phase=PROVISIONING)
        self.sandboxes[box.name] = box
        return self._ref(box)

    def get(self, name: str, *, workspace: str) -> SandboxRef:
        self._check_workspace(workspace)
        self.calls.append(("get", name))
        return self._ref(self._box(name))

    def list_all(self, *, workspace: str, label_selector: str | None = None) -> list[SandboxRef]:
        self._check_workspace(workspace)
        self.calls.append(("list_all", label_selector))
        wanted = dict(part.split("=", 1) for part in (label_selector or "").split(",") if part)
        return [self._ref(box) for box in self.sandboxes.values()
                if all(box.labels.get(key) == value for key, value in wanted.items())]

    def wait_ready(self, name: str, *, workspace: str, timeout_seconds: float = 300.0) -> SandboxRef:
        self._check_workspace(workspace)
        self.calls.append(("wait_ready", name, timeout_seconds))
        box = self._box(name)
        box.phase = self.ready_phase
        if box.phase == ERROR:
            raise SandboxError(f"sandbox {name} entered error phase")
        if box.phase != READY:
            raise SandboxError(f"sandbox {name} was not ready within timeout")
        return self._ref(box)

    def delete(self, name: str, *, workspace: str, allow_missing: bool = False) -> DeletionResult:
        self._check_workspace(workspace)
        self.calls.append(("delete", name))
        box = self._box(name)
        if not self.survives_delete:
            del self.sandboxes[name]
        return DeletionResult(self.delete_outcome, self.delete_id or box.id)

    def wait_deleted(self, name: str, *, workspace: str, timeout_seconds: float = 60.0,
                     expected_sandbox_id: str | None = None) -> None:
        self._check_workspace(workspace)
        self.calls.append(("wait_deleted", name, expected_sandbox_id, timeout_seconds))
        box = self.sandboxes.get(name)
        if box is not None and (expected_sandbox_id is None or box.id == expected_sandbox_id):
            raise SandboxError(f"sandbox {name} was not deleted within timeout")

    def exec_stream(self, sandbox: str, command: Sequence[str], *, workspace: str, workdir: str | None = None,
                    env: Mapping[str, str] | None = None, stdin: bytes | None = None,
                    timeout_seconds: int | None = None, no_login_shell: bool = False):
        self._check_workspace(workspace)
        self.calls.append(("exec_stream", sandbox, tuple(command)))
        call = ExecCall(sandbox, list(command), workdir, dict(env or {}), stdin or b"", timeout_seconds,
                        no_login_shell)
        self.execs.append(call)
        box = self._box(sandbox)
        outcome = self.handler(call)

        def events():
            for index, arg in enumerate(command):  # The live gateway's per-argument cap.
                if len(arg.encode()) > 32768:
                    raise FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT,
                                       f"command argument {index} exceeds 32768 byte limit")
            for start in range(0, len(outcome.stdout), 4096):
                yield ExecChunk(stream="stdout", data=outcome.stdout[start:start + 4096])
            if outcome.stderr:
                yield ExecChunk(stream="stderr", data=outcome.stderr)
            self.now += outcome.elapsed
            if outcome.gone:
                self.sandboxes.pop(box.name, None)
            if outcome.error is not None:
                raise outcome.error
            if outcome.exit_code is None:
                raise SandboxError("ExecSandbox stream ended without an exit event")
            yield ExecResult(exit_code=outcome.exit_code, stdout="", stderr="")

        return events()

    # --- the pinned CLI (policy commands only) ---

    def cli(self, argv: list[str], env: Mapping[str, str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        assert argv[1:3] == ["--gateway", argv[2]] and argv[3] == "--workspace"
        self._check_workspace(argv[4])
        args = argv[5:]
        self.calls.append(("cli", tuple(args)))

        def done(value: dict) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(value).encode(), b"")

        try:
            box = self._box(args[2])
        except FakeRpcError:
            return subprocess.CompletedProcess(argv, 1, b"", b"sandbox not found")
        if args[:2] == ["policy", "set"]:
            assert "--wait" in args
            document = yaml.safe_load(Path(args[args.index("--policy") + 1]).read_text())
            box.revisions.append(document)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        current = self.policy_override if self.policy_override is not None else (
            box.revisions[-1] if box.revisions else {})
        digest = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
        if args[:2] == ["sandbox", "get"]:
            shown = {"id": box.id, "name": box.name, "policy_source": "sandbox", "policy": current,
                     "configuration_admission": {"state": "accepted", "policy_hash": digest}}
            if self.shown_image is not None:
                shown["spec"] = {"template": {"image": self.shown_image}}
            return done(shown)
        if args[:2] == ["policy", "get"]:
            if "--rev" in args:
                return done({"version": int(args[args.index("--rev") + 1]), "status": self.policy_status,
                             "hash": digest, "policy": current})
            return done({"version": len(box.revisions), "hash": digest, "policy": current})
        raise AssertionError(f"unexpected CLI call {args}")

    def policy_sets(self) -> list[tuple]:
        return [call for call in self.calls if call[0] == "cli" and call[1][:2] == ("policy", "set")]
