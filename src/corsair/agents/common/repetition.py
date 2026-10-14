"""Read-loop guard: an identical read-only tool call repeated past a small allowance returns a short notice.

Live run 20261014T091602Z: the Investigator read the same 7-line file 33 times and spent its whole 40-request budget
(1.58M input tokens) without answering. A read-only call with the same arguments returns the same bytes, so after
``ALLOWED`` identical calls the tool is not run again and the model is told to use the result it already has. Only
read-only tools are guarded; a command the Builder re-runs after changing files may legitimately differ.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ToolCallPart

READ_TOOLS = ("read_file", "list_directory", "find_files", "grep", "search_files")
ALLOWED = 2
NOTICE = ("You already made this exact {tool} call {count} times and it returns the same result. Do not repeat it: "
          "use that result, make a different call, or give your final answer now.")


def _key(name: str, args: Any) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"


def repeat_count(ctx: RunContext[Any], call: ToolCallPart) -> int:
    """How many earlier calls in this run had the same tool name and arguments as ``call``."""
    wanted = _key(call.tool_name, call.args_as_dict())
    return sum(1 for message in ctx.messages for part in message.parts
               if isinstance(part, ToolCallPart) and part.tool_call_id != call.tool_call_id
               and _key(part.tool_name, part.args_as_dict()) == wanted)


def read_loop_guard() -> Hooks:
    hooks = Hooks()

    @hooks.on.tool_execute(tools=READ_TOOLS)
    async def guard(ctx: RunContext[Any], *, call: ToolCallPart, tool_def: Any, args: dict[str, Any], handler: Any):
        count = repeat_count(ctx, call)
        if count >= ALLOWED:
            return NOTICE.format(tool=call.tool_name, count=count)
        return await handler(args)

    return hooks
