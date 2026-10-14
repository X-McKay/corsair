"""Read-only source access shared by the Probers and the Reviewer: the native Harness ``FileSystem``.

No bespoke file tools. ``FileSystem(read_only=True)`` offers ``read_file`` (line-numbered, paged), ``list_directory``,
``find_files`` (glob) and ``search_files`` (content search in Python, so no command runs), each bounded, and checks
every path, symlinks included, against the workspace root before any I/O. The run's workspace is the revision tree
wrapped in ``ReadOnlyWorkspace``, so even a tool that tried to write would be refused. This mirrors the
Investigator's configuration; ``search_files`` is used instead of ``grep`` because it needs no ``rg`` command.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.workspaces import LocalWorkspaceBackend, ReadOnlyWorkspace, Workspace
from pydantic_ai_harness import FileSystem

TOOL_NAMES = ("read_file", "list_directory", "find_files", "search_files")


def source_tools() -> FileSystem:
    return FileSystem(read_only=True, tools=TOOL_NAMES, content_hashes=False, denied_patterns=["**/.git/**"],
                      max_read_lines=400, max_read_chars=20_000, max_list_results=300, max_search_results=200,
                      max_find_results=300)


def source_workspace(source_root: Path) -> ReadOnlyWorkspace:
    """The run's workspace: one revision's tree on this host, read-only."""
    return ReadOnlyWorkspace(Workspace(LocalWorkspaceBackend(Path(source_root))))


def numbered(content: str) -> str:
    """``content`` with one-based line numbers, as the Reviewer sees the frozen drafts."""
    return "\n".join(f"{n}: {line}" for n, line in enumerate(content.splitlines(), 1))


def source_lines(source_root: Path, path: str) -> list[str] | None:
    """The lines of a UTF-8 file inside ``source_root``, or None when ``path`` leaves the tree or is unreadable."""
    raw = path.strip()
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if raw.startswith("/") or "\0" in raw or ".." in parts or not parts:
        return None
    base = Path(source_root).resolve()
    target = base.joinpath(*parts).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None


__all__ = ["TOOL_NAMES", "numbered", "source_lines", "source_tools", "source_workspace"]
