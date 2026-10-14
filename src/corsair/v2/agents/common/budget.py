"""Tool-call budget: withdraw an agent's domain tools once the run's own native cap is reached.

``RunContext.usage_limits.tool_calls_limit`` is the cap the run enforces (``UsageLimits``); withdrawing the tools
when it is reached lets the agent finish with its output instead of attempting a call the limit would refuse.
The cap is operator configuration passed to the run, never prompt text. Copied in spirit from v1's budget hook.
"""
from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.capabilities import PrepareTools
from pydantic_ai.tools import ToolDefinition


async def within_tool_budget(ctx: RunContext, tools: list[ToolDefinition]) -> list[ToolDefinition]:
    cap = ctx.usage_limits.tool_calls_limit if ctx.usage_limits is not None else None
    return [] if cap is not None and ctx.usage.tool_calls >= cap else tools


def tool_budget() -> PrepareTools:
    return PrepareTools(within_tool_budget)
