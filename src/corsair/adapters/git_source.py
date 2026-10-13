"""Offline raw native Git capture into the independent immutable artifact port."""
import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time
from uuid import UUID

from corsair.adapters.local_artifacts import ArtifactStorageError
from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.artifacts import ArtifactStore, SkippedEntry, SourceFile, SourceSnapshot


@dataclass(frozen=True)
class Executable:
    path: Path
    sha256: str

    def verify(self):
        if not self.path.is_absolute() or not re.fullmatch('[0-9a-f]{64}', self.sha256):
            raise ValueError('Absolute pinned native executable required')
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Pinned executable must be a regular file')
            if hashlib.file_digest(stream, 'sha256').hexdigest() != self.sha256:
                raise ValueError('Native executable digest mismatch')


# Git fsck message ids that concern only the formatting of historical commit and tree objects; their object hashes
# still verify. SPEC-0037 lets an operator accept exactly these in old benchmark history, recorded, never by default.
FORMAT_ONLY_FSCK = frozenset({'badTimezone', 'missingSpaceBeforeEmail', 'zeroPaddedFilemode'})
NONREGULAR_MODES = {'120000': 'symlink', '160000': 'submodule'}


@dataclass(frozen=True)
class SourceLimits:
    max_files: int = 128
    max_file_bytes: int = 1024*1024
    max_total_bytes: int = 4*1024*1024
    wall_seconds: int = 20
    memory_bytes: int = 512*1024*1024
    cpu_seconds: int = 10

    def __post_init__(self):
        if (any(type(v) is not int or v <= 0 for v in asdict(self).values())
                or self.max_files > 65536 or self.max_file_bytes > 16*1024*1024
                or self.max_total_bytes > 256*1024*1024 or self.wall_seconds > 600
                or self.memory_bytes != 512*1024*1024 or self.cpu_seconds > 300):
            raise ValueError('Bounded operator source limits required')


