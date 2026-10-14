from __future__ import annotations

import asyncio

import httpx
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from corsair.v2.agents.models import bounded_model_settings, build_model
from corsair.v2.agents.usage import ProviderUsageModel, openai_usage_response_hook
from corsair.v2.contracts import Budget, ModelProfile


def _chat_response(usage: dict | None, *, include_usage: bool = True) -> dict:
    response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": "unit-model",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}
        ],
    }
    if include_usage:
        response["usage"] = usage
    return response


def _native_wrapped_model(payload: dict) -> tuple[ProviderUsageModel, AsyncOpenAI]:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(respond)
    http_client = httpx.AsyncClient(transport=transport, event_hooks={"response": [openai_usage_response_hook]})
    client = AsyncOpenAI(
        api_key="test-only",
        base_url="http://mock.invalid/v1",
        http_client=http_client,
        max_retries=0,
        timeout=2.0,
    )
    native = OpenAIChatModel("unit-model", provider=OpenAIProvider(openai_client=client))
    return ProviderUsageModel(native), client


async def _request(model: ProviderUsageModel):
    return await model.request(
        [ModelRequest(parts=[UserPromptPart(content="hello")])],
        None,
        ModelRequestParameters(),
    )


def test_explicit_provider_zero_is_distinct_from_absent_usage_fields() -> None:
    async def check() -> None:
        payload = _chat_response({
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0},
        })
        model, client = _native_wrapped_model(payload)
        try:
            response = await _request(model)
            usage = response.metadata["corsair_usage_presence"]
            assert usage["schema"] == "corsair.provider-usage-presence.v1"
            assert usage["source"] == "provider-response-boundary"
            assert usage["provider"] == "openai"
            assert usage["fields"] == {
                "input_tokens": True,
                "output_tokens": True,
                "cache_read_tokens": True,
                "cache_write_tokens": False,
                "reasoning_tokens": True,
            }
            assert usage["raw_usage"] == payload["usage"]
            assert usage["request_attempts"] == 1
            assert usage["request_latency_seconds"] >= 0
            # The native adapter still owns actual framework usage parsing.
            assert response.usage.input_tokens == 0
            assert response.usage.output_tokens == 0
        finally:
            await client.close()

    asyncio.run(check())


def test_missing_provider_usage_is_not_inferred_from_native_zero_defaults() -> None:
    async def check() -> None:
        payload = _chat_response(None, include_usage=False)
        model, client = _native_wrapped_model(payload)
        try:
            response = await _request(model)
            usage = response.metadata["corsair_usage_presence"]
            assert usage["fields"] == {
                "input_tokens": False,
                "output_tokens": False,
                "cache_read_tokens": False,
                "cache_write_tokens": False,
                "reasoning_tokens": False,
            }
            assert usage["raw_usage"] is None
            # PydanticAI's native normalized defaults remain zero, but the
            # provider-boundary envelope correctly says those fields were absent.
            assert response.usage.input_tokens == 0
            assert response.usage.output_tokens == 0
        finally:
            await client.close()

    asyncio.run(check())


def test_only_actual_integer_usage_counts_are_reported() -> None:
    async def check() -> None:
        payload = _chat_response({
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "total_tokens": 4,
            "prompt_tokens_details": {},
            "completion_tokens_details": {"reasoning_tokens": None},
        })
        model, client = _native_wrapped_model(payload)
        try:
            response = await _request(model)
            assert response.metadata["corsair_usage_presence"]["fields"] == {
                "input_tokens": True,
                "output_tokens": True,
                "cache_read_tokens": False,
                "cache_write_tokens": False,
                "reasoning_tokens": False,
            }
        finally:
            await client.close()

    asyncio.run(check())


def test_model_factory_keeps_budgets_timeout_retries_and_local_credential_isolation(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-cloud-secret")
    profile = ModelProfile(
        model="local-model",
        provider="openai-compatible",
        base_url="http://127.0.0.1:11434/v1",
        settings={"max_tokens": 100_000},
    )
    budget = Budget(output_tokens_limit=77, stage_timeout_seconds=19)
    model = build_model(profile, budget)
    try:
        assert isinstance(model, ProviderUsageModel)
        assert model.model_name == "local-model"
        assert model.system == "openai"
        assert model.provider_name == "openai-compatible"
        native_client = model.provider._client
        assert native_client.api_key == "ollama"
        assert native_client.max_retries == 0
        assert native_client.timeout.read == 19
        assert model.settings["max_tokens"] == 77
        assert bounded_model_settings(profile, budget)["max_tokens"] == 77
    finally:
        asyncio.run(model.provider._client.close())


def test_explicit_custom_credential_environment_is_still_supported(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_OPENAI_KEY", "explicit-user-key")
    profile = ModelProfile(
        model="custom-local",
        provider="openai-compatible",
        base_url="http://localhost:11434/v1",
        api_key_env="CUSTOM_OPENAI_KEY",
    )
    model = build_model(profile, Budget())
    try:
        assert model.provider._client.api_key == "explicit-user-key"
    finally:
        asyncio.run(model.provider._client.close())
