"""SPEC-0070: the environment stage's sandbox on OpenShell, one adapter per case.

`prepare` places the host-captured source of the case's commit in a fresh sandbox of the selected toolchain's
prepared image (the qualified `OpenShellTestWorkspace` upload and in-sandbox verification), then applies the
dependency-setup network policy (SPEC-0026) before the agent's first command. Each step runs once; any failure
discards the sandbox (never repaired in place) and raises `PreparationRefused` with its layer. Everything here
is operator configuration; nothing comes from the agent.
"""
from collections.abc import Callable, Mapping
from dataclasses import asdict
from functools import partial
import json
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID, uuid4, uuid5

from corsair.adapters.openshell_workspace import WorkspaceError
from corsair.adapters.receipts import ReceiptDirectory
from corsair.agents.environment.contracts import Toolchain
from corsair.composition.direct import PreparationRefused, PreparedSandbox
from corsair.nodes.phase_policy import dependency_policy
from corsair.nodes.source_fetch import WorkspaceBudget, WorkspaceBudgetRefused, admit_workspace_budget, node_free_bytes
from corsair.ports.artifacts import ArtifactStore, SourceSnapshot
from corsair.ports.execution import SandboxExecution
from corsair.ports.sandbox import PolicyError, SandboxHandle, SandboxPolicy
from corsair.ports.test_runner import PatchFile

Cleanup = Literal['confirmed', 'unconfirmed']


class SourceWorkspace(Protocol):
    """`OpenShellTestWorkspace` over one captured revision and one image."""
    def prepare_source(self, operation: UUID, added: tuple[PatchFile, ...] = ()) -> SandboxHandle: ...
    def release_source(self, handle: SandboxHandle, operation: UUID) -> Cleanup: ...


