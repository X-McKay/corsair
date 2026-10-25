"""Safe, deterministic admission of local Python source snapshots.

Only bytes in an immutable artifact are later exposed to an investigator or mounted in
an execution container. This module deliberately never returns a path to the admitted
local checkout after :func:`snapshot_source` completes.
"""

from __future__ import annotations

import io
import os
import stat
import sys
import tarfile
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path, PurePosixPath

from corsair.contracts import ArtifactRef, Case, PreparedCase, RunManifest, Source, safe_path
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings


class SourceAdmissionError(ValueError):
    """The source cannot be safely represented by a bounded immutable snapshot."""


_EXCLUDED_DIRECTORIES = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
_SENSITIVE_BASENAMES = {
    "oracle.json",
    "expected.json",
    "ground_truth.json",
    "truth.json",
    "answer.json",
    "answers.json",
    "secret.txt",
    "secrets.json",
}
# These are the maximum values Settings permits. They bound reads of a snapshot
# artifact even where the compact public read_source API receives no Settings.
_MAX_SNAPSHOT_FILES = 10_000
_MAX_SNAPSHOT_BYTES = 33_554_432

# Source admission is a Linux-only pilot boundary. Record support before tests or
# callers can replace os.open, and never substitute path-based traversal if it is absent.
_SECURE_SOURCE_SUPPORTED = (
    sys.platform.startswith("linux")
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in getattr(os, "supports_dir_fd", ())
    and os.stat in getattr(os, "supports_dir_fd", ())
    and os.stat in getattr(os, "supports_follow_symlinks", ())
    and os.scandir in getattr(os, "supports_fd", ())
)


def _safe_relative(value: str, *, allow_dot: bool = False) -> PurePosixPath:
    """Validate a caller-provided relative POSIX path without resolving it."""
    if allow_dot and value == ".":
        return PurePosixPath(".")
    try:
        safe_path(value)
    except ValueError as exc:
        raise SourceAdmissionError(str(exc)) from exc
    return PurePosixPath(value)


def _is_sensitive(path: PurePosixPath) -> bool:
    lower = path.name.lower()
    parts = lower.replace("-", "_").replace(".", "_").split("_")
    return (
        lower in _SENSITIVE_BASENAMES
        or "oracle" in parts
        or "truth" in parts
        or lower == ".env"
        or lower.startswith(".env.")
    )


