"""OpenShell TestWorkspace: fresh sandbox, captured source plus one approved patch, exact remote admission.

Delivery reuses the qualified fixed source-arrival recipe (SPEC-0011): one private host staging copy,
one native CLI directory upload that is never replayed, then a fixed operator verifier whose inventory
the host compares exactly with the captured snapshot and the patch. Bounded to small trees: general
source delivery waits on SPEC-0025 fetch and a qualified storage quota (ISSUE-0006). No retries.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import time
from typing import Literal, Protocol
from uuid import UUID, uuid5

from corsair.adapters.git_source import confined_path
from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.artifacts import ArtifactRef, ArtifactStore, SourceSnapshot
from corsair.ports.execution import ExecutionError, ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle, SandboxLifecycle
from corsair.ports.test_runner import ApprovedPatch, PreparedWorkspace

MAX_TREE_FILES = 64
MAX_TREE_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MODES = {'100644': 0o400, '100755': 0o500}

# Trusted operator verifier: reads, never imports or executes, workspace content. It reports; the host
# decides. argv: root, maximum entries, maximum file bytes. Absent root reports exists=false.
VERIFY = r'''import hashlib,json,os,stat,sys
root,limit,cap=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
out=dict(exists=os.path.lexists(root),euid=os.geteuid())
if out['exists']:
 s=os.lstat(root);out['root']=[stat.S_IMODE(s.st_mode),s.st_uid,stat.S_ISDIR(s.st_mode),os.path.realpath(root)==root]
 files,dirs,other,n={},{},[],0
 if out['root'][2]:
  for cur,ds,names in os.walk(root,followlinks=False):
   for name in sorted(ds)+sorted(names):
    n+=1
    if n>limit:break
    p=os.path.join(cur,name);rel=os.path.relpath(p,root);s=os.lstat(p)
    if stat.S_ISDIR(s.st_mode):dirs[rel]=[stat.S_IMODE(s.st_mode),s.st_uid]
    elif stat.S_ISREG(s.st_mode):
     fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
     with os.fdopen(fd,'rb') as f:
      t=os.fstat(f.fileno());data=f.read(cap+1)
     files[rel]=[stat.S_IMODE(t.st_mode),t.st_uid,t.st_nlink,len(data),hashlib.sha256(data).hexdigest()]
    else:other.append(rel)
   if n>limit:break
 out.update(files=files,directories=dirs,other=other,truncated=n>limit)
print(json.dumps(out,sort_keys=True))
'''


@dataclass(frozen=True)
class WorkspaceConfig:
    """Operator-owned placement and bounds; the remote root becomes the runner's workspace root."""
    staging: Path
    remote_parent: str
    root_name: str
    python: str
    max_files: int = MAX_TREE_FILES
    max_bytes: int = MAX_TREE_BYTES

    def __post_init__(self):
        for path in (self.remote_parent, self.python):
            if (type(path) is not str or not path.startswith('/') or path.endswith('/') or '\0' in path
                    or str(PurePosixPath(path)) != path or '..' in PurePosixPath(path).parts):
                raise ValueError('Canonical absolute operator paths required')
        if type(self.root_name) is not str or not self.root_name or '/' in self.root_name or self.root_name in ('.', '..'):
            raise ValueError('Single plain workspace root name required')
        if not isinstance(self.staging, Path) or not self.staging.is_absolute():
            raise ValueError('Absolute host staging directory required')
        if not (type(self.max_files) is int and 1 <= self.max_files <= MAX_TREE_FILES
                and type(self.max_bytes) is int and 1 <= self.max_bytes <= MAX_TREE_BYTES):
            raise ValueError('Workspace bounds outside the admitted fixture range')

    @property
    def remote_root(self) -> str:
        return f'{self.remote_parent}/{self.root_name}'


class UploadError(RuntimeError):
    """A failed or unacknowledged upload; the native CLI may already have mutated the sandbox."""
    def __init__(self, detail: str, delivery: Literal['not_dispatched', 'unknown']):
        self.delivery = delivery
        super().__init__(detail)


class DirectoryUpload(Protocol):
    def upload(self, handle: SandboxHandle, local: Path, remote_parent: str, operation: UUID) -> None: ...


