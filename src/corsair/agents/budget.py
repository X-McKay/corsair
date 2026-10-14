"""Native tool-call budget disclosure: domain function tools are withdrawn once the run's own cap is reached.

``RunContext.usage_limits`` is the cap the run enforces; withdrawing domain tools lets a stage finish with its output
contract rather than attempt another domain call
(SPEC-0043). Native reserved tools such as load_capability can remain offered; UsageLimits still rejects
any call beyond the hard cap before execution. The cap stays operator configuration, never prompt text.
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
