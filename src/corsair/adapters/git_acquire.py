"""SPEC-0037 host acquisition: fetch one exact commit over HTTPS into a new private bare repository, verify it, measure it.

The repository produced here is the input `GitSource` (SPEC-0012) captures and the `FetchTarget` the SPEC-0025 sandbox
fetch later replays. Nothing here checks out, builds or runs repository content. A refused or unknown fetch is never
repaired in place: the caller discards the destination and, if it chooses, acquires again into a new one.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from uuid import UUID

from corsair.adapters.git_source import Executable, confined_path, git_hash
from corsair.adapters.receipts import ReceiptDirectory
from corsair.nodes.source_fetch import HOST, FetchTarget

PIN_REF = 'refs/corsair/pinned'
GIB = 1024**3
# Git fsck message ids that concern only the formatting of historical commit and tree objects. Old history in
# several benchmark repositories carries them; the object hashes still verify. An operator may downgrade only these.
FORMAT_ONLY_FSCK = frozenset({'badTimezone', 'missingSpaceBeforeEmail', 'zeroPaddedFilemode'})


@dataclass(frozen=True)
class HostTransport:
    """Operator-owned egress for the fetch; the caller's proxy, credential and Git environment are never inherited."""
    allowed_hosts: frozenset[str]
    proxy: str | None = None
    ca_bundle: Path | None = None

    def __post_init__(self):
        if (type(self.allowed_hosts) is not frozenset or not self.allowed_hosts
                or not all(isinstance(h, str) and re.fullmatch(HOST, h) for h in self.allowed_hosts)):
            raise ValueError('Nonempty frozenset of lowercase repository hosts required')
        if self.proxy is not None and not (isinstance(self.proxy, str)
                                           and re.fullmatch(r'https?://[A-Za-z0-9.-]+:[0-9]{1,5}/?', self.proxy)):
            raise ValueError('Proxy must be a plain scheme://host:port URL without credentials')
        if self.ca_bundle is not None and not (isinstance(self.ca_bundle, Path) and self.ca_bundle.is_absolute()
                                               and self.ca_bundle.is_file()):
            raise ValueError('CA bundle must be an absolute regular file')


@dataclass(frozen=True)
class AcquireLimits:
    """`depth` None fetches the commit's complete ancestry, which `GitSource` admits; a depth gives a shallow,
    measure-only repository that `GitSource` refuses. `fsck_warn` downgrades named format-only fsck errors to
    recorded warnings; empty by default."""
    wall_seconds: int = 600
    repository_bytes: int = 2*GIB
    memory_bytes: int = 4*GIB
    depth: int | None = None
    fsck_warn: frozenset[str] = frozenset()

    def __post_init__(self):
        if (any(type(v) is not int or v <= 0 for v in (self.wall_seconds, self.repository_bytes, self.memory_bytes))
                or self.wall_seconds > 3600 or self.repository_bytes > 16*GIB or self.memory_bytes > 8*GIB
                or not (self.depth is None or (type(self.depth) is int and 1 <= self.depth <= 64))
                or type(self.fsck_warn) is not frozenset or not self.fsck_warn <= FORMAT_ONLY_FSCK):
            raise ValueError('Bounded operator acquisition limits required')


@dataclass(frozen=True)
class TreeStats:
    """One commit's tree as Git records it; sizes the SPEC-0036 workspace quota and the capture ceilings."""
    commit: str
    tree: str
    entries: int
    regular_files: int
    regular_bytes: int
    largest_file_bytes: int
    executables: int
    symlinks: int
    submodules: int
    noncanonical_paths: int


