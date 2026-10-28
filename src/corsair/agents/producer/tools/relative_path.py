"""POSIX lexical arithmetic, not filesystem resolution or bypass evidence."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable
from typing import Annotated

from google.adk.tools.tool_context import ToolContext
from pydantic import Field, JsonValue

from corsair.contracts import ProducerInput


def create_relative_path(producer_input: ProducerInput) -> Callable[..., object]:
    """Bind a pure native ADK helper to this episode's output budget."""

    byte_limit = producer_input.budget.tool_output_bytes

    async def relative_path(
        base_root: Annotated[str, Field(min_length=1, max_length=1024)],
        target_path: Annotated[str, Field(min_length=1, max_length=1024)],
        tool_context: ToolContext,
    ) -> dict[str, JsonValue]:
        """Calculate a POSIX path relative to a supplied absolute public base.

        Use only when the source supports these lexical semantics. This does not
        read files, follow symlinks, decode input, execute code or establish bypass.
        """
        del tool_context
        error: dict[str, JsonValue] = {
            "error": "supply bounded absolute POSIX paths without // roots, backslash or NUL",
            "target_executed": False,
        }
        for path in (base_root, target_path):
            if (
                not isinstance(path, str)
                or not 1 <= len(path) <= 1024
                or not path.startswith("/")
                or path.startswith("//")
                or "\\" in path
                or "\x00" in path
            ):
                return error
        base, target = posixpath.normpath(base_root), posixpath.normpath(target_path)
        result: dict[str, JsonValue] = {
            "base_root": base,
            "target_path": target,
            "relative_path": posixpath.relpath(target, base),
            "scope": "lexical_posix_only",
            "target_executed": False,
        }
        try:
            if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > byte_limit:
                return {
                    "error": "relative-path output exceeds the byte limit",
                    "target_executed": False,
                }
        except UnicodeError:
            return error
        return result

    return relative_path
