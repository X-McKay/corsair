"""SPEC-0070: the environment stage's sandbox on OpenShell, one adapter per case.

`prepare` places the host-captured source of the case's commit in a fresh sandbox of the selected toolchain's
prepared image (the qualified `OpenShellTestWorkspace` upload and in-sandbox verification), then applies the
dependency-setup network policy (SPEC-0026) before the agent's first command. Each step runs once; any failure
discards the sandbox (never repaired in place) and raises `PreparationRefused` with its layer. Everything here
is operator configuration; nothing comes from the agent.
"""
from collections.abc import Callable, Mapping
from dataclasses import asdict
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

Cleanup = Literal['confirmed', 'unconfirmed']


class SourceWorkspace(Protocol):
    """`OpenShellTestWorkspace` over one captured revision and one image."""
    def prepare_source(self, operation: UUID) -> SandboxHandle: ...
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

    def prepare(self, toolchain: Toolchain, operation: UUID) -> PreparedSandbox:
        if not isinstance(operation, UUID):
            raise ValueError('Operation must be a UUID')
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
        try:
            handle = workspace.prepare_source(uuid5(operation, 'source'))
        except WorkspaceError as error:
            # The workspace discarded its own sandbox and says whether that was confirmed.
            raise PreparationRefused(error.layer, error.detail, error.cleanup) from error
        except Exception as error:
            raise PreparationRefused('sandbox', f'{type(error).__name__}: {error}'[:2048], 'unconfirmed') from error
        try:
            # Journaled before anything else, so `sweep` can find a sandbox a lost worker left.
            self._journal.write(operation, 'prepared', dict(handle=asdict(handle), image=toolchain.image))
            self._policy.apply(handle, dependency, 'dependency_setup', uuid5(operation, 'dependency-policy'))
        except Exception as error:
            layer = 'policy' if isinstance(error, PolicyError) else 'sandbox'
            cleanup = self._release(workspace, handle, uuid5(operation, 'discard'))
            raise PreparationRefused(layer, f'{type(error).__name__}: {error}'[:2048], cleanup) from error
        self._live[handle.id] = workspace
        return PreparedSandbox(self._execution, handle, self._scratch, self._read_source)

    def _read_source(self, path: str) -> bytes | None:
        """The captured bytes of one file of the revision placed in the sandbox, from the operator's store."""
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
        """Delete every journaled sandbox this adapter prepared and never saw released, by its original handle.

        For the operator after a lost worker; the run already recorded its cleanup as unconfirmed."""
        outcome: dict[str, Cleanup] = {}
        for prepared in sorted(self._receipts.glob('*.prepared.json')):
            operation = UUID(prepared.name.split('.', 1)[0])
            released = self._receipts / f'{operation}.released.json'
            if released.exists() and json.loads(released.read_text())['cleanup'] == 'confirmed':
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
