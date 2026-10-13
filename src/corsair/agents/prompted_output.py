"""Native response hook for prompted structured output: drop prose before a final bare JSON object.

In prompted mode PydanticAI parses the final text as JSON and already strips a fenced block after prose,
but not a bare object after prose. Live Docker run live-006 (2026-10-13) spent the authoring stage's only
output correction on exactly that ("Both tests were discovered ... The patch is ready.\n\n{...}"). When a
response has no tool call and its text ends with one complete JSON object, only that object is kept; the
dropped prose stays in ``provider_details`` so receipts still show what the model wrote. Anything else
(no object, an object followed by more text, tool calls) is left for the native parser to accept or refuse.
"""

import json
from dataclasses import replace

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

PROSE_KEY = "corsair_dropped_prose"
_DECODER = json.JSONDecoder()


def trailing_object(text: str) -> tuple[str, str] | None:
    """(prose, object) when ``text`` is prose followed by exactly one complete JSON object, else None."""
    body = text.rstrip()
    if body.lstrip().startswith("{"):
        return None
    start = body.find("{")
    while start != -1:
        try:
            value, end = _DECODER.raw_decode(body, start)
        except ValueError:
            value, end = None, -1
        if end == len(body) and isinstance(value, dict):
            return body[:start], body[start:]
        start = body.find("{", start + 1)
    return None


async def keep_trailing_object(ctx: RunContext, *, request_context, response: ModelResponse) -> ModelResponse:
    if any(isinstance(part, ToolCallPart) for part in response.parts):
        return response
    texts = [part for part in response.parts if isinstance(part, TextPart)]
    found = trailing_object("".join(part.content for part in texts)) if texts else None
    if found is None:
        return response
    prose, value = found
    parts = [part for part in response.parts if not isinstance(part, TextPart)] + [TextPart(value)]
    details = dict(response.provider_details or {}) | {PROSE_KEY: prose[:4096]}
    return replace(response, parts=parts, provider_details=details)


def prompted_output() -> Hooks:
    return Hooks(after_model_request=keep_trailing_object)


__all__ = ["PROSE_KEY", "keep_trailing_object", "prompted_output", "trailing_object"]