@dataclass(frozen=True)
class AcquiredSource:
    url: str
    commit: str
    tree: TreeStats
    parents: tuple[str, ...]
    first_parent: TreeStats | None  # None when the parent is absent (depth 1) or the commit is a root
    shallow: bool
    repository: str
    repository_bytes: int
    fetched_at: str
    elapsed_seconds: float
    git_version: str
    fsck_warnings: tuple[str, ...]  # downgraded fsck message ids actually reported, with the objects in the receipt

    def target(self, commit: str | None = None) -> FetchTarget:
        """The SPEC-0025 sandbox fetch target for this commit or, by name, its fetched first parent."""
        if commit not in (None, self.commit) and (self.first_parent is None or commit != self.first_parent.commit):
            raise ValueError('Only the acquired commit or its fetched first parent')
        return FetchTarget(self.url, commit or self.commit)


class AcquisitionError(RuntimeError):
    """`layer`: configuration, host_network, source_unavailable, transport, budget, source_admission or native_git."""
    def __init__(self, layer: str, detail: str, receipt: dict):
        self.layer, self.receipt = layer, receipt
        super().__init__(f'{layer}: {detail}')


NETWORK = re.compile(rb'CONNECT tunnel failed|Could not resolve host|Failed to connect|Connection (?:timed out|refused)'
                     rb'|SSL certificate problem|gnutls_handshake|OpenSSL SSL_')
FSCK_REFUSED = re.compile(rb'fsck error in packed object')
FSCK_MESSAGE = re.compile(rb'[0-9a-f]{40}: (\w+):')
UNAVAILABLE = re.compile(rb'not our ref|couldn\'t find remote ref|Repository not found|repository \S+ not found'
                         rb'|upload-pack: not our ref|The requested URL returned error: 40[34]')


XFSZ = re.compile(rb'died of signal %d\b' % signal.SIGXFSZ)


def _fetch_layer(error: Exception, stderr: bytes) -> str:
    # The file-size limit kills the writer (index-pack) with SIGXFSZ; fetch itself then exits 128.
    if isinstance(error, TimeoutError) or isinstance(error, _Exit) and error.code == -signal.SIGXFSZ or XFSZ.search(stderr):
        return 'budget'
    if NETWORK.search(stderr): return 'host_network'
    if UNAVAILABLE.search(stderr): return 'source_unavailable'
    if FSCK_REFUSED.search(stderr): return 'source_admission'
    return 'transport'


class _Exit(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'Native Git exit {code}')


def tree_stats(commit: str, tree: str, listing: bytes) -> TreeStats:
    """Parse `git ls-tree -r -l -z --full-tree` output."""
    if listing and not listing.endswith(b'\0'): raise ValueError('Incomplete native tree list')
    counts = dict(entries=0, regular_files=0, regular_bytes=0, largest_file_bytes=0, executables=0, symlinks=0,
                  submodules=0, noncanonical_paths=0)
    for record in listing[:-1].split(b'\0') if listing else []:
        metadata, path = record.split(b'\t', 1)
        mode, kind, _, size = metadata.decode('ascii').split()
        counts['entries'] += 1
        try: confined_path(path.decode('utf8'))
        except (UnicodeDecodeError, ValueError): counts['noncanonical_paths'] += 1
        if kind == 'commit': counts['submodules'] += 1
        elif mode == '120000': counts['symlinks'] += 1
        elif kind == 'blob' and mode in ('100644', '100755'):
            counts['regular_files'] += 1; counts['regular_bytes'] += int(size)
            counts['largest_file_bytes'] = max(counts['largest_file_bytes'], int(size))
            counts['executables'] += mode == '100755'
        else: raise ValueError(f'Unsupported native tree entry {mode} {kind}')
    return TreeStats(commit, tree, **counts)


def _bytes_on_disk(root: Path) -> int:
    total = 0
    for directory, _, files in os.walk(root):
        for name in files: total += os.lstat(os.path.join(directory, name)).st_size
    return total


