"""Shared cache and archive safety primitives for immutable source snapshots."""

from __future__ import annotations

import fcntl
import hashlib
import os
import posixpath
import shutil
import stat
import tarfile
import tempfile
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable

from corsair.domain.case import GitSource

SOURCES_ENV = "CORSAIR_SOURCES"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_PATH_LENGTH = 1024
CHUNK_SIZE = 1024 * 1024


def sources_root() -> Path:
    """The operator-owned cache location, evaluated only when acquisition is requested."""
    return Path(os.environ.get(SOURCES_ENV) or Path.cwd() / ".runs" / "sources")


def cache_key(source: GitSource, *, provider: str) -> str:
    """Return a non-sensitive content-addressed cache key.

    Keep the established Git key stable; provider snapshots additionally include the
    provider name because their archive materialization is different from a checkout.
    """
    fields = (source.url, source.commit) if provider == "git" else (provider, source.url, source.commit)
    return hashlib.sha256("\n".join(fields).encode()).hexdigest()[:24]


def acquire_cached(
    source: GitSource,
    *,
    provider: str,
    root: Path | None,
    populate: Callable[[Path], None],
) -> Path:
    """Populate a cache entry once, publishing it atomically after completion."""
    base = Path(root) if root is not None else sources_root()
    base.mkdir(parents=True, exist_ok=True)
    target = base / cache_key(source, provider=provider)
    marker = target / ".corsair-complete"
    lock = base / f".{target.name}.lock"
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            if target.is_symlink():
                raise ValueError("source cache entry must not be a symlink")
            if target.exists() and not target.is_dir():
                raise ValueError("source cache entry must be a directory")
            if _is_complete_marker(marker):
                return target
            if target.exists():
                shutil.rmtree(target)
            staging = base / f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            try:
                staging.mkdir()
                populate(staging)
                marker = staging / ".corsair-complete"
                if marker.exists() or marker.is_symlink():
                    raise ValueError("provider archive contains reserved cache metadata")
                marker.write_text("complete\n")
                os.replace(staging, target)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            return target
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _is_complete_marker(marker: Path) -> bool:
    try:
        mode = marker.lstat().st_mode
    except FileNotFoundError:
        return False
    if marker.is_symlink() or not stat.S_ISREG(mode):
        raise ValueError("source cache completion marker is invalid")
    try:
        complete = marker.read_text() == "complete\n"
    except OSError as error:
        raise ValueError("source cache completion marker is invalid") from error
    if not complete:
        raise ValueError("source cache completion marker is invalid")
    return True


def tree_at(source: GitSource, target: Path) -> Path:
    """Return the requested local subtree without following a link out of the cache."""
    tree = target / source.subdir if source.subdir else target
    if not tree.is_dir() or not tree.resolve().is_relative_to(target.resolve()):
        raise ValueError(f"subdir {source.subdir!r} is not a directory inside the checkout")
    return tree


def install_archive(payload: bytes | BinaryIO | Iterable[bytes], target: Path, *, strip_root: bool) -> None:
    """Download, validate, and unpack a ZIP or tar snapshot into an empty target."""
    with tempfile.NamedTemporaryFile(prefix=".corsair-source-", dir=target, delete=False) as handle:
        archive = Path(handle.name)
        _write_limited(payload, handle)
    unpacked = Path(tempfile.mkdtemp(prefix=".corsair-unpacked-", dir=target.parent))
    try:
        if zipfile.is_zipfile(archive):
            _extract_zip(archive, unpacked)
        elif tarfile.is_tarfile(archive):
            _extract_tar(archive, unpacked)
        else:
            raise ValueError("provider archive is neither ZIP nor tar")
        archive.unlink()
        _move_snapshot_root(unpacked, target, strip_root=strip_root)
        _validate_tree_links(target)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(unpacked, ignore_errors=True)


def _write_limited(payload: bytes | BinaryIO | Iterable[bytes], output: BinaryIO) -> None:
    if isinstance(payload, bytes):
        chunks: Iterable[bytes] = (payload,)
    elif hasattr(payload, "read"):
        chunks = iter(lambda: payload.read(CHUNK_SIZE), b"")
    else:
        chunks = payload
    written = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise ValueError("provider archive stream yielded non-bytes")
        written += len(chunk)
        if written > MAX_ARCHIVE_BYTES:
            raise ValueError("provider archive exceeds compressed-size limit")
        output.write(chunk)