class CliUpload:
    """Pinned native `openshell sandbox upload`; the curated SDK has no transfer methods (ISSUE-0006).

    The CLI retries whole operations internally; this adapter never adds an outer retry and treats any
    unacknowledged result as unknown delivery, so the caller discards the sandbox.
    """
    def __init__(self, binary: Path, binary_sha256: str, *, gateway: str, env: dict[str, str],
                 timeout_seconds: int, receipts: Path):
        if not binary.is_absolute() or not gateway or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise ValueError('Absolute pinned binary, gateway name and bounded timeout required')
        if any(type(k) is not str or type(v) is not str for k, v in env.items()):
            raise ValueError('Explicit string environment required')
        self._binary, self._sha256, self._gateway = binary, binary_sha256, gateway
        self._env, self._timeout = dict(env), timeout_seconds
        self._journal = ReceiptDirectory(receipts)

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def upload(self, handle: SandboxHandle, local: Path, remote_parent: str, operation: UUID) -> None:
        argv = [str(self._binary), '--gateway', self._gateway, '--workspace', handle.workspace, 'sandbox', 'upload',
                '--no-git-ignore', handle.name, str(local), remote_parent]
        receipt = dict(operation=str(operation), handle=asdict(handle), argv=argv, delivery='not_dispatched',
                       started_at=datetime.now(timezone.utc).isoformat(), application_retries=0,
                       native_internal_attempts='unknown')
        self._journal.write(operation, 'intent', receipt)
        started = time.monotonic()
        try:
            if hashlib.sha256(self._binary.read_bytes()).hexdigest() != self._sha256:
                raise UploadError('native CLI binary differs from its pin', 'not_dispatched')
            receipt['delivery'] = 'unknown'
            try:
                done = subprocess.run(argv, capture_output=True, timeout=self._timeout, env=self._env)
            except subprocess.TimeoutExpired as error:
                receipt.update(timed_out=True, stderr=(error.stderr or b'')[-2048:].decode('utf-8', 'replace'))
                raise UploadError('native upload timed out; remote mutation unknown', 'unknown') from error
            receipt.update(exit_code=done.returncode, stdout=done.stdout[-2048:].decode('utf-8', 'replace'),
                           stderr=done.stderr[-2048:].decode('utf-8', 'replace'))
            if done.returncode != 0:
                raise UploadError(f'native upload exit {done.returncode}; remote mutation unknown', 'unknown')
            receipt['delivery'] = 'acknowledged'
        except UploadError as error:
            receipt.update(error_type='UploadError', error_detail=str(error), delivery=error.delivery)
            raise
        except Exception as error:
            receipt.update(error_type=type(error).__name__, error_detail=str(error))
            raise UploadError(f'{type(error).__name__}: {error}', receipt['delivery']) from error
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - started
            self._journal.write(operation, 'result', receipt)


class WorkspaceError(RuntimeError):
    """Preparation refused; `cleanup` says whether the created sandbox is confirmed deleted."""
    def __init__(self, layer: Literal['staging', 'sandbox', 'upload', 'admission'], detail: str,
                 cleanup: Literal['not_required', 'confirmed', 'unconfirmed'], receipt: ExecutionReceipt | None = None):
        self.layer, self.detail, self.cleanup, self.receipt = layer, detail, cleanup, receipt
        super().__init__(f'{layer}: {detail}; cleanup {cleanup}')


def _patch_manifest(patch: ApprovedPatch, refs: dict[str, ArtifactRef]) -> bytes:
    files = [dict(path=f.path, sha256=refs[f.path].sha256, size=refs[f.path].size)
             for f in sorted(patch.files, key=lambda f: f.path)]
    return (json.dumps(dict(version=1, patch_sha256=patch.sha256, files=files), sort_keys=True,
                       separators=(',', ':')) + '\n').encode()