class GitAcquisition:
    def __init__(self, git: Executable, prlimit: Executable, *, transport: HostTransport, limits: AcquireLimits,
                 receipts: Path):
        git.verify(); prlimit.verify()
        self._git, self._prlimit, self._transport, self._limits = git, prlimit, transport, limits
        self._journal = ReceiptDirectory(receipts)

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def _native(self, repo: Path, args, deadline, calls, *, network=False, allowed=(0,)) -> bytes:
        if time.monotonic() >= deadline: raise TimeoutError('Acquisition wall budget exhausted before dispatch')
        limits = self._limits
        config = ['-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c', 'protocol.allow=never',
                  '-c', 'transfer.fsckObjects=true', '-c', 'submodule.recurse=false', '-c', 'credential.helper=',
                  '-c', 'pack.threads=2']
        for message in sorted(limits.fsck_warn):
            config += ['-c', f'fetch.fsck.{message}=warn', '-c', f'fsck.{message}=warn']
        if network:
            config += ['-c', 'protocol.https.allow=always']
            if self._transport.proxy: config += ['-c', 'http.proxy='+self._transport.proxy]
            if self._transport.ca_bundle: config += ['-c', f'http.sslCAInfo={self._transport.ca_bundle}']
        argv = [str(self._prlimit.path), f'--as={limits.memory_bytes}:{limits.memory_bytes}',
                f'--fsize={limits.repository_bytes}:{limits.repository_bytes}', '--',
                str(self._git.path), *config, '-C', str(repo), *args]
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_TERMINAL_PROMPT': '0',
               'GIT_LFS_SKIP_SMUDGE': '1'}
        observation = dict(args=args, network=network, exit=None, elapsed_seconds=None, stdout_bytes=0, stderr='')
        calls.append(observation)
        started = time.monotonic()
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=env, start_new_session=True)
        try:
            out, err = process.communicate(timeout=max(0.001, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            # Fetch helpers are grandchildren; end the whole session this call started.
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            out, err = process.communicate()
            observation.update(exit=process.returncode, elapsed_seconds=time.monotonic()-started,
                               stderr=err[-4096:].decode('utf8', 'replace'))
            raise TimeoutError('Acquisition wall budget exhausted') from None
        observation.update(exit=process.returncode, elapsed_seconds=time.monotonic()-started, stdout_bytes=len(out),
                           stderr=err[-4096:].decode('utf8', 'replace'),
                           fsck_messages=sorted({m.decode() for m in FSCK_MESSAGE.findall(err)}))
        if process.returncode not in allowed:
            error = _Exit(process.returncode); error.stderr = err
            raise error
        return out

    def inspect(self, repo: Path, commit: str, *, deadline: float | None = None, calls: list | None = None,
                expect_shallow: bool | None = None) -> tuple[TreeStats, tuple[str, ...], TreeStats | None, bool]:
        """Verify `commit` in an existing bare repository and measure it and its first parent; reads only."""
        deadline = time.monotonic()+self._limits.wall_seconds if deadline is None else deadline
        calls = [] if calls is None else calls
        native = lambda args, **kw: self._native(repo, args, deadline, calls, **kw)
        if native(['rev-parse', '--is-bare-repository']) != b'true\n':
            raise ValueError('Bare repository required')
        shallow = native(['rev-parse', '--is-shallow-repository']) == b'true\n'
        if expect_shallow is not None and shallow != expect_shallow:
            raise ValueError('Repository shallowness differs from the requested depth')
        if native(['rev-parse', '--verify', '--end-of-options', PIN_REF+'^{commit}']).strip().decode() != commit:
            raise ValueError('Pinned ref does not name the requested commit')
        data = native(['cat-file', 'commit', commit])
        if git_hash('commit', data) != commit: raise ValueError('Fetched commit digest mismatch')
        header = data.split(b'\n\n', 1)[0].split(b'\n')
        if not re.fullmatch(b'tree [0-9a-f]{40}', header[0]): raise ValueError('Unsupported native commit tree')
        parents = tuple(line[7:].decode() for line in header[1:] if re.fullmatch(b'parent [0-9a-f]{40}', line))
        native(['fsck', '--strict', '--no-reflogs', '--no-dangling', '--no-progress', commit])
        stats = tree_stats(commit, header[0][5:].decode(),
                           native(['ls-tree', '-r', '-l', '-z', '--full-tree', commit]))
        parent = None
        if parents:
            native(['cat-file', '-e', parents[0]+'^{commit}'], allowed=(0, 1, 128))
        if parents and calls[-1]['exit'] == 0:
            tree = native(['rev-parse', '--verify', '--end-of-options', parents[0]+'^{tree}']).strip().decode()
            parent = tree_stats(parents[0], tree, native(['ls-tree', '-r', '-l', '-z', '--full-tree', parents[0]]))
        return stats, parents, parent, shallow

    def acquire(self, target: FetchTarget, destination: Path, operation: UUID) -> AcquiredSource:
        limits = self._limits
        receipt = dict(operation=str(operation), url=target.url, commit=target.commit, destination=str(destination),
                       outcome='unknown', layer='configuration', started_at=datetime.now(timezone.utc).isoformat(),
                       limits=dict(asdict(limits), fsck_warn=sorted(limits.fsck_warn)), proxy=self._transport.proxy is not None,
                       git=dict(path=str(self._git.path), sha256=self._git.sha256), native_calls=[])
        try:
            if not isinstance(target, FetchTarget) or target.credential is not None:
                raise ValueError('Public FetchTarget required; no credential path exists for host acquisition')
            if target.host not in self._transport.allowed_hosts: raise ValueError('Repository host not operator-allowed')
            if not isinstance(operation, UUID) or not destination.is_absolute() or destination.parent.resolve() != destination.parent:
                raise ValueError('UUID and canonical absolute destination required')
        except ValueError as error:
            raise AcquisitionError('configuration', str(error), dict(receipt, outcome='refused', delivery='not_dispatched')) from error
        self._journal.write(operation, 'intent', receipt)
        started = time.monotonic(); deadline = started+limits.wall_seconds
        calls = receipt['native_calls']
        result = None; cause = None
        try:
            os.mkdir(destination, 0o700)  # exclusive: a destination is never reused
            receipt['layer'] = 'native_git'
            version = self._native(destination, ['version'], deadline, calls).strip().decode()
            self._native(destination, ['init', '--bare', '-q', '--template='], deadline, calls)
            receipt['layer'] = 'transport'
            depth = [] if limits.depth is None else [f'--depth={limits.depth}']
            try:
                self._native(destination, ['fetch', '--no-tags', '--no-write-fetch-head', '--no-progress', *depth,
                                           '--end-of-options', target.url, f'{target.commit}:{PIN_REF}'],
                             deadline, calls, network=True)
            except (TimeoutError, _Exit) as error:
                receipt['layer'] = _fetch_layer(error, getattr(error, 'stderr', b''))
                raise
            receipt['layer'] = 'budget'
            size = _bytes_on_disk(destination)
            if size > limits.repository_bytes: raise ValueError('Repository byte budget exceeded')
            receipt['layer'] = 'source_admission'
            try:
                stats, parents, parent, shallow = self.inspect(destination, target.commit, deadline=deadline,
                                                               calls=calls, expect_shallow=limits.depth is not None)
            except TimeoutError:
                receipt['layer'] = 'budget'; raise
            except _Exit:  # a failing fsck is the integrity refusal itself; any other local Git failure is not
                if calls[-1]['args'][0] != 'fsck': receipt['layer'] = 'native_git'
                raise
            warnings = tuple(sorted({m for call in calls for m in call.get('fsck_messages', ())}))
            result = AcquiredSource(target.url, target.commit, stats, parents, parent, shallow, str(destination), size,
                                    receipt['started_at'], time.monotonic()-started, version, warnings)
            receipt.update(outcome='completed', layer=None, result=asdict(result))
        except Exception as error:
            cause = error
            receipt.update(outcome='failed', error_type=type(error).__name__, error_detail=str(error))
        receipt['elapsed_seconds'] = time.monotonic()-started
        self._journal.write(operation, 'result', receipt)
        if cause is not None: raise AcquisitionError(receipt['layer'], str(cause), receipt) from cause
        return result
