"""Tool availability: the reader is withdrawn once a read could only repeat one."""

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from ..dependencies import PlanningDependencies
from ._history import run_reads


async def withdraw_when_read(ctx: RunContext[PlanningDependencies], tools: list[ToolDefinition]) -> list[ToolDefinition]:
    """Native tool preparation: once every inventory line was returned in this run, a read can only repeat one.

    PLAN-0036 found re-reads of already returned files exhausting the tool-call budget; withdrawing
    the tool leaves the output tool as the only call.
    """
    covered = {(read.path, line) for read in run_reads(ctx) for line in range(read.start_line, read.end_line + 1)}
    if all((source.path, line) in covered for source in ctx.deps.source_files
           for line in range(1, len(source.content.splitlines()) + 1)):
        return []
    return tools