class OpenShellTestWorkspace:
    """One adapter per captured source revision; each `prepare` creates a fresh sandbox."""
    __test__ = False

    def __init__(self, lifecycle: SandboxLifecycle, execution: SandboxExecution, upload: DirectoryUpload,
                 store: ArtifactStore, snapshot: SourceSnapshot, config: WorkspaceConfig):
        if not isinstance(config, WorkspaceConfig) or not isinstance(snapshot, SourceSnapshot):
            raise ValueError('Operator workspace configuration and captured snapshot required')
        if any(f.mode not in MODES for f in snapshot.files):
            raise ValueError('Only regular captured files are admitted')
        if len(snapshot.files) >= config.max_files or sum(f.artifact.size for f in snapshot.files) > config.max_bytes:
            raise ValueError('Captured source exceeds the fixture workspace bound')
        for f in snapshot.files:
            confined_path(f.path)
        self._lifecycle, self._execution, self._upload = lifecycle, execution, upload
        self._store, self._snapshot, self._config = store, snapshot, config

    def _expected(self, patch: ApprovedPatch):
        source = {f.path: (MODES[f.mode], f.artifact.size, f.artifact.sha256) for f in self._snapshot.files}
        tests = {f.path: (0o400, len(f.content), hashlib.sha256(f.content).hexdigest()) for f in patch.files}
        files = source | tests
        parents = {'/'.join(p.split('/')[:n]) for p in files for n in range(1, p.count('/') + 1)}
        if source.keys() & tests.keys() or files.keys() & parents:
            raise ValueError('Patch paths overlap captured source')
        if len(files) + len(parents) > self._config.max_files or sum(v[1] for v in files.values()) > self._config.max_bytes:
            raise ValueError('Workspace exceeds the fixture bound')
        return files, parents

    def _stage(self, operation: UUID, patch: ApprovedPatch, parents) -> tuple[Path, Path]:
        base = self._config.staging / operation.hex
        base.mkdir(mode=0o700)
        try:
            return base, self._write(base, patch, parents)
        except BaseException:
            shutil.rmtree(base, ignore_errors=True)
            raise

    def _write(self, base: Path, patch: ApprovedPatch, parents) -> Path:
        root = base / self._config.root_name
        root.mkdir(mode=0o700)
        for parent in sorted(parents):
            (root / parent).mkdir(mode=0o700)
        content = {f.path: (MODES[f.mode], self._store.get(f.artifact)) for f in self._snapshot.files}
        content |= {f.path: (0o400, f.content) for f in patch.files}
        for path, (mode, data) in sorted(content.items()):
            fd = os.open(root / path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
        return root

    def _observe(self, handle: SandboxHandle, operation: UUID) -> tuple[dict, ExecutionReceipt]:
        argv = (self._config.python, '-I', '-S', '-B', '-c', VERIFY, self._config.remote_root,
                str(self._config.max_files), str(MAX_FILE_BYTES))
        try:
            receipt = self._execution.execute(handle, argv, operation)
        except ExecutionError as error:
            raise WorkspaceError('sandbox', f'verifier: {error}', 'unconfirmed', error.receipt) from error
        if (receipt.operation != str(operation) or receipt.handle != handle or receipt.delivery != 'acknowledged'
                or receipt.completion != 'terminal_observed' or receipt.native_exit != 0 or receipt.stderr):
            raise WorkspaceError('sandbox', f'verifier incomplete: exit {receipt.native_exit} reason {receipt.reason}',
                                 'unconfirmed', receipt)
        try:
            observed = json.loads(receipt.stdout)
        except ValueError:
            observed = None
        if not isinstance(observed, dict):
            raise WorkspaceError('admission', 'verifier output is not one JSON object', 'unconfirmed', receipt)
        return observed, receipt

    def _admit(self, observed: dict, files, parents) -> None:
        euid = observed.get('euid')
        want = dict(exists=True, euid=euid, root=[0o700, euid, True, True], other=[], truncated=False,
                    files={p: [m, euid, 1, s, h] for p, (m, s, h) in files.items()},
                    directories={p: [0o700, euid] for p in parents})
        if type(euid) is not int or observed != want:
            differs = sorted(k for k in want.keys() | observed.keys() if observed.get(k) != want.get(k))
            raise ValueError('remote workspace differs from captured source and patch: ' + ', '.join(differs))

    def prepare(self, patch: ApprovedPatch, operation: UUID) -> PreparedWorkspace:
        if not isinstance(operation, UUID) or not isinstance(patch, ApprovedPatch):
            raise ValueError('Operator operation and approved patch required')
        files, parents = self._expected(patch)
        refs = {f.path: self._store.put(f.content) for f in patch.files}
        tests = self._store.put(_patch_manifest(patch, refs))
        try:
            base, root = self._stage(operation, patch, parents)
        except Exception as error:
            raise WorkspaceError('staging', f'{type(error).__name__}: {error}', 'not_required') from error
        handle = None
        try:
            try:
                handle = self._lifecycle.create(uuid5(operation, 'create'))
                self._lifecycle.wait_ready(handle, uuid5(operation, 'ready'))
            except Exception as error:
                raise WorkspaceError('sandbox', f'{type(error).__name__}: {error}', 'unconfirmed') from error
            before, receipt = self._observe(handle, uuid5(operation, 'absent'))
            if before != dict(exists=False, euid=before.get('euid')):
                raise WorkspaceError('admission', 'remote workspace root exists before upload', 'unconfirmed', receipt)
            try:
                self._upload.upload(handle, root, self._config.remote_parent, uuid5(operation, 'upload'))
            except UploadError as error:
                raise WorkspaceError('upload', f'{error} (delivery {error.delivery})', 'unconfirmed') from error
            observed, receipt = self._observe(handle, uuid5(operation, 'verify'))
            try:
                self._admit(observed, files, parents)
            except ValueError as error:
                raise WorkspaceError('admission', str(error), 'unconfirmed', receipt) from error
            return PreparedWorkspace(handle, self._snapshot.manifest, tests, patch.sha256)
        except Exception as error:
            failure = error if isinstance(error, WorkspaceError) else WorkspaceError(
                'sandbox', f'{type(error).__name__}: {error}', 'unconfirmed')
            # Without a handle, create may still have dispatched: cleanup stays unconfirmed.
            failure.cleanup = self._delete(handle, uuid5(operation, 'discard')) if handle is not None else 'unconfirmed'
            if failure is error:
                raise
            raise failure from error
        finally:
            # The CLI has exited; the authoritative bytes stay in the store, never in staging.
            shutil.rmtree(base, ignore_errors=True)

    def _delete(self, handle: SandboxHandle, operation: UUID) -> Literal['confirmed', 'unconfirmed']:
        try:
            self._lifecycle.delete(handle, operation)
        except Exception:
            return 'unconfirmed'
        return 'confirmed'

    def release(self, workspace: PreparedWorkspace, operation: UUID) -> Literal['confirmed', 'unconfirmed']:
        return self._delete(workspace.handle, uuid5(operation, 'release'))
