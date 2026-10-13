"""Native response hook for prompted structured output: keep exactly one JSON object, refuse the rest by name.

In prompted mode PydanticAI parses the final text as JSON. It strips a fenced block after prose, but not prose
around a bare object, and with two fenced objects it silently takes the first. Live runs on 2026-10-13 spent
the stage's only output correction on such answers: Docker live-006 authoring answered prose then a bare object,
and the corpus rerun's planner answered with about 9k characters of reasoning and no output at all. This hook
runs on every final answer (a response with no tool call):

- exactly one complete JSON object in the text, bare or fenced, with any prose around it: only the object is
  kept; the dropped text stays in ``provider_details`` so receipts still show what the model wrote;
- more than one complete object: refused with ``ModelRetry`` naming the count (one correction, as any refusal);
- no text but reasoning: refused as ``no output after N characters of reasoning``, a failure of its own;
- anything else (no complete object) is left for the native parser to accept or refuse.

A refusal counts against the agent's output retries; it adds none.
"""

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


def trailing_object(text: str) -> tuple[str, str] | None:
    """(dropped text, object) when ``text`` holds exactly one complete JSON object; None otherwise."""
    spans = json_objects(text)
    if len(spans) != 1:
        return None
    start, end = spans[0]
    return (text[:start] + text[end:]).strip(), text[start:end]


async def keep_trailing_object(ctx: RunContext, *, request_context, response: ModelResponse) -> ModelResponse:
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
    found = trailing_object(text)
    if found is None:
        return response
    dropped, value = found
    if not dropped and len(response.parts) == 1:
        return response
    parts = [part for part in response.parts if not isinstance(part, TextPart)] + [TextPart(value)]
    details = dict(response.provider_details or {})
    if dropped:
        details[PROSE_KEY] = dropped[:4096]
    return replace(response, parts=parts, provider_details=details)


def prompted_output() -> Hooks:
    return Hooks(after_model_request=keep_trailing_object)


__all__ = ["NO_OUTPUT", "PROSE_KEY", "json_objects", "keep_trailing_object", "prompted_output", "trailing_object"]