class SourceCaptureError(RuntimeError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__(receipt.get('storage_error') or receipt.get('error_detail') or 'Source capture failed')


def confined_path(path: str):
    parts = path.split('/')
    if (not path or len(path.encode()) > 1024 or any(p in ('', '.', '..') or p.lower()=='.git' for p in parts)
            or '\\' in path or any(ord(c)<32 or ord(c)==127 for c in path)):
        raise ValueError('Canonical relative UTF8 source path required')


def git_hash(kind, data):
    return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()


class GitSource:
    def __init__(self, git: Executable, prlimit: Executable, *, store: ArtifactStore,
                 limits: SourceLimits, receipts: Path, fsck_ignore: frozenset[str] = frozenset(),
                 skip_nonregular: bool = False):
        """`fsck_ignore` (SPEC-0037) accepts only FORMAT_ONLY_FSCK ids; `skip_nonregular` leaves symlinks and
        submodule links out of the snapshot and lists them in the manifest. Both default off and are recorded."""
        if (type(fsck_ignore) is not frozenset or not fsck_ignore <= FORMAT_ONLY_FSCK
                or type(skip_nonregular) is not bool):
            raise ValueError('Only format-only fsck message ids and an explicit skip choice admitted')
        git.verify(); prlimit.verify()
        self._fsck_ignore, self._skip_nonregular = fsck_ignore, skip_nonregular
        self._git_executable, self._prlimit = git, prlimit
        self._store, self._limits = store, limits
        self._journal = ReceiptDirectory(receipts)

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def _native(self, repo, args, cap, deadline, calls, *, allowed=(0,)):
        started = time.monotonic()
        if started >= deadline: raise TimeoutError('Source wall budget exhausted before dispatch')
        argv = [str(self._prlimit.path), f'--as={self._limits.memory_bytes}:{self._limits.memory_bytes}',
                f'--cpu={self._limits.cpu_seconds}:{self._limits.cpu_seconds}', '--',
                str(self._git_executable.path), '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never',
                '-c', 'core.fsmonitor=false',
                *(item for message in sorted(self._fsck_ignore) for item in ('-c', f'fsck.{message}=ignore')),
                '-C', str(repo), *args]
        # Do not inherit caller GIT_*, credentials, transport helpers or config.
        env = {'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C', 'GIT_CONFIG_NOSYSTEM':'1',
               'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_TERMINAL_PROMPT':'0'}
        observation = dict(args=args, pid=None, exit=None, reaped=False, elapsed_seconds=None,
                           stdout_bytes=0, stderr_base64='', reason='start_unknown')
        calls.append(observation)
        out, err = bytearray(), bytearray()
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=env, start_new_session=True)
            observation['pid'] = process.pid
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ, ('stdout', out, cap))
                ready.register(process.stderr, selectors.EVENT_READ, ('stderr', err, 4096))
                while ready.get_map():
                    remaining = deadline-time.monotonic()
                    if remaining <= 0: raise TimeoutError('Source wall budget exhausted')
                    events = ready.select(remaining)
                    if not events: raise TimeoutError('Source native pipe deadline')
                    for key, _ in events:
                        name, retained, limit = key.data
                        data = os.read(key.fd, 8192)
                        if not data:
                            ready.unregister(key.fileobj)
                        else:
                            available = limit-len(retained)
                            retained.extend(data[:available])
                            if len(data) > available: raise ValueError(name+' byte budget exceeded; remainder unknown')
            process.wait(timeout=max(0.001, deadline-time.monotonic()))
            if process.returncode not in allowed: raise RuntimeError('Native Git exit '+str(process.returncode))
            observation['reason'] = 'terminal'
            return bytes(out)
        except Exception as error:
            observation['reason'] = type(error).__name__+': '+str(error)
            raise
        finally:
            if process is not None:
                # No hooks, network protocols or custom helpers are admitted.
                # Kill/reap only this original direct child; no cancellation claim.
                try:
                    if process.returncode is None: process.kill()
                    process.wait(timeout=2)
                    observation.update(exit=process.returncode, reaped=True)
                except Exception as error:
                    observation['cleanup_error'] = f'{type(error).__name__}: {error}'
                finally:
                    process.stdout.close(); process.stderr.close()
            observation.update(elapsed_seconds=time.monotonic()-started, stdout_bytes=len(out),
                               stdout_sha256=hashlib.sha256(out).hexdigest(), stderr_base64=base64.b64encode(err).decode())

    def capture(self, repo: Path, commit: str, operation: UUID) -> SourceSnapshot:
        if (not isinstance(operation, UUID) or not repo.is_absolute() or repo.resolve()!=repo
                or not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}', commit)):
            raise ValueError('Exact SHA1 commit, UUID and canonical absolute operator bare repository required')
        info = repo.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Operator bare repository must be private and user-owned')
        started = time.monotonic(); deadline = started+self._limits.wall_seconds
        receipt = dict(operation=str(operation), commit=commit, outcome='unknown', started_at=datetime.now(timezone.utc).isoformat(),
                       elapsed_seconds=0.0, layer='receipt_storage', native_calls=[], admitted_artifacts=[], snapshot=None,
                       limits=asdict(self._limits), git=asdict(self._git_executable), prlimit=asdict(self._prlimit),
                       fsck_ignore=sorted(self._fsck_ignore), skip_nonregular=self._skip_nonregular, skipped=[])
        for key in ('git','prlimit'): receipt[key]['path'] = str(receipt[key]['path'])
        try: self._journal.write(operation, 'intent', receipt)
        except Exception as error:
            raise SourceCaptureError(dict(receipt, error_detail=str(error), delivery='not_dispatched')) from error
        snapshot = None; cause = None
        try:
            receipt['layer'] = 'native_source'
            native = lambda args,cap,**kw: self._native(repo,args,cap,deadline,receipt['native_calls'],**kw)
            if native(['rev-parse','--is-bare-repository'],16) != b'true\n':
                raise ValueError('Only complete operator bare repositories admitted')
            if native(['config','--local','--get-regexp',r'^(extensions\.partialclone|remote\..*\.promisor)$'],4096,allowed=(0,1)):
                raise ValueError('Partial/promisor source repositories unsupported')
            if native(['rev-parse','--is-shallow-repository'],16) != b'false\n':
                raise ValueError('Shallow source repositories unsupported')
            # Native full integrity checks include trees, not just blob bytes.
            # Large or corrupt databases can fail the same bounded admission.
            native(['fsck','--strict','--no-reflogs','--no-dangling',commit],4096)
            commit_data = native(['cat-file','commit',commit],65536)
            if git_hash('commit', commit_data) != commit: raise ValueError('Original Git commit digest mismatch')
            tree_line = commit_data.split(b'\n',1)[0]
            if not re.fullmatch(b'tree [0-9a-f]{40}', tree_line): raise ValueError('Unsupported native commit tree')
            tree = tree_line[5:].decode()
            # Long listing: sizes come from the tree walk, so each admitted blob costs one native call, not two.
            entries = native(['ls-tree','-rlz','--full-tree',tree], self._limits.max_files*1200)
            receipt['layer'] = 'source_admission'
            if entries and not entries.endswith(b'\0'): raise ValueError('Incomplete native tree list')
            records = entries[:-1].split(b'\0') if entries else []
            selected = []; paths = set(); skipped = receipt['skipped']
            for record in records:
                metadata, path_bytes = record.split(b'\t',1)
                mode, kind, blob, size_text = metadata.decode('ascii').split()
                path = path_bytes.decode('utf8'); confined_path(path)
                if (self._skip_nonregular and mode in NONREGULAR_MODES and kind == ('commit' if mode == '160000' else 'blob')
                        and re.fullmatch('[0-9a-f]{40}',blob)):
                    skipped.append(dict(path=path,mode=mode,kind=NONREGULAR_MODES[mode],object=blob)); continue
                if mode not in ('100644','100755') or kind!='blob' or not re.fullmatch('[0-9a-f]{40}',blob):
                    raise ValueError('Only regular source blobs admitted; symlinks/submodules refused')
                if not re.fullmatch('0|[1-9][0-9]*',size_text): raise ValueError('Unsupported Git object size')
                if path in paths or any('/'.join(path.split('/')[:n]) in paths for n in range(1,len(path.split('/')))):
                    raise ValueError('Duplicate/colliding source path')
                paths.add(path); selected.append((path,mode,blob,int(size_text)))
            if len(selected) > self._limits.max_files: raise ValueError('Source file count exceeded')
            if any('/'.join(p.split('/')[:n]) in paths for p in paths for n in range(1,len(p.split('/')))):
                raise ValueError('Colliding source paths')
            files = []; total = 0
            for path,mode,blob,size in selected:
                receipt['layer'] = 'source_admission'
                if size > self._limits.max_file_bytes or total+size > self._limits.max_total_bytes:
                    raise ValueError('Source byte budget exceeded')
                receipt['layer'] = 'native_source'
                data = native(['cat-file','blob',blob],self._limits.max_file_bytes)
                if len(data)!=size or git_hash('blob',data)!=blob: raise ValueError('Original Git blob size/digest mismatch')
                receipt['layer'] = 'artifact_storage'
                ref = self._store.put(data, expected_sha256=hashlib.sha256(data).hexdigest())
                receipt['admitted_artifacts'].append(asdict(ref)); files.append(SourceFile(path,mode,blob,ref)); total += size
            receipt['layer'] = 'artifact_storage'
            # Skipped entries are listed only when present, so manifests of regular-only trees are unchanged.
            manifest_value = dict(version=1,commit=commit,tree=tree,files=[asdict(f) for f in files])
            if skipped: manifest_value['skipped'] = skipped
            manifest_bytes = (json.dumps(manifest_value,sort_keys=True,separators=(',',':'))+'\n').encode()
            manifest = self._store.put(manifest_bytes)
            receipt['admitted_artifacts'].append(asdict(manifest))
            snapshot = SourceSnapshot(commit,tree,tuple(files),manifest,tuple(SkippedEntry(**item) for item in skipped))
            receipt.update(outcome='completed',snapshot=asdict(snapshot),layer=None)
        except Exception as error:
            cause = error; receipt.update(outcome='failed',error_type=type(error).__name__,error_detail=str(error))
            if isinstance(error,ArtifactStorageError):
                receipt['artifact_failure'] = dict(reference=asdict(error.reference) if error.reference else None,
                    publication=error.publication,temporary_cleanup=error.temporary_cleanup,
                    temporary_name=error.temporary_name,temporary_identity=error.temporary_identity)
        receipt['elapsed_seconds'] = time.monotonic()-started
        try: self._journal.write(operation,'result',receipt)
        except Exception as error:
            receipt['storage_error'] = f'{type(error).__name__}: {error}'
            raise SourceCaptureError(receipt) from error
        if cause is not None: raise SourceCaptureError(receipt) from cause
        return snapshot
