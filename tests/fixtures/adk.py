"""Offline ADK test helpers using the real Runner and BaseLlm interface."""

from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


class ScriptedLlm(BaseLlm):
    """A deterministic native ADK model; each response represents one request."""

    responses: list[LlmResponse] = Field(default_factory=list)
    requests: list[Any] = Field(default_factory=list)

    async def generate_content_async(self, llm_request: Any, stream: bool = False):
        del stream
        self.requests.append(llm_request)
        if not self.responses:
            raise AssertionError("ScriptedLlm received more requests than scripted responses")
        yield self.responses.pop(0)


def text_response(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def tool_response(name: str, args: dict[str, Any]) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))],
        )
    )


def tool_batch_response(calls: list[tuple[str, dict[str, Any]]]) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(function_call=types.FunctionCall(name=name, args=args))
                for name, args in calls
            ],
        )
    )
