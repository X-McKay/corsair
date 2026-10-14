"""The Investigator's tools: the native Harness ``FileSystem`` over a read-only workspace of the revision tree.

No bespoke file tools: ``FileSystem(read_only=True)`` offers ``read_file`` (line-numbered, paged by offset and
limit), ``list_directory``, ``find_files`` (glob) and ``grep`` (regex or literal, with a glob filter), each
bounded, and resolves every path, symlinks included, against the workspace root before any I/O. A path outside
the tree comes back to the model as a refusal. The workspace itself is ``ReadOnlyWorkspace``, so even a tool
that tried to write or run a command would be refused.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.workspaces import LocalWorkspaceBackend, ReadOnlyWorkspace, Workspace
from pydantic_ai_harness import FileSystem

TOOL_NAMES = ("read_file", "list_directory", "find_files", "grep")


def source_tools() -> FileSystem:
    return FileSystem(read_only=True, tools=TOOL_NAMES, content_hashes=False, denied_patterns=["**/.git/**"],
                      max_read_lines=400, max_read_chars=20_000, max_list_results=300, max_search_results=200,
                      max_find_results=300)


def source_workspace(source_root: Path) -> ReadOnlyWorkspace:
    """The run's workspace: the revision tree on this host, read-only."""
    return ReadOnlyWorkspace(Workspace(LocalWorkspaceBackend(source_root)))
