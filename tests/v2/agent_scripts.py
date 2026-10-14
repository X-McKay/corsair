"""A scripted native FunctionModel for v2 agent tests: one step per model request, no live inference.

A step is a tool call ``("tool_name", {args})``, a final answer (a dict, sent through the agent's output tool, or
as JSON text in prompted mode), or a callable ``(messages, info) -> ModelResponse``. Every response reports fixed
token counts so usage capture can be checked against known numbers.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

INPUT_TOKENS, OUTPUT_TOKENS = 100, 10


class Script:
    def __init__(self, steps: Sequence[Any]):
        self.steps, self.index = list(steps), 0
        self.seen: list[list[ModelMessage]] = []
        self.model = FunctionModel(self, model_name="scripted")

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.seen.append(list(messages))
        if self.index >= len(self.steps):
            raise AssertionError(f"script exhausted after {self.index} steps")
        step, self.index = self.steps[self.index], self.index + 1
        if callable(step):
            response = step(messages, info)
        elif isinstance(step, tuple):
            response = ModelResponse(parts=[ToolCallPart(step[0], step[1])])
        elif info.output_tools:
            response = ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step)])
        else:
            response = ModelResponse(parts=[TextPart(json.dumps(step))])
        usage = RequestUsage(input_tokens=INPUT_TOKENS, output_tokens=OUTPUT_TOKENS)
        return ModelResponse(parts=response.parts, usage=usage, model_name="scripted")


def tool_returns(messages: Sequence[ModelMessage]) -> list[Any]:
    """Every tool result and retry prompt in ``messages``, in order, as (kind, tool_name, content)."""
    found = []
    for message in messages:
        for part in message.parts:
            kind = type(part).__name__
            if kind in ("ToolReturnPart", "RetryPromptPart", "LoadCapabilityReturnPart"):
                found.append((kind, getattr(part, "tool_name", None), part.content))
    return found


ScriptStep = tuple[str, dict] | dict | Callable[..., ModelResponse]
