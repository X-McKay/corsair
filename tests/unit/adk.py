"""Offline ADK test helpers using the real Runner and BaseLlm interface."""

from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.base_llm import LlmCapabilities
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


class ScriptedLlm(BaseLlm):
    """A deterministic native ADK model; each response represents one request."""

    structured_tools: bool = True

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.structured_tools)

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


def truncated_response(text: str | None = None) -> LlmResponse:
    """A final response that stopped at the output cap, as each ADK route reports it.

    With ``text`` it is ADK's native Gemini shape: the truncated content is kept and
    only ``finish_reason`` says MAX_TOKENS.  Without it, it is the LiteLLM shape for an
    OpenAI-style ``length`` finish, which also stamps the reason as ``error_code``.
    """

    if text is not None:
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            finish_reason=types.FinishReason.MAX_TOKENS,
        )
    return LlmResponse(
        error_code=types.FinishReason.MAX_TOKENS,
        error_message="Maximum tokens reached",
        finish_reason=types.FinishReason.MAX_TOKENS,
    )
