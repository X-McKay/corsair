"""Read-only whole-repository source view and the typed results of its bounded tools; no SDK types.

A `SourceTree` is built from an immutable `SourceSnapshot` (or, for tests and fixtures, inline
files). Lines are newline-separated as Git and grep count them, so citations resolve to the same
path and line an operator sees in the commit.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields
from fnmatch import fnmatchcase
from types import MappingProxyType
from typing import Literal

from pydantic import Field, field_validator

from corsair.ports.artifacts import ArtifactStore, SourceSnapshot

from .contracts import Contract, SourceExcerpt, SourceFile, bounded_inventory, confined_path

READ_LINE_LIMIT = 80


@dataclass(frozen=True)
class RepositoryLimits:
    """Operator-owned bounds; agents cannot change them."""
    list_entries: int = 200
    search_matches: int = 40
    search_line_chars: int = 240
    query_chars: int = 200
    read_bytes: int = 16384
    file_bytes: int = 1024 * 1024
    run_bytes: int = 131072

    def __post_init__(self):
        if any(type(getattr(self, f.name)) is not int or getattr(self, f.name) <= 0 for f in fields(self)):
            raise ValueError("repository limits must be positive integers")
        if (self.list_entries > 1000 or self.search_matches > 200 or self.search_line_chars > 1024
                or self.query_chars > 1024 or self.read_bytes > 65536 or self.file_bytes > 16 * 1024 * 1024
                or self.run_bytes > 1024 * 1024 or self.read_bytes > self.run_bytes):
            raise ValueError("repository limits exceed their operator ceilings")


class UnreadableSource(ValueError):
    """The path exists but holds no readable text (binary, oversized or overlong lines)."""


@dataclass(frozen=True)
class SourceTree:
    """Immutable path -> bytes view with lazy, cached UTF-8 decoding."""
    sizes: Mapping[str, int]
    _load: Callable[[str], bytes] = field(repr=False)
    identity: tuple[str, str] | None = None
    _text: dict[str, tuple[str, tuple[str, ...]] | str] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        for path in self.sizes:
            confined_path(path)
        object.__setattr__(self, "sizes", MappingProxyType(dict(sorted(self.sizes.items()))))

    @classmethod
    def from_snapshot(cls, snapshot: SourceSnapshot, store: ArtifactStore) -> "SourceTree":
        refs = {item.path: item.artifact for item in snapshot.files}
        if len(refs) != len(snapshot.files):
            raise ValueError("duplicate snapshot path")
        return cls({path: ref.size for path, ref in refs.items()}, lambda path: store.get(refs[path]),
                   (snapshot.commit, snapshot.tree))

    @classmethod
    def from_files(cls, files: tuple[SourceFile, ...], identity: tuple[str, str] | None = None) -> "SourceTree":
        """Inline fixture files as a tree; identity names the commit and tree they stand for."""
        data = {item.path: item.content.encode("utf-8") for item in files}
        if len(data) != len(files):
            raise ValueError("duplicate source path")
        return cls({path: len(content) for path, content in data.items()}, data.__getitem__, identity)

    def source_files(self, paths: tuple[str, ...], limits: RepositoryLimits) -> tuple[SourceFile, ...]:
        """Inline handoff of selected files, with their exact decoded text, to stages that still take a SPEC-0014 inventory."""
        files = tuple(SourceFile(path=path, content=self._readable(path, limits)[0]) for path in paths)
        bounded_inventory(files)
        return files

    def lines(self, path: str, limits: RepositoryLimits) -> tuple[str, ...]:
        """Newline-separated lines without terminators; a trailing newline adds no line."""
        return self._readable(path, limits)[1]

    def _readable(self, path: str, limits: RepositoryLimits) -> tuple[str, tuple[str, ...]]:
        """Limit checks run on every call; only limit-independent decoding is cached."""
        confined_path(path)
        if path not in self.sizes:
            raise ValueError("source path is absent from the repository")
        if len(path) > 256:
            raise UnreadableSource("source path exceeds 256 characters")
        if self.sizes[path] > limits.file_bytes:
            raise UnreadableSource(f"source file exceeds {limits.file_bytes} bytes")
        cached = self._text.get(path)
        if cached is None:
            cached = self._decode(path)
            self._text[path] = cached
        if isinstance(cached, str):
            raise UnreadableSource(cached)
        return cached

    def _decode(self, path: str) -> tuple[str, tuple[str, ...]] | str:
        data = self._load(path)
        if len(data) != self.sizes[path]:
            raise ValueError("source bytes do not match the recorded size")
        if b"\0" in data:
            return "binary source file"
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return "source file is not UTF-8 text"
        lines = text.split("\n")
        if lines[-1] == "":
            lines.pop()
        lines = [line[:-1] if line.endswith("\r") else line for line in lines]
        if any(len(line) > 16384 for line in lines):
            return "source line exceeds 16384 characters"
        return text, tuple(lines)

    def excerpt(self, path: str, start_line: int, end_line: int, limits: RepositoryLimits) -> SourceExcerpt:
        lines = self.lines(path, limits)
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            raise ValueError("source line range is absent from the repository file")
        if end_line - start_line + 1 > READ_LINE_LIMIT:
            raise ValueError(f"source read exceeds {READ_LINE_LIMIT} lines")
        return SourceExcerpt(path=path, start_line=start_line, end_line=end_line,
                             quote="\n".join(lines[start_line - 1:end_line]))

    def window_end(self, path: str, start_line: int, limits: RepositoryLimits) -> int:
        """Last line of the window from start_line: 80 lines, read_bytes, or end of file."""
        lines = self.lines(path, limits)
        if not 1 <= start_line <= len(lines):
            raise ValueError(f"start_line must be within 1..{len(lines)} for this file" if lines
                             else "source file is empty")
        end, spent = start_line, 0
        while end <= len(lines) and end - start_line < READ_LINE_LIMIT:
            spent += len(lines[end - 1].encode("utf-8")) + 1
            if spent > limits.read_bytes and end > start_line:
                break
            end += 1
        return end - 1

    def under(self, directory: str, pattern: str | None = None) -> list[str]:
        prefix = _directory(directory)
        return [path for path in self.sizes if path.startswith(prefix)
                and (pattern is None or fnmatchcase(path, pattern) or fnmatchcase(path.rsplit("/", 1)[-1], pattern))]


def _directory(directory: str) -> str:
    directory = directory.strip("/")
    if not directory:
        return ""
    confined_path(directory)
    return directory + "/"


class ListedEntry(Contract):
    path: str
    kind: Literal["file", "directory"]
    files: int = Field(ge=1, description="Files in this entry: 1 for a file, all nested files for a directory")
    bytes: int = Field(ge=0)


class SourceListing(Contract):
    directory: str
    pattern: str | None
    entries: tuple[ListedEntry, ...]
    total: int = Field(ge=0, description="Entries that matched before the listing cap")
    truncated: bool


class SearchMatch(Contract):
    path: str
    line: int = Field(ge=1, description="Repository-file line; locate only, read before citing")
    text: str


class SourceSearch(Contract):
    text: str
    directory: str
    pattern: str | None
    matches: tuple[SearchMatch, ...]
    total_matches: int = Field(ge=0)
    files_with_matches: int = Field(ge=0)
    files_searched: int = Field(ge=0)
    files_skipped: int = Field(ge=0, description="Binary, non-UTF-8 or oversized files not searched")
    truncated: bool


class RepeatedRead(Contract):
    """Returned instead of lines when this run already returned the whole window."""
    status: Literal["already_returned"] = "already_returned"
    path: str
    start_line: int
    end_line: int
    note: str = "These lines were already returned in this run and remain in your context; cite them from that earlier result."

    _path = field_validator("path")(confined_path)


def list_tree(tree: SourceTree, limits: RepositoryLimits, directory: str = "", pattern: str | None = None) -> SourceListing:
    prefix = _directory(directory)
    if pattern is not None and not 0 < len(pattern) <= limits.query_chars:
        raise ValueError(f"pattern must be 1..{limits.query_chars} characters")
    paths = tree.under(directory, pattern)
    if pattern is not None:
        entries = [ListedEntry(path=path, kind="file", files=1, bytes=tree.sizes[path]) for path in paths]
    else:
        if prefix and not paths:
            raise ValueError("directory is absent from the repository")
        children: dict[str, list[str]] = {}
        for path in paths:
            name = path[len(prefix):].split("/", 1)[0]
            children.setdefault(prefix + name, []).append(path)
        entries = [ListedEntry(path=child, kind="file", files=1, bytes=tree.sizes[child]) if members == [child]
                   else ListedEntry(path=child, kind="directory", files=len(members),
                                    bytes=sum(tree.sizes[member] for member in members))
                   for child, members in children.items()]
    return SourceListing(directory=prefix.rstrip("/"), pattern=pattern, entries=tuple(entries[:limits.list_entries]),
                         total=len(entries), truncated=len(entries) > limits.list_entries)


def search_tree(tree: SourceTree, limits: RepositoryLimits, text: str, directory: str = "",
                pattern: str | None = None, ignore_case: bool = False) -> SourceSearch:
    """Literal substring search in path order; no regular expressions, so no backtracking cost."""
    if not text.strip() or len(text) > limits.query_chars or "\n" in text:
        raise ValueError(f"search text must be one non-blank line of at most {limits.query_chars} characters")
    if pattern is not None and not 0 < len(pattern) <= limits.query_chars:
        raise ValueError(f"pattern must be 1..{limits.query_chars} characters")
    if _directory(directory) and not tree.under(directory):
        raise ValueError("directory is absent from the repository")
    needle = text.casefold() if ignore_case else text
    matches: list[SearchMatch] = []
    total = files_with = searched = skipped = 0
    for path in tree.under(directory, pattern):
        try:
            lines = tree.lines(path, limits)
        except UnreadableSource:
            skipped += 1
            continue
        searched += 1
        found = False
        for number, line in enumerate(lines, start=1):
            if needle in (line.casefold() if ignore_case else line):
                total += 1
                found = True
                if len(matches) < limits.search_matches:
                    matches.append(SearchMatch(path=path, line=number, text=line.strip()[:limits.search_line_chars]))
        files_with += found
    return SourceSearch(text=text, directory=_directory(directory).rstrip("/"), pattern=pattern, matches=tuple(matches),
                        total_matches=total, files_with_matches=files_with, files_searched=searched,
                        files_skipped=skipped, truncated=total > len(matches))
