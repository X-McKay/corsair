"""Native response hook for prompted structured output: keep exactly one JSON object, refuse the rest by name.

Copied from v1 (``corsair.agents.prompted_output``) so v2 imports nothing from v1. The served local model is driven
in prompted mode (its model profile sets it); PydanticAI then parses the final text as JSON, which fails when the
model wraps the object in prose or answers with reasoning only. On every final answer (a response with no tool
call) this hook:

- keeps only the object when the text holds exactly one complete JSON object, bare or fenced, with any prose
  around it; the dropped text stays in ``provider_details`` so transcripts still show what the model wrote;
- refuses more than one complete object with ``ModelRetry`` naming the count;
- refuses a response with reasoning but no text as ``no output after N characters of reasoning``;
- leaves anything else (no complete object) to the native parser.

A refusal counts against the agent's output retries; it adds none.
"""
from __future__ import annotations

import json
from dataclasses import replace

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart

PROSE_KEY = "corsair_dropped_prose"
NO_OUTPUT = "no output after {} characters of reasoning"
_DECODER = json.JSONDecoder()


def json_objects(text: str) -> list[tuple[int, int]]:
    """(start, end) of each complete top-level JSON object in ``text``, outermost and left to right."""
    spans, start = [], text.find("{")
    while start != -1:
        try:
            value, end = _DECODER.raw_decode(text, start)
        except ValueError:
            value, end = None, start
        if isinstance(value, dict):
            spans.append((start, end))
        start = text.find("{", max(end, start + 1))
    return spans


async def keep_one_object(ctx: RunContext, *, request_context, response: ModelResponse) -> ModelResponse:
    if any(isinstance(part, ToolCallPart) for part in response.parts):
        return response
    text = "".join(part.content for part in response.parts if isinstance(part, TextPart))
    if not text.strip():
        reasoning = sum(len(part.content) for part in response.parts if isinstance(part, ThinkingPart))
        if reasoning:
            raise ModelRetry(NO_OUTPUT.format(reasoning) + "; return the final JSON object as text")
        return response
    spans = json_objects(text)
    if len(spans) > 1:
        raise ModelRetry(f"the answer holds {len(spans)} complete JSON objects; return exactly one")
    if len(spans) != 1:
        return response
    start, end = spans[0]
    dropped = (text[:start] + text[end:]).strip()
    if not dropped and len(response.parts) == 1:
        return response
    parts = [part for part in response.parts if not isinstance(part, TextPart)] + [TextPart(text[start:end])]
    details = dict(response.provider_details or {})
    if dropped:
        details[PROSE_KEY] = dropped[:4096]
    return replace(response, parts=parts, provider_details=details)


def prompted_output() -> Hooks:
    return Hooks(after_model_request=keep_one_object)
