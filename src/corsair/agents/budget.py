"""Native tool-call budget disclosure: function tools are withdrawn once the run's own cap is reached.

``RunContext.usage_limits`` is the cap the run enforces; preparing tools against it leaves only the output
contract, so a stage that spent its tool calls returns its typed output instead of dying on the next call
(SPEC-0043). The cap itself stays operator configuration, never prompt text.
"""

from pydantic_ai import RunContext
from pydantic_ai.capabilities import PrepareTools
from pydantic_ai.tools import ToolDefinition


async def within_tool_budget(ctx: RunContext, tools: list[ToolDefinition]) -> list[ToolDefinition]:
    cap = ctx.usage_limits.tool_calls_limit if ctx.usage_limits is not None else None
    return [] if cap is not None and ctx.usage.tool_calls >= cap else tools


def tool_budget() -> PrepareTools:
    return PrepareTools(within_tool_budget)


__all__ = ["tool_budget", "within_tool_budget"]
