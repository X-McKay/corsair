"""OpenAI-compatible native PydanticAI model construction."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterable
from contextlib import AsyncExitStack, asynccontextmanager

from pydantic_ai.models import Model

from corsair.runtime.inference import AGENTS, ModelProfile, ProviderConfig


def model_settings(profile: ModelProfile) -> dict:
    settings: dict = {"max_tokens": profile.max_tokens, "parallel_tool_calls": False}
    if profile.temperature is not None:
        settings["temperature"] = profile.temperature
    if profile.thinking == "disabled":
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    elif profile.thinking_token_budget is not None:
        settings["extra_body"] = {"thinking_token_budget": profile.thinking_token_budget}
    return settings


def _api_key(profile: ModelProfile) -> str:
    if profile.api_key_env is None:
        return "corsair-anonymous"  # The SDK requires a value even for a keyless endpoint.
    key = os.environ.get(profile.api_key_env, "")
    if not key:
        raise ValueError(f"configured credential {profile.api_key_env} is unavailable")
    return key


def _build_model(profile: ModelProfile, *, openai_client) -> Model:
    """Build a native SDK model using only the client owned by the inference context."""
    from pydantic_ai import InlineDefsJsonSchemaTransformer
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.profiles.openai import OpenAIModelProfile
    from pydantic_ai.providers.vllm import VLLMProvider

    model_profile = OpenAIModelProfile(
        json_schema_transformer=InlineDefsJsonSchemaTransformer,
        default_structured_output_mode="prompted",
        supports_json_schema_output=False,
        supports_json_object_output=False,
        openai_supports_strict_tool_definition=False,
        openai_chat_supports_multiple_system_messages=False,
    )
    return OpenAIChatModel(
        profile.model_name,
        provider=VLLMProvider(openai_client=openai_client),
        profile=model_profile,
        settings=model_settings(profile),
    )


class OpenAIInference:
    """OpenAI-compatible inference adapter with one managed client per selected profile."""

    @asynccontextmanager
    async def models(
        self, config: ProviderConfig, agents: Iterable[str] = AGENTS
    ) -> AsyncIterator[dict[str, Model]]:
        from openai import AsyncOpenAI

        profiles = {agent: config.profile(agent) for agent in tuple(agents)}
        for profile in profiles.values():
            _api_key(profile)  # Fail before any client exists.
        async with AsyncExitStack() as stack:
            built: dict[ModelProfile, Model] = {}
            for profile in profiles.values():
                if profile not in built:
                    client = await stack.enter_async_context(
                        AsyncOpenAI(
                            base_url=profile.base_url,
                            api_key=_api_key(profile),
                            organization="",
                            project="",
                            max_retries=0,
                            timeout=profile.timeout_s,
                        )
                    )
                    built[profile] = _build_model(profile, openai_client=client)
            yield {agent: built[profile] for agent, profile in profiles.items()}