def _require_secure_source_support() -> int:
    """Return no-follow directory flags or reject platforms lacking the required APIs."""
    if not _SECURE_SOURCE_SUPPORTED:
        raise SourceAdmissionError(
            "secure source admission requires Linux fd-based no-follow support"
        )
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _open_source_root(root: Path, directory_flags: int) -> int:
    """Open the configured trusted root and reject a replacement during the open."""
    try:
        expected = os.stat(root, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise SourceAdmissionError("configured source_root does not exist") from exc
    except OSError as exc:
        raise SourceAdmissionError("cannot inspect configured source_root") from exc
    if stat.S_ISLNK(expected.st_mode):
        raise SourceAdmissionError("configured source_root must not be a symbolic link")
    if not stat.S_ISDIR(expected.st_mode):
        raise SourceAdmissionError("configured source_root is not a directory")
    try:
        descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise SourceAdmissionError("cannot safely open configured source_root") from exc
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISDIR(actual.st_mode) or not _same_inode(expected, actual):
            raise SourceAdmissionError("configured source_root changed while it was being admitted")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    directory_flags: int,
    *,
    symbolic_error: str,
    non_directory_error: str,
) -> int:
    """Pin one child directory under ``parent_fd`` and verify its identity."""
    if stat.S_ISLNK(expected.st_mode):
        raise SourceAdmissionError(symbolic_error)
    if not stat.S_ISDIR(expected.st_mode):
        raise SourceAdmissionError(non_directory_error)
    try:
        descriptor = os.open(name, directory_flags, dir_fd=parent_fd)
    except OSError as exc:
        raise SourceAdmissionError("source changed while it was being admitted") from exc
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISDIR(actual.st_mode) or not _same_inode(expected, actual):
            raise SourceAdmissionError("source changed while it was being admitted")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _admitted_directory(source: Source, settings: Settings) -> int:
    """Return a pinned non-symlink source directory below the trusted root descriptor."""
    directory_flags = _require_secure_source_support()
    root = Path(settings.source_root).absolute()
    raw = Path(source.path)
    if raw.is_absolute():
        try:
            relative_text = raw.relative_to(root).as_posix()
        except ValueError as exc:
            raise SourceAdmissionError("absolute source is outside configured source_root") from exc
    else:
        relative_text = source.path
    relative = _safe_relative(relative_text, allow_dot=True)

    cursor_fd = _open_source_root(root, directory_flags)
    try:
        parts = tuple(part for part in relative.parts if part != ".")
        for index, part in enumerate(parts):
            try:
                expected = os.stat(part, dir_fd=cursor_fd, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise SourceAdmissionError("source path does not exist") from exc
            except OSError as exc:
                raise SourceAdmissionError("cannot inspect source path") from exc
            final_component = index == len(parts) - 1
            next_fd = _open_directory(
                cursor_fd,
                part,
                expected,
                directory_flags,
                symbolic_error="source path contains a symbolic link",
                non_directory_error=(
                    "source must be a directory below configured source_root"
                    if final_component
                    else "source path has a non-directory component"
                ),
            )
            os.close(cursor_fd)
            cursor_fd = next_fd
        return cursor_fd
    except BaseException:
        os.close(cursor_fd)
        raise


def _directory_entries(directory_fd: int) -> list[os.DirEntry[str]]:
    """Read one pinned directory, retaining no path string for later descent."""
    try:
        with os.scandir(directory_fd) as scan:
            return sorted(scan, key=lambda entry: entry.name)
    except OSError as exc:
        raise SourceAdmissionError("source changed while it was being admitted") from exc


def _iter_regular_files(
    directory_fd: int, settings: Settings
) -> Generator[tuple[PurePosixPath, int, str, os.stat_result], None, None]:
    """Walk pinned descriptors in lexical order, rejecting every unadmitted entry."""
    directory_flags = _require_secure_source_support()
    emitted = 0

    def walk(
        parent_fd: int, relative_directory: PurePosixPath
    ) -> Iterator[tuple[PurePosixPath, int, str, os.stat_result]]:
        nonlocal emitted
        directories: list[tuple[str, PurePosixPath, os.stat_result]] = []
        files: list[tuple[str, PurePosixPath, os.stat_result]] = []
        for entry in _directory_entries(parent_fd):
            relative = relative_directory / entry.name
            try:
                metadata = entry.stat(follow_symlinks=False)
            except FileNotFoundError as exc:
                raise SourceAdmissionError("source changed while it was being admitted") from exc
            except OSError as exc:
                raise SourceAdmissionError("cannot inspect admitted source entry") from exc
            if stat.S_ISDIR(metadata.st_mode):
                if entry.name not in _EXCLUDED_DIRECTORIES:
                    directories.append((entry.name, relative, metadata))
            else:
                files.append((entry.name, relative, metadata))

        # os.walk yielded current files before descending sorted child directories; preserve
        # that established member order so unchanged datasets retain their tar digests.
        for name, relative, metadata in files:
            if stat.S_ISLNK(metadata.st_mode):
                raise SourceAdmissionError(f"symbolic links are not admitted: {relative}")
            if not stat.S_ISREG(metadata.st_mode):
                raise SourceAdmissionError(f"special files are not admitted: {relative}")
            if _is_sensitive(relative):
                raise SourceAdmissionError(
                    f"sensitive/evaluation file is not admitted: {relative.name}"
                )
            _safe_relative(relative.as_posix())
            emitted += 1
            if emitted > settings.source_limit_files:
                raise SourceAdmissionError("source exceeds configured file limit")
            yield relative, parent_fd, name, metadata

        for name, relative, metadata in directories:
            child_fd = _open_directory(
                parent_fd,
                name,
                metadata,
                directory_flags,
                symbolic_error=f"symbolic links are not admitted: {relative}",
                non_directory_error=f"special files are not admitted: {relative}",
            )
            try:
                yield from walk(child_fd, relative)
            finally:
                os.close(child_fd)

    yield from walk(directory_fd, PurePosixPath("."))


def _read_regular_file(
    parent_fd: int, name: str, metadata: os.stat_result, remaining: int
) -> bytes:
    """Read at most ``remaining`` bytes from a pinned parent without following links."""
    if metadata.st_size > remaining:
        raise SourceAdmissionError("source exceeds configured byte limit")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise SourceAdmissionError("cannot safely open admitted source file") from exc
    try:
        actual = os.fstat(descriptor)
        if (
            not stat.S_ISREG(actual.st_mode)
            or not _same_inode(actual, metadata)
            or actual.st_size != metadata.st_size
            or actual.st_mtime_ns != metadata.st_mtime_ns
        ):
            raise SourceAdmissionError("source changed while it was being admitted")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(remaining + 1)
        if len(content) > remaining:
            raise SourceAdmissionError("source exceeds configured byte limit")
        after = os.fstat(descriptor)
        if (
            not _same_inode(after, actual)
            or after.st_size != actual.st_size
            or after.st_mtime_ns != actual.st_mtime_ns
        ):
            raise SourceAdmissionError("source changed while it was being admitted")
        return content
    except OSError as exc:
        raise SourceAdmissionError("cannot read admitted source file") from exc
    finally:
        os.close(descriptor)


def snapshot_source(source: Source, settings: Settings, store: ArtifactStore) -> ArtifactRef:
    """Store a deterministic bounded tar snapshot and enforce ``expected_digest``."""
    directory_fd = _admitted_directory(source, settings)
    entries: list[tuple[PurePosixPath, bytes]] = []
    total = 0
    files = _iter_regular_files(directory_fd, settings)
    try:
        for relative, parent_fd, name, metadata in files:
            content = _read_regular_file(
                parent_fd, name, metadata, settings.source_limit_bytes - total
            )
            total += len(content)
            entries.append((relative, content))
    finally:
        files.close()
        os.close(directory_fd)

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for relative, content in entries:
            info = tarfile.TarInfo(relative.as_posix())
            info.size = len(content)
            info.mode = 0o444
            info.uid = 0
            info.gid = 0
            info.mtime = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    ref = store.put(buffer.getvalue(), "application/x-tar")
    if source.expected_digest and ref.sha256 != source.expected_digest:
        raise SourceAdmissionError("source snapshot digest does not match expected_digest")
    return ref


def _archive_members(ref: ArtifactRef, store: ArtifactStore) -> dict[str, tarfile.TarInfo]:
    """Validate a pinned artifact as a safe, bounded regular-file source snapshot."""
    if ref.media_type != "application/x-tar":
        raise SourceAdmissionError("source artifact has an unexpected media type")
    content = store.get(ref)
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
            members: dict[str, tarfile.TarInfo] = {}
            total = 0
            for member in archive.getmembers():
                name = member.name
                try:
                    _safe_relative(name)
                except SourceAdmissionError as exc:
                    raise SourceAdmissionError("source artifact contains an unsafe member") from exc
                if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                    raise SourceAdmissionError("source artifact contains a non-regular member")
                if name in members:
                    raise SourceAdmissionError("source artifact contains duplicate members")
                if member.size < 0:
                    raise SourceAdmissionError("source artifact has an invalid member size")
                total += member.size
                if len(members) + 1 > _MAX_SNAPSHOT_FILES or total > _MAX_SNAPSHOT_BYTES:
                    raise SourceAdmissionError("source artifact exceeds snapshot safety limits")
                members[name] = member
            return members
    except tarfile.TarError as exc:
        raise SourceAdmissionError("source artifact is not a valid uncompressed tar") from exc


def _read_member(ref: ArtifactRef, store: ArtifactStore, member: tarfile.TarInfo) -> bytes:
    content = store.get(ref)
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
            stream = archive.extractfile(member)
            if stream is None:
                raise SourceAdmissionError("source artifact member cannot be read")
            data = stream.read(member.size + 1)
    except tarfile.TarError as exc:
        raise SourceAdmissionError("source artifact is not a valid uncompressed tar") from exc
    if len(data) != member.size:
        raise SourceAdmissionError("source artifact member has an unexpected size")
    return data


def read_source(ref: ArtifactRef, path: str, store: ArtifactStore, max_bytes: int) -> str:
    """Read UTF-8 source exclusively from a safe immutable snapshot artifact."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    normalized = _safe_relative(path).as_posix()
    member = _archive_members(ref, store).get(normalized)
    if member is None:
        raise SourceAdmissionError("requested source path is absent from snapshot")
    if member.size > max_bytes:
        raise SourceAdmissionError("requested source excerpt exceeds byte limit")
    try:
        return _read_member(ref, store, member).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceAdmissionError("source excerpts must be valid UTF-8") from exc


def iter_snapshot_files(ref: ArtifactRef, store: ArtifactStore) -> Iterable[tuple[str, bytes]]:
    """Yield only members accepted by the shared immutable snapshot validator."""
    members = _archive_members(ref, store)
    for name in sorted(members):
        yield name, _read_member(ref, store, members[name])


def _excerpt(text: str, line: int | None) -> str:
    lines = text.splitlines()
    if line is None:
        selected = list(enumerate(lines[:160], start=1))
    else:
        start = max(1, line - 20)
        end = min(len(lines), line + 20)
        selected = list(enumerate(lines[start - 1 : end], start=start))
    excerpt = "\n".join(f"{number}: {value}" for number, value in selected)
    return excerpt[:12000]


def prepare_case(
    case: Case, settings: Settings, store: ArtifactStore, manifest: RunManifest
) -> PreparedCase:
    """Freeze source revisions before an agent is given only a pinned source excerpt."""
    source = snapshot_source(case.source, settings, store)
    read_source(source, case.recipe.module_file, store, settings.source_limit_bytes)
    finding_text = read_source(source, case.finding.file, store, settings.source_limit_bytes)
    fixed_source = (
        snapshot_source(case.fixed_source, settings, store)
        if case.fixed_source is not None
        else None
    )
    if fixed_source is not None:
        read_source(fixed_source, case.recipe.module_file, store, settings.source_limit_bytes)
    return PreparedCase(
        case_id=case.case_id,
        finding=case.finding,
        recipe=case.recipe,
        source=source,
        fixed_source=fixed_source,
        source_excerpt=_excerpt(finding_text, case.finding.line),
        manifest=manifest,
    )
