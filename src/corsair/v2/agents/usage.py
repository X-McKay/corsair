"""Provider-boundary usage-presence capture for native PydanticAI models.

The adapter observes OpenAI Chat Completions JSON through httpx's supported
response hook. It does not parse/replace the provider protocol or alter native
PydanticAI response usage. Capture is scoped to one wrapped request with a
ContextVar, so concurrent agent requests cannot exchange presence metadata.
"""
from __future__ import annotations

import json
from contextvars import ContextVar, Token
from time import perf_counter
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

# The list is request-local (ContextVar context is copied per asyncio task).
# The hook is only active while ProviderUsageModel.request() is awaiting the
# corresponding native provider call.
_CURRENT_OPENAI_OBSERVATIONS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "corsair_current_openai_usage_observations", default=None
)


def _is_streaming_request(request: httpx.Request) -> bool:
    """Do not consume an event stream in an HTTP response hook."""
    try:
        body = request.content
        payload = json.loads(body) if body else None
    except (AttributeError, RuntimeError, ValueError, TypeError):
        return True
    return isinstance(payload, dict) and payload.get("stream") is True


def _reported_count(mapping: Any, key: str) -> bool:
    if not isinstance(mapping, dict):
        return False
    value = mapping.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _presence_metadata(payload: Any, latency_seconds: float, provider_name: str) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    usage = usage if isinstance(usage, dict) else None
    prompt_details = usage.get("prompt_tokens_details") if usage else None
    completion_details = usage.get("completion_tokens_details") if usage else None
    fields = {
        "input_tokens": _reported_count(usage, "prompt_tokens"),
        "output_tokens": _reported_count(usage, "completion_tokens"),
        "cache_read_tokens": _reported_count(prompt_details, "cached_tokens"),
        # Chat Completions does not currently report cache-write usage. Leave
        # this false rather than deriving zero from PydanticAI's normalized use.
        "cache_write_tokens": False,
        "reasoning_tokens": _reported_count(completion_details, "reasoning_tokens"),
    }
    # Keep only the provider's usage object, not prompts, completions, or tools.
    return {
        "schema": "corsair.provider-usage-presence.v1",
        "source": "provider-response-boundary",
        "provider": provider_name,
        "fields": fields,
        "raw_usage": usage,
        "request_latency_seconds": max(0.0, latency_seconds),
        "request_attempts": 1,
    }


async def openai_usage_response_hook(response: httpx.Response) -> None:
    """Capture response usage only when a Corsair wrapped request is active."""
    observations = _CURRENT_OPENAI_OBSERVATIONS.get()
    if observations is None or _is_streaming_request(response.request):
        return
    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type:
        return
    try:
        # For non-stream JSON the native SDK reads and parses this same bounded
        # response body immediately afterwards. We retain only its usage object.
        body = await response.aread()
        payload = json.loads(body)
    except (httpx.HTTPError, ValueError, TypeError):
        return
    observations.append({"payload": payload})


class ProviderUsageModel(WrapperModel):
    """Annotate native model responses with provider-boundary presence data."""

    def __init__(self, wrapped: Model, provider_name: str = "openai") -> None:
        super().__init__(wrapped)
        self.provider_name = provider_name

    async def aclose(self) -> None:
        await self.wrapped.client.close()

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        observations: list[dict[str, Any]] = []
        context_token: Token[list[dict[str, Any]] | None] = _CURRENT_OPENAI_OBSERVATIONS.set(observations)
        started = perf_counter()
        try:
            response = await self.wrapped.request(messages, model_settings, model_request_parameters)
        finally:
            _CURRENT_OPENAI_OBSERVATIONS.reset(context_token)
        if observations:
            metadata = dict(response.metadata or {})
            metadata["corsair_usage_presence"] = _presence_metadata(
                observations[-1]["payload"], perf_counter() - started, self.provider_name
            )
            response.metadata = metadata
        return response


def wrap_openai_usage(model: Model, provider_name: str = "openai") -> ProviderUsageModel:
    """Wrap a native OpenAI Chat model without changing its identity/provider."""
    return ProviderUsageModel(model, provider_name)


__all__ = ["ProviderUsageModel", "openai_usage_response_hook", "wrap_openai_usage"]