def _archive_path(name: str) -> PurePosixPath:
    if not name or len(name) > MAX_PATH_LENGTH or "\0" in name or "\\" in name:
        raise ValueError("archive entry has an unsafe path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("archive entry escapes the destination")
    return path


def _symlink_target(path: PurePosixPath, target: str) -> str:
    if not target or len(target) > MAX_PATH_LENGTH or "\0" in target or "\\" in target:
        raise ValueError("archive symlink has an unsafe target")
    if target.startswith("/"):
        raise ValueError("archive symlink escapes the destination")
    resolved = posixpath.normpath(str(path.parent / PurePosixPath(target)))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        raise ValueError("archive symlink escapes the destination")
    return target


def _destination(root: Path, path: PurePosixPath) -> Path:
    destination = root.joinpath(*path.parts)
    if not destination.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError("archive entry escapes the destination")
    return destination


def _extract_zip(archive: Path, root: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        _check_archive_limits(len(entries), sum(entry.file_size for entry in entries))
        seen: set[PurePosixPath] = set()
        links: list[tuple[Path, str]] = []
        for entry in entries:
            path = _archive_path(entry.filename.rstrip("/"))
            if path in seen:
                raise ValueError("archive contains duplicate paths")
            seen.add(path)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            is_link = stat.S_ISLNK(mode)
            is_directory = entry.is_dir()
            if kind and kind not in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError("archive contains a special file")
            destination = _destination(root, path)
            if is_directory:
                if is_link or (kind and kind != stat.S_IFDIR):
                    raise ValueError("archive directory has an unsafe type")
                _make_directory(destination)
                _chmod(destination, mode, directory=True)
            elif is_link:
                target = source.read(entry).decode("utf-8", "strict")
                links.append((destination, _symlink_target(path, target)))
            else:
                if kind and kind != stat.S_IFREG:
                    raise ValueError("archive entry has an unsafe type")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as reader, destination.open("xb") as output:
                    shutil.copyfileobj(reader, output, CHUNK_SIZE)
                _chmod(destination, mode)
        _create_links(links, root)


def _extract_tar(archive: Path, root: Path) -> None:
    with tarfile.open(archive, "r:*") as source:
        seen: set[PurePosixPath] = set()
        links: list[tuple[Path, str]] = []
        count = 0
        extracted = 0
        while entry := source.next():
            count += 1
            extracted += entry.size if entry.isfile() else 0
            _check_archive_limits(count, extracted)
            path = _archive_path(entry.name.rstrip("/"))
            if path in seen:
                raise ValueError("archive contains duplicate paths")
            seen.add(path)
            destination = _destination(root, path)
            if entry.isdir():
                _make_directory(destination)
                _chmod(destination, entry.mode, directory=True)
            elif entry.isfile():
                reader = source.extractfile(entry)
                if reader is None:
                    raise ValueError("archive regular file has no content")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with reader, destination.open("xb") as output:
                    shutil.copyfileobj(reader, output, CHUNK_SIZE)
                _chmod(destination, entry.mode)
            elif entry.issym():
                links.append((destination, _symlink_target(path, entry.linkname)))
            else:
                raise ValueError("archive contains a special file or hard link")
        _create_links(links, root)


def _check_archive_limits(count: int, extracted: int) -> None:
    if count > MAX_ARCHIVE_FILES:
        raise ValueError("provider archive exceeds file-count limit")
    if extracted > MAX_EXTRACTED_BYTES:
        raise ValueError("provider archive exceeds extracted-size limit")


def _chmod(path: Path, mode: int, *, directory: bool = False) -> None:
    permissions = mode & 0o777 if mode else (0o755 if directory else 0o644)
    # Git trees do not track directory modes; extraction must remain traversable by its owner.
    path.chmod(permissions | 0o700 if directory else permissions)


def _make_directory(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("archive directory conflicts with an existing path")


def _create_links(links: list[tuple[Path, str]], root: Path) -> None:
    for destination, target in links:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise ValueError("archive link conflicts with an existing path")
        os.symlink(target, destination)
    _validate_tree_links(root)


def _validate_tree_links(root: Path) -> None:
    root = root.resolve()
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            link = Path(parent) / name
            if not link.is_symlink():
                continue
            try:
                resolved = link.resolve(strict=False)
            except RuntimeError as error:
                raise ValueError("archive symlink is cyclic") from error
            if not resolved.is_relative_to(root):
                raise ValueError("archive symlink escapes the destination")


def _move_snapshot_root(unpacked: Path, target: Path, *, strip_root: bool) -> None:
    entries = list(unpacked.iterdir())
    source = unpacked
    if strip_root:
        if len(entries) != 1 or not entries[0].is_dir() or entries[0].is_symlink():
            raise ValueError("provider archive is missing its expected wrapper directory")
        source = entries[0]
    marker = source / ".corsair-complete"
    if marker.exists() or marker.is_symlink():
        raise ValueError("provider archive contains reserved cache metadata")
    for entry in list(source.iterdir()):
        entry.rename(target / entry.name)
