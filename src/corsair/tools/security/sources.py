"""Safe, deterministic admission of local Python source snapshots.

Only bytes in an immutable artifact are later exposed to an investigator or mounted in
an execution container. This module deliberately never returns a path to the admitted
local checkout after :func:`snapshot_source` completes.
"""

from __future__ import annotations

import io
import os
import stat
import tarfile
from collections.abc import Iterable
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


def _admitted_directory(source: Source, settings: Settings) -> Path:
    """Return a non-symlink directory lexically below ``source_root``.

    Absolute sources are supported when they are lexically within source_root. The
    caller must preserve the source spelling (use ``Path.absolute()``, not ``resolve``)
    so lstat below can reject every symlink hop before any file is opened.
    """
    root = Path(settings.source_root).resolve(strict=True)
    root_mode = root.stat().st_mode
    if not stat.S_ISDIR(root_mode):
        raise SourceAdmissionError("configured source_root is not a directory")
    raw = Path(source.path)
    if raw.is_absolute():
        try:
            relative_text = raw.relative_to(root).as_posix()
        except ValueError as exc:
            raise SourceAdmissionError("absolute source is outside configured source_root") from exc
    else:
        relative_text = source.path
    relative = _safe_relative(relative_text, allow_dot=True)

    cursor = root
    for part in relative.parts:
        if part == ".":
            continue
        cursor = cursor / part
        try:
            mode = cursor.lstat().st_mode
        except FileNotFoundError as exc:
            raise SourceAdmissionError("source path does not exist") from exc
        if stat.S_ISLNK(mode):
            raise SourceAdmissionError("source path contains a symbolic link")
        if not stat.S_ISDIR(mode) and part != relative.parts[-1]:
            raise SourceAdmissionError("source path has a non-directory component")
    try:
        mode = cursor.lstat().st_mode
    except FileNotFoundError as exc:
        raise SourceAdmissionError("source path does not exist") from exc
    if not stat.S_ISDIR(mode):
        raise SourceAdmissionError("source must be a directory below configured source_root")
    return cursor


def _iter_regular_files(
    directory: Path, settings: Settings
) -> Iterable[tuple[PurePosixPath, Path, os.stat_result]]:
    """Walk safely in lexical order, pruning ignored trees before they are scanned."""
    emitted = 0
    for current_text, directory_names, file_names in os.walk(
        directory, topdown=True, followlinks=False
    ):
        current = Path(current_text)
        relative_directory = PurePosixPath(current.relative_to(directory).as_posix())
        admitted_directories: list[str] = []
        for name in sorted(directory_names):
            if name in _EXCLUDED_DIRECTORIES:
                continue
            child = current / name
            relative = relative_directory / name
            try:
                mode = child.lstat().st_mode
            except FileNotFoundError as exc:
                raise SourceAdmissionError("source changed while it was being admitted") from exc
            if stat.S_ISLNK(mode):
                raise SourceAdmissionError(f"symbolic links are not admitted: {relative}")
            if not stat.S_ISDIR(mode):
                raise SourceAdmissionError(f"special files are not admitted: {relative}")
            admitted_directories.append(name)
        # Mutating this list is how os.walk prunes traversal before eager descent.
        directory_names[:] = admitted_directories

        for name in sorted(file_names):
            child = current / name
            relative = relative_directory / name
            try:
                metadata = child.lstat()
            except FileNotFoundError as exc:
                raise SourceAdmissionError("source changed while it was being admitted") from exc
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
            yield relative, child, metadata


def _read_regular_file(path: Path, metadata: os.stat_result, remaining: int) -> bytes:
    """Read at most ``remaining`` bytes, refusing symlink races and post-stat changes."""
    if metadata.st_size > remaining:
        raise SourceAdmissionError("source exceeds configured byte limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SourceAdmissionError("cannot safely open admitted source file") from exc
    try:
        actual = os.fstat(descriptor)
        if (
            not stat.S_ISREG(actual.st_mode)
            or actual.st_dev != metadata.st_dev
            or actual.st_ino != metadata.st_ino
            or actual.st_size != metadata.st_size
        ):
            raise SourceAdmissionError("source changed while it was being admitted")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(remaining + 1)
        if len(content) > remaining:
            raise SourceAdmissionError("source exceeds configured byte limit")
        after = os.fstat(descriptor)
        if after.st_size != actual.st_size or after.st_mtime_ns != actual.st_mtime_ns:
            raise SourceAdmissionError("source changed while it was being admitted")
        return content
    except OSError as exc:
        raise SourceAdmissionError("cannot read admitted source file") from exc
    finally:
        os.close(descriptor)


def snapshot_source(source: Source, settings: Settings, store: ArtifactStore) -> ArtifactRef:
    """Store a deterministic bounded tar snapshot and enforce ``expected_digest``."""
    directory = _admitted_directory(source, settings)
    entries: list[tuple[PurePosixPath, bytes]] = []
    total = 0
    for relative, path, metadata in _iter_regular_files(directory, settings):
        content = _read_regular_file(path, metadata, settings.source_limit_bytes - total)
        total += len(content)
        entries.append((relative, content))

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


def list_snapshot_paths(ref: ArtifactRef, store: ArtifactStore) -> list[str]:
    """List only paths validated by the same artifact validator used for execution."""
    return sorted(_archive_members(ref, store))


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
    module_text = read_source(source, case.recipe.module_file, store, settings.source_limit_bytes)
    finding_text = read_source(source, case.finding.file, store, settings.source_limit_bytes)
    fixed_source = (
        snapshot_source(case.fixed_source, settings, store)
        if case.fixed_source is not None
        else None
    )
    if fixed_source is not None:
        read_source(fixed_source, case.recipe.module_file, store, settings.source_limit_bytes)
    _ = module_text
    return PreparedCase(
        case_id=case.case_id,
        finding=case.finding,
        recipe=case.recipe,
        source=source,
        fixed_source=fixed_source,
        source_excerpt=_excerpt(finding_text, case.finding.line),
        manifest=manifest,
    )
