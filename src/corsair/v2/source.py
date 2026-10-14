"""Immutable, data-only v2 source capture and materialization.

No captured source is imported, checked out, hooked, or executed.  Git inputs
are copied into a private complete bare repository before their tree is read;
directory inputs are read through no-follow file descriptors.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from corsair.adapters.git_acquire import AcquireLimits, GitAcquisition, HostTransport
from corsair.adapters.git_source import Executable, GitSource, SourceLimits, git_hash
from corsair.adapters.git_source import confined_path as legacy_confined_path
from corsair.nodes.source_fetch import FetchTarget
from corsair.ports.artifacts import ArtifactRef as LocalArtifactRef
from corsair.ports.artifacts import SourceSnapshot as LocalSourceSnapshot

from .contracts import (
    ArtifactRef,
    SourceFile,
    SourceRequest,
    SourceSnapshot,
    canonical_bytes,
    confined_path,
)
from .storage import Store, _private_directory

_EXCLUDED_DIRECTORIES = frozenset({".git", ".venv", ".state", ".runs", "cache"})
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")
_SENSITIVE_NAMES = frozenset({"credentials", "credentials.json", "id_rsa", "id_ed25519", "secrets"})
_MAX_OVERLAY_FILES = 64
_MAX_OVERLAY_FILE_BYTES = 2 * 1024 * 1024
_MAX_OVERLAY_BYTES = 8 * 1024 * 1024
_MAX_DIFF_FILE_BYTES = 512 * 1024
_MAX_DIFF_CHARS = 1024 * 1024


class SourceError(ValueError):
    """A source was not safe, complete, or inside the requested capture bounds."""


class _LegacyStore:
    """Bridge v2 Pydantic references to the legacy GitSource dataclasses."""

    def __init__(self, store: Store):
        self._store = store

    def put(self, data: bytes, *, expected_sha256: str | None = None) -> LocalArtifactRef:
        value = self._store.put(data, expected_sha256=expected_sha256)
        return LocalArtifactRef(value.sha256, value.size)

    def get(self, reference: LocalArtifactRef) -> bytes:
        return self._store.get(ArtifactRef(sha256=reference.sha256, size=reference.size))


def _native_executable(path: str) -> Executable:
    value = Path(path)
    if not value.is_absolute() or not value.is_file():
        raise RuntimeError(f"Required native executable is unavailable: {path}")
    return Executable(value, hashlib.sha256(value.read_bytes()).hexdigest())


def _is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return (lowered == ".env" or lowered.startswith(".env.") or lowered in _SENSITIVE_NAMES
            or lowered.endswith(_SENSITIVE_SUFFIXES))


def _skipped_reason(path: str) -> str | None:
    parts = path.split("/")
    if any(part in _EXCLUDED_DIRECTORIES for part in parts):
        return "excluded"
    if _is_sensitive(parts[-1]):
        return "sensitive"
    return None


def _private_child(root: Path, name: str) -> Path:
    return _private_directory(root / name)


def _real_directory(value: Path, label: str) -> Path:
    """Return an existing directory only when no path component is a link."""
    lexical = value.expanduser().absolute()
    try:
        resolved = lexical.resolve(strict=True)
        info = os.lstat(lexical)
    except FileNotFoundError as error:
        raise SourceError(f"{label} does not exist") from error
    if lexical != resolved or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SourceError(f"{label} must be a real directory, not a symlink")
    return lexical


class SourceService:
    """Capture bounded source bytes, then read or materialize the immutable snapshot."""

    def __init__(self, store: Store):
        if not isinstance(store, Store):
            raise ValueError("SourceService requires a v2 Store")  # noqa: TRY004 - invalid admission is consistently ValueError
        self.store = store
        self._sources = _private_child(store.root, "sources")
        self._receipts = _private_child(store.root, "source-receipts")
        self._git = _native_executable("/usr/bin/git")
        self._prlimit = _native_executable("/usr/bin/prlimit")

    def capture(self, request: SourceRequest, revision: str = "baseline") -> SourceSnapshot:
        """Capture the selected immutable revision without changing a supplied checkout."""
        if not isinstance(request, SourceRequest):
            raise ValueError("A v2 SourceRequest is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        if revision not in ("baseline", "candidate"):
            raise ValueError("revision must be 'baseline' or 'candidate'")
        if revision == "baseline":
            location, commit = request.path, request.commit
        else:
            location, commit = request.candidate_path or request.path, request.candidate_commit or request.commit
        if self._https(location):
            if commit is None:
                raise SourceError("HTTPS Git source capture requires an exact pinned commit")
            return self._capture_remote(location, commit, request)
        directory = _real_directory(Path(location), "Local source")
        if commit is None:
            return self.capture_directory(directory, repository=str(directory), max_files=request.max_files,
                                          max_bytes=request.max_bytes, max_file_bytes=request.max_file_bytes)
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise SourceError("An exact SHA-1 or SHA-256 Git commit is required")
        bare = self._clone_local_bare(directory)
        return self._capture_bare(bare, str(directory), commit, request)

    def capture_directory(self, directory: Path, *, repository: str | None = None, max_files: int = 10000,
                          max_bytes: int = 32 * 1024 * 1024, max_file_bytes: int = 2 * 1024 * 1024,
                          wall_seconds: int = 30) -> SourceSnapshot:
        """Capture one directory through no-follow descriptors, excluding sensitive defaults."""
        if (not isinstance(max_files, int) or not 1 <= max_files <= 65536 or not isinstance(max_bytes, int)
                or not 1 <= max_bytes <= 256 * 1024 * 1024 or not isinstance(max_file_bytes, int)
                or not 1 <= max_file_bytes <= 16 * 1024 * 1024 or not isinstance(wall_seconds, int)
                or not 1 <= wall_seconds <= 600):
            raise ValueError("Bounded directory source limits are required")
        directory = _real_directory(Path(directory), "Directory source")
        deadline = time.monotonic() + wall_seconds
        files: list[SourceFile] = []
        skipped: list[str] = []
        total = 0

        def descend(fd: int, prefix: str) -> None:
            nonlocal total
            if time.monotonic() >= deadline:
                raise SourceError("Directory source wall-time bound exceeded")
            with os.scandir(fd) as entries:
                names = sorted(entries, key=lambda entry: os.fsencode(entry.name))
            for entry in names:
                if time.monotonic() >= deadline:
                    raise SourceError("Directory source wall-time bound exceeded")
                try:
                    name = os.fsdecode(os.fsencode(entry.name))
                    name.encode("utf-8", "strict")
                except UnicodeError as error:
                    raise SourceError("Directory source has a non-UTF-8 filename") from error
                path = f"{prefix}/{name}" if prefix else name
                try:
                    entry_info = entry.stat(follow_symlinks=False)
                except FileNotFoundError as error:
                    raise SourceError("Directory source changed while being captured") from error
                if stat.S_ISLNK(entry_info.st_mode):
                    skipped.append(f"symlink:{path}")
                    continue
                reason = _skipped_reason(path)
                if reason is not None:
                    skipped.append(f"{reason}:{path}")
                    continue
                if stat.S_ISDIR(entry_info.st_mode):
                    try:
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    except OSError as error:
                        raise SourceError(f"Unable to safely open directory {path}") from error
                    try:
                        descend(child, path)
                    finally:
                        os.close(child)
                    continue
                if not stat.S_ISREG(entry_info.st_mode):
                    skipped.append(f"nonregular:{path}")
                    continue
                try:
                    confined_path(path)
                except ValueError as error:
                    raise SourceError(f"Unsafe directory source path: {path!r}") from error
                if entry_info.st_size > max_file_bytes or total + entry_info.st_size > max_bytes:
                    raise SourceError("Directory source byte bound exceeded")
                if len(files) >= max_files:
                    raise SourceError("Directory source file-count bound exceeded")
                try:
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(file_fd, "rb", closefd=True) as stream:
                        opened = os.fstat(stream.fileno())
                        if not stat.S_ISREG(opened.st_mode) or opened.st_size != entry_info.st_size:
                            raise SourceError("Directory source changed while being captured")
                        data = stream.read(max_file_bytes + 1)
                except OSError as error:
                    raise SourceError(f"Unable to safely read source file {path}") from error
                if len(data) != entry_info.st_size or len(data) > max_file_bytes:
                    raise SourceError("Directory source changed or exceeded a byte bound")
                if total + len(data) > max_bytes:
                    raise SourceError("Directory source byte bound exceeded")
                ref = self.store.put(data)
                files.append(SourceFile(path=path, artifact=ref,
                                        mode="100755" if opened.st_mode & 0o111 else "100644"))
                total += len(data)

        root_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descend(root_fd, "")
        finally:
            os.close(root_fd)
        files.sort(key=lambda value: value.path)
        return self._make_snapshot(repository or str(directory), None, None, files, skipped)

    def materialize(self, snapshot: SourceSnapshot, target: Path, overlays: dict[str, bytes] | None = None) -> Path:
        """Write a snapshot to one brand-new, no-symlink target directory."""
        self._validate_snapshot(snapshot)
        target = Path(target).expanduser()
        if not target.is_absolute():
            raise ValueError("Materialization target must be absolute")
        if os.path.lexists(target):
            raise SourceError("Materialization target must be fresh")
        _real_directory(target.parent, "Materialization parent")
        merged = {item.path: self.store.get(item.artifact) for item in snapshot.files}
        if overlays is not None:
            if not isinstance(overlays, dict) or len(overlays) > _MAX_OVERLAY_FILES:
                raise ValueError("Overlay count exceeds the bounded materialization envelope")
            overlay_total = 0
            for path, data in overlays.items():
                confined_path(path)
                if type(data) is not bytes or len(data) > _MAX_OVERLAY_FILE_BYTES:
                    raise ValueError("Overlay values must be bounded exact bytes")
                overlay_total += len(data)
                if overlay_total > _MAX_OVERLAY_BYTES:
                    raise ValueError("Overlay byte bound exceeded")
                merged[path] = data
        ordered = sorted(merged)
        if any(other.startswith(path + "/") for index, path in enumerate(ordered) for other in ordered[index + 1:]):
            raise SourceError("A source file path collides with a source directory")
        os.mkdir(target, 0o700)
        root_fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            mode_by_path = {item.path: 0o755 if item.mode == "100755" else 0o644 for item in snapshot.files}
            for path in ordered:
                fd = os.dup(root_fd)
                try:
                    parts = path.split("/")
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, 0o700, dir_fd=fd)
                        except FileExistsError:
                            pass
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        os.close(fd)
                        fd = child
                    file_fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                      mode_by_path.get(path, 0o600), dir_fd=fd)
                    with os.fdopen(file_fd, "wb", closefd=True) as stream:
                        stream.write(merged[path])
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    os.close(fd)
            os.fsync(root_fd)
        finally:
            # An incomplete target remains private; never guess at recursive
            # deletion after an I/O failure.
            os.close(root_fd)
        return target

    def diff(self, baseline: SourceSnapshot, candidate: SourceSnapshot) -> str:
        self._validate_snapshot(baseline)
        self._validate_snapshot(candidate)
        left, right = {item.path: item for item in baseline.files}, {item.path: item for item in candidate.files}
        chunks: list[str] = []
        spent = 0
        for path in sorted(set(left) | set(right)):
            before = self.store.get(left[path].artifact) if path in left else b""
            after = self.store.get(right[path].artifact) if path in right else b""
            before_mode = left[path].mode if path in left else None
            after_mode = right[path].mode if path in right else None
            if before == after and before_mode == after_mode:
                continue
            if (b"\0" in before or b"\0" in after or len(before) > _MAX_DIFF_FILE_BYTES
                    or len(after) > _MAX_DIFF_FILE_BYTES):
                chunks.append(f"Binary or oversized difference: {path} ({len(before)} -> {len(after)} bytes)\n")
                continue
            try:
                old = before.decode("utf-8").splitlines(keepends=True)
                new = after.decode("utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                chunks.append(f"Binary difference: {path} ({len(before)} -> {len(after)} bytes)\n")
                continue
            rendered = "".join(difflib.unified_diff(old, new, fromfile=f"baseline/{path}", tofile=f"candidate/{path}"))
            if before_mode != after_mode:
                rendered += f"mode {before_mode or 'absent'} -> {after_mode or 'absent'}: {path}\n"
            if spent + len(rendered) > _MAX_DIFF_CHARS:
                chunks.append("Diff output truncated at bounded limit.\n")
                break
            chunks.append(rendered)
            spent += len(rendered)
        return "".join(chunks)

    def read_text(self, snapshot: SourceSnapshot, path: str, start_line: int = 1, end_line: int | None = None,
                  max_chars: int = 32768) -> str:
        self._validate_snapshot(snapshot)
        confined_path(path)
        if not isinstance(start_line, int) or start_line < 1 or (end_line is not None and (not isinstance(end_line, int) or end_line < start_line)):
            raise ValueError("A valid inclusive source line range is required")
        if not isinstance(max_chars, int) or not 1 <= max_chars <= 32768:
            raise ValueError("max_chars must be within 1..32768")
        refs = {item.path: item.artifact for item in snapshot.files}
        if path not in refs:
            raise ValueError("Source path is absent from snapshot")
        try:
            text = self.store.get(refs[path]).decode("utf-8")
        except UnicodeDecodeError as error:
            raise SourceError("Source file is not UTF-8 text") from error
        lines = text.splitlines(keepends=True)
        if start_line > len(lines):
            raise ValueError("Source start line is absent")
        chosen = "".join(lines[start_line - 1:(end_line if end_line is not None else len(lines))])
        if len(chosen) > max_chars:
            raise SourceError("Requested source text exceeds max_chars")
        return chosen

    def list_paths(self, snapshot: SourceSnapshot, pattern: str = "*") -> list[str]:
        from fnmatch import fnmatchcase
        self._validate_snapshot(snapshot)
        if not isinstance(pattern, str) or not pattern or len(pattern) > 1024:
            raise ValueError("A bounded path pattern is required")
        return [item.path for item in snapshot.files if fnmatchcase(item.path, pattern)]

    def _capture_remote(self, url: str, commit: str, request: SourceRequest) -> SourceSnapshot:
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise SourceError("An exact SHA-1 or SHA-256 Git commit is required")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port
                or parsed.query or parsed.fragment or parsed.hostname != parsed.hostname.lower()):
            raise SourceError("A canonical credential-free HTTPS Git URL is required")
        # FetchTarget retains the established strict canonical URL grammar.
        try:
            target = FetchTarget(url, commit if len(commit) == 40 else "0" * 40)
        except ValueError as error:
            raise SourceError(str(error)) from error
        bare = self._sources / f"remote-{uuid4().hex}.git"
        if len(commit) == 64:
            self._fetch_sha256_remote(url, commit, bare, request)
            return self._capture_bare(bare, url, commit, request)
        repository_bytes = min(16 * 1024**3, max(16 * 1024**2, request.max_bytes * 8))
        acquisition = GitAcquisition(self._git, self._prlimit,
                                     transport=HostTransport(frozenset({parsed.hostname})),
                                     limits=AcquireLimits(wall_seconds=60, repository_bytes=repository_bytes,
                                                          memory_bytes=512 * 1024**2), receipts=self._receipts)
        with acquisition:
            acquisition.acquire(target, bare, uuid4())
        os.chmod(bare, 0o700)
        return self._capture_bare(bare, url, commit, request)

    def _fetch_sha256_remote(self, url: str, commit: str, bare: Path, request: SourceRequest) -> None:
        """Fetch a complete private SHA-256 bare repository without checkout or hooks."""
        limit = min(2 * 1024**3, max(64 * 1024**2, request.max_bytes * 8))
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
               "GIT_LFS_SKIP_SMUDGE": "1"}
        commands = [
            [str(self._git.path), "init", "--bare", "--quiet", "--template=", str(bare)],
            [str(self._prlimit.path), "--as=536870912:536870912", f"--fsize={limit}:{limit}", "--",
             str(self._git.path), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c",
             "protocol.allow=never", "-c", "protocol.https.allow=always", "-c", "http.followRedirects=false", "-c",
             "credential.helper=", "-C", str(bare), "fetch", "--no-tags", "--no-write-fetch-head", "--no-progress",
             "--end-of-options", url, f"{commit}:refs/corsair/pinned"],
        ]
        for command in commands:
            try:
                completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=60, check=False)
            except subprocess.TimeoutExpired as error:
                raise SourceError("HTTPS Git bare capture exceeded wall-time bound") from error
            if completed.returncode != 0:
                raise SourceError("HTTPS Git bare capture failed: " + completed.stderr[-1024:].decode("utf-8", "replace"))
        os.chmod(bare, 0o700)

    def _clone_local_bare(self, directory: Path) -> Path:
        bare = self._sources / f"local-{uuid4().hex}.git"
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"}
        command = [str(self._git.path), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c",
                   "protocol.file.allow=always", "-c", "credential.helper=", "clone", "--bare", "--no-local", "--quiet",
                   "--", str(directory), str(bare)]
        try:
            completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=60, check=False)
        except subprocess.TimeoutExpired as error:
            raise SourceError("Local Git bare capture exceeded wall-time bound") from error
        if completed.returncode != 0:
            raise SourceError("Local Git bare capture failed: " + completed.stderr[-1024:].decode("utf-8", "replace"))
        os.chmod(bare, 0o700)
        return bare

    def _capture_bare(self, bare: Path, repository: str, commit: str, request: SourceRequest) -> SourceSnapshot:
        """Use the established GitSource parser when no default exclusion is needed.

        The small filtered branch is necessary because the older parser correctly
        captures every regular Git blob; v2 must not retain `.env`/credential or
        excluded-tree bytes at all.
        """
        deadline = time.monotonic() + 30
        records = self._git_listing(bare, commit, deadline)
        needs_filter = any(_skipped_reason(path) is not None for _, _, _, _, path in records)
        limits = SourceLimits(max_files=request.max_files, max_file_bytes=request.max_file_bytes,
                              max_total_bytes=request.max_bytes, wall_seconds=30)
        if len(commit) == 40 and not needs_filter:
            bridge = _LegacyStore(self.store)
            with GitSource(self._git, self._prlimit, store=bridge, limits=limits, receipts=self._receipts,
                           skip_nonregular=True) as source:
                captured: LocalSourceSnapshot = source.capture(bare, commit, uuid4())
            files = [SourceFile(path=item.path, mode=item.mode,
                                artifact=ArtifactRef(sha256=item.artifact.sha256, size=item.artifact.size))
                     for item in captured.files]
            skipped = [f"{item.kind}:{item.path}" for item in captured.skipped]
            return self._make_snapshot(repository, captured.commit, captured.tree, files, skipped)
        return self._capture_filtered_bare(bare, repository, commit, request, records, deadline)

    def _git_listing(self, bare: Path, commit: str, deadline: float) -> list[tuple[str, str, str, int, str]]:
        self._git_call(bare, ["fsck", "--strict", "--no-reflogs", "--no-dangling", commit], deadline=deadline)
        resolved = self._git_call(bare, ["rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}"],
                                  deadline=deadline).strip().decode()
        if resolved != commit:
            raise SourceError("Git commit identity mismatch")
        commit_data = self._git_call(bare, ["cat-file", "commit", commit], deadline=deadline)
        if len(commit) == 40 and git_hash("commit", commit_data) != commit:
            raise SourceError("Git commit digest mismatch")
        first = commit_data.split(b"\n", 1)[0]
        if not re.fullmatch(fr"tree [0-9a-f]{{{len(commit)}}}".encode(), first):
            raise SourceError("Unsupported Git commit tree")
        output = self._git_call(bare, ["ls-tree", "-rlz", "--full-tree", first[5:].decode()], deadline=deadline)
        if output and not output.endswith(b"\0"):
            raise SourceError("Incomplete native Git tree listing")
        records: list[tuple[str, str, str, int, str]] = []
        for raw in output[:-1].split(b"\0") if output else []:
            try:
                metadata, path_bytes = raw.split(b"\t", 1)
                mode, kind, object_id, size_text = metadata.decode("ascii").split()
                path = path_bytes.decode("utf-8")
                size = int(size_text)
            except (ValueError, UnicodeDecodeError) as error:
                raise SourceError("Malformed native Git tree listing") from error
            if str(size) != size_text or size < 0:
                raise SourceError("Malformed native Git object size")
            records.append((mode, kind, object_id, size, path))
        return records

    def _capture_filtered_bare(self, bare: Path, repository: str, commit: str, request: SourceRequest,
                               records: list[tuple[str, str, str, int, str]], deadline: float) -> SourceSnapshot:
        commit_data = self._git_call(bare, ["cat-file", "commit", commit], deadline=deadline)
        tree = commit_data.split(b"\n", 1)[0][5:].decode()
        files: list[SourceFile] = []
        skipped: list[str] = []
        paths: set[str] = set()
        total = 0
        for mode, kind, object_id, size, path in records:
            try:
                legacy_confined_path(path)
            except ValueError as error:
                raise SourceError(f"Unsafe Git source path: {path!r}") from error
            reason = _skipped_reason(path)
            if reason is not None:
                skipped.append(f"{reason}:{path}")
                continue
            if mode in ("120000", "160000"):
                skipped.append(f"{'symlink' if mode == '120000' else 'submodule'}:{path}")
                continue
            if (mode not in ("100644", "100755") or kind != "blob"
                    or not re.fullmatch(fr"[0-9a-f]{{{len(commit)}}}", object_id)):
                raise SourceError("Only regular Git blobs are admitted")
            if path in paths or any(path.startswith(other + "/") or other.startswith(path + "/") for other in paths):
                raise SourceError("Colliding Git source paths")
            if len(files) >= request.max_files or size > request.max_file_bytes or total + size > request.max_bytes:
                raise SourceError("Git source exceeds a requested bound")
            data = self._git_call(bare, ["cat-file", "blob", object_id], cap=request.max_file_bytes + 1,
                                  deadline=deadline)
            if len(data) != size or (len(commit) == 40 and git_hash("blob", data) != object_id):
                raise SourceError("Git blob digest or size mismatch")
            ref = self.store.put(data)
            files.append(SourceFile(path=path, mode=mode, artifact=ref))
            paths.add(path)
            total += size
        return self._make_snapshot(repository, commit, tree, files, skipped)

    def _git_call(self, bare: Path, args: list[str], *, cap: int = 80 * 1024 * 1024,
                  deadline: float | None = None) -> bytes:
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"}
        command = [str(self._git.path), "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never", "-c",
                   "core.fsmonitor=false", "-C", str(bare), *args]
        timeout = 30 if deadline is None else max(0.001, deadline - time.monotonic())
        if deadline is not None and time.monotonic() >= deadline:
            raise SourceError("Native Git source wall-time bound exceeded")
        try:
            completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise SourceError("Native Git source command exceeded wall-time bound") from error
        if len(completed.stdout) > cap:
            raise SourceError("Native Git source output exceeded a byte bound")
        if completed.returncode != 0:
            raise SourceError("Native Git source command failed: " + completed.stderr[-1024:].decode("utf-8", "replace"))
        return completed.stdout

    @staticmethod
    def _https(value: str) -> bool:
        return urlsplit(value).scheme == "https"

    def _make_snapshot(self, repository: str, commit: str | None, tree: str | None, files: list[SourceFile],
                       skipped: list[str]) -> SourceSnapshot:
        ordered = tuple(sorted(files, key=lambda value: value.path))
        skips = tuple(sorted(set(skipped)))
        provisional = SourceSnapshot(repository=repository, commit=commit, tree=tree, files=ordered,
                                     manifest=ArtifactRef(sha256="0" * 64, size=0), skipped=skips)
        manifest = self.store.put_json(self._manifest_value(provisional))
        return provisional.model_copy(update={"manifest": manifest})

    @staticmethod
    def _manifest_value(snapshot: SourceSnapshot) -> dict[str, Any]:
        return {"schema_version": snapshot.schema_version, "repository": snapshot.repository, "commit": snapshot.commit,
                "tree": snapshot.tree,
                "files": [{"path": item.path, "artifact": item.artifact.model_dump(mode="json"), "mode": item.mode}
                          for item in snapshot.files], "skipped": list(snapshot.skipped)}

    def _validate_snapshot(self, snapshot: SourceSnapshot) -> None:
        if not isinstance(snapshot, SourceSnapshot):
            raise ValueError("A v2 SourceSnapshot is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        actual = self.store.get_json(snapshot.manifest)
        if canonical_bytes(actual) != canonical_bytes(self._manifest_value(snapshot)):
            raise SourceError("Source snapshot does not match its immutable manifest")
