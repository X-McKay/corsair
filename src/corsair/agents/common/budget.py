"""Tool-call budget: withdraw an agent's domain tools once the run's own native cap is reached.

``RunContext.usage_limits.tool_calls_limit`` is the cap the run enforces (``UsageLimits``); withdrawing the tools
when it is reached lets the agent finish with its output instead of attempting a call the limit would refuse.
The cap is operator configuration passed to the run, never prompt text. Copied in spirit from v1's budget hook.
"""
from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.capabilities import PrepareTools
from pydantic_ai.tools import ToolDefinition


HEADROOM = 3
"""Tools go this many calls or requests before either cap: a model can emit several calls in one response, and an
answer (plus one output correction) still needs requests. Live chain run 20261014T110211Z hit both caps outright:
31 tool calls against a cap of 30, and an Investigator that reached its 40th request without answering."""


async def within_tool_budget(ctx: RunContext, tools: list[ToolDefinition]) -> list[ToolDefinition]:
    limits = ctx.usage_limits
    if limits is None:
        return tools
    tool_cap, request_cap = limits.tool_calls_limit, limits.request_limit
    if tool_cap is not None and ctx.usage.tool_calls >= tool_cap - HEADROOM:
        return []
    if request_cap is not None and ctx.usage.requests >= request_cap - HEADROOM:
        return []
    return tools


def tool_budget() -> PrepareTools:
    return PrepareTools(within_tool_budget)
