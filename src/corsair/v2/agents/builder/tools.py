"""The Builder's tools: ``run`` (one argv in the run's workspace) plus the native read-only Harness file tools.

``run`` goes through ``ctx.workspace``, the native PydanticAI Workspace the stage passes to the run (a Docker
container in production, a local directory in tests), so the tool never knows which backend it drives. It runs
argv lists only, never a shell string, because the recipe it feeds is argv lists. A timeout or an output overflow
is a result the model can react to; a lost workspace propagates as the infrastructure failure it is.
"""
from __future__ import annotations

from typing import Any

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.workspaces import WorkspaceOutputLimitError, WorkspaceTimeoutError
from pydantic_ai_harness import FileSystem

TOOLSET_ID = "builder"
DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S = 300, 900
OUTPUT_CHARS = 6_000
"""Output kept per command: the head and the tail, where install and test errors usually are."""


def clip(text: str, limit: int = OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... [{len(text) - limit} characters omitted] ...\n{text[-half:]}"


async def run(ctx: RunContext[Any], argv: list[str], timeout_s: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Run one command in the workspace's working directory and return its exit code and output.

    Args:
        argv: The command as a list of arguments, run without a shell, e.g. ["python", "-m", "pytest", "-q"].
        timeout_s: Seconds before the command is stopped (at most 900).
    """
    if not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ModelRetry("argv must be a non-empty list of non-empty strings")
    timeout = min(max(int(timeout_s), 1), MAX_TIMEOUT_S)
    try:
        result = await ctx.workspace.run(argv, timeout=timeout)
    except WorkspaceTimeoutError as error:
        return {"exit_code": None, "timed_out": True, "output": clip(error.stdout + error.stderr)}
    except WorkspaceOutputLimitError as error:
        return {"exit_code": None, "output_limit": True, "output": clip(error.stdout + error.stderr)}
    return {"exit_code": result.exit_code, "output": clip(result.stdout + result.stderr)}


def builder_tools() -> FunctionToolset[Any]:
    tools = FunctionToolset[Any](id=TOOLSET_ID)
    tools.add_function(run, name="run", retries=1)
    return tools


def file_tools() -> FileSystem:
    return FileSystem(read_only=True, tools=("read_file", "list_directory", "find_files"), content_hashes=False,
                      denied_patterns=["**/.git/**"], max_read_lines=400, max_read_chars=20_000,
                      max_list_results=300, max_find_results=300)