class OpenShellPreparation:
    """`workspace(image)` builds the operator's source workspace for one digest-pinned image over the case's capture;
    `resolvers` names each ecosystem's resolver binaries for the dependency-setup policy."""

    def __init__(self, workspace: Callable[[str], SourceWorkspace], execution: SandboxExecution,
                 policy: SandboxPolicy, *, store: ArtifactStore, snapshot: SourceSnapshot, private_source: bool, base_policy: Mapping,
                 resolvers: Mapping[str, tuple[str, ...]], budget: WorkspaceBudget, scratch_location: str,
                 receipts: Path, free_bytes: Callable[[WorkspaceBudget], int] = node_free_bytes):
        if type(private_source) is not bool or not scratch_location.startswith('/'):
            raise ValueError('Explicit source visibility and absolute scratch location required')
        self._workspace, self._execution, self._policy = workspace, execution, policy
        self._store, self._files = store, {f.path: f.artifact for f in snapshot.files}
        self._snapshot, self._private, self._base, self._resolvers = snapshot, private_source, base_policy, dict(resolvers)
        self._budget, self._scratch, self._free = budget, scratch_location, free_bytes
        self._receipts, self._journal = receipts, ReceiptDirectory(receipts)
        self._live: dict[str, SourceWorkspace] = {}

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def prepare(self, toolchain: Toolchain, operation: UUID, *, overlay: tuple[PatchFile, ...] = ()) -> PreparedSandbox:
        """`overlay`: SPEC-0071 operator files (smoke tests) placed and verified with the captured source."""
        if not isinstance(operation, UUID):
            raise ValueError('Operation must be a UUID')
        added = {}
        for item in overlay:  # PatchFile already confines each path.
            if item.path in self._files or item.path in added:
                raise PreparationRefused('admission', f'overlay path {item.path} is already in the commit',
                                         'not_required')
            added[item.path] = item
        try:
            dependency = dependency_policy(self._base, toolchain.language, self._resolvers.get(toolchain.language, ()),
                                           private_source=self._private)
        except ValueError as error:
            raise PreparationRefused('policy', str(error), 'not_required') from error
        try:
            admit_workspace_budget(self._snapshot, self._budget, self._free(self._budget))
        except WorkspaceBudgetRefused as error:
            raise PreparationRefused(error.layer, error.reason, 'not_required') from error
        workspace = self._workspace(toolchain.image)
        # Intent before any sandbox exists, so a worker lost during creation still leaves a trace for `sweep`.
        try:
            self._journal.write(operation, 'intent', dict(image=toolchain.image,
                                                          source_operation=str(uuid5(operation, 'source'))))
        except Exception as error:
            raise PreparationRefused('host', f'journal: {type(error).__name__}: {error}'[:2048], 'not_required') from error
        try:
            handle = workspace.prepare_source(uuid5(operation, 'source'), tuple(added.values()))
        except WorkspaceError as error:
            # The workspace discarded its own sandbox and says whether that was confirmed.
            self._record(operation, 'unconfirmed' if error.cleanup == 'unconfirmed' else 'confirmed')
            raise PreparationRefused(error.layer, error.detail, error.cleanup) from error
        except Exception as error:
            raise PreparationRefused('sandbox', f'{type(error).__name__}: {error}'[:2048], 'unconfirmed') from error
        try:
            self._journal.write(operation, 'prepared', dict(handle=asdict(handle), image=toolchain.image))
            self._policy.apply(handle, dependency, 'dependency_setup', uuid5(operation, 'dependency-policy'))
        except Exception as error:
            layer = 'policy' if isinstance(error, PolicyError) else 'sandbox'
            cleanup = self._release(workspace, handle, uuid5(operation, 'discard'))
            self._record(operation, cleanup)  # So `sweep` does not delete it a second time.
            raise PreparationRefused(layer, f'{type(error).__name__}: {error}'[:2048], cleanup) from error
        self._live[handle.id] = workspace
        # SPEC-0071: the complete listing of what the operator placed, from the capture and overlay, never the
        # sandbox's view; placement admits at most the workspace's bounded tree, so it is never truncated.
        paths = tuple(sorted(self._files.keys() | added.keys()))
        return PreparedSandbox(self._execution, handle, self._scratch, partial(self._read_source, added),
                               source_paths=lambda: paths)

    def _read_source(self, overlay: Mapping[str, PatchFile], path: str) -> bytes | None:
        """One placed file's bytes from the operator's store or overlay, never from the sandbox."""
        if path in overlay:
            return overlay[path].content
        artifact = self._files.get(path)
        return None if artifact is None else self._store.get(artifact)

    @staticmethod
    def _release(workspace: SourceWorkspace, handle: SandboxHandle, operation: UUID) -> Cleanup:
        try:
            return workspace.release_source(handle, operation)
        except Exception:
            return 'unconfirmed'

    def release(self, sandbox: PreparedSandbox, operation: UUID) -> Cleanup:
        workspace = self._live.pop(sandbox.handle.id, None)
        if workspace is None:
            return 'unconfirmed'
        cleanup = self._release(workspace, sandbox.handle, operation)
        self._record(operation, cleanup)
        return cleanup

    def _record(self, operation: UUID, cleanup: Cleanup) -> None:
        try:
            self._journal.write(operation, 'released', dict(cleanup=cleanup))
        except Exception:
            pass  # The delete receipt is the lifecycle's; this note only lets `sweep` skip the sandbox.

    def sweep(self) -> dict[str, Cleanup]:
        """For the operator after a lost worker, when no worker using this journal is live: delete every journaled
        sandbox this adapter prepared and never saw released, by its original handle.

        A placement journaled as intended but never as prepared has no handle, so it is reported unconfirmed and
        not deleted (only the immutable id confirms a delete); the workspace's lifecycle receipts for its source
        operation name any sandbox it created. The run already recorded its cleanup as unconfirmed."""
        outcome: dict[str, Cleanup] = {}
        for intent in sorted(self._receipts.glob('*.intent.json')):
            operation = UUID(intent.name.split('.', 1)[0])
            released = self._receipts / f'{operation}.released.json'
            if released.exists() and json.loads(released.read_text())['cleanup'] == 'confirmed':
                continue
            prepared = self._receipts / f'{operation}.prepared.json'
            if not prepared.exists():
                outcome[str(operation)] = 'unconfirmed'
                continue
            record = json.loads(prepared.read_text())
            # A fresh delete operation per pass: the lifecycle journal refuses to reuse one.
            outcome[str(operation)] = cleanup = self._release(self._workspace(record['image']),
                                                              SandboxHandle(**record['handle']), uuid4())
            if cleanup == 'confirmed' and released.exists():
                released.unlink()  # An earlier unconfirmed note; this pass replaces it.
            if not released.exists():
                self._record(operation, cleanup)
        return outcome
