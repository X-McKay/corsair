"""Explicit native PydanticAI model construction for admitted operator profiles."""
from __future__ import annotations

import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ..contracts import Budget, ModelProfile
from .usage import openai_usage_response_hook, wrap_openai_usage


def _loopback_endpoint(base_url: str | None) -> bool:
    if base_url is None:
        return False
    host = urlsplit(base_url).hostname
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def bounded_model_settings(profile: ModelProfile, budget: Budget) -> dict[str, Any]:
    """Apply an operator ceiling before the SDK reaches a provider."""
    settings = dict(profile.settings)
    requested = settings.get("max_tokens", 4096)
    if not isinstance(requested, int) or requested < 1:
        raise ValueError("Model profile max_tokens must be a positive integer")
    settings["max_tokens"] = min(requested, budget.output_tokens_limit)
    return settings


def build_model(profile: ModelProfile, budget: Budget) -> Model:
    """Build only supported SDK model routes; never fall back to another provider."""
    if not isinstance(profile, ModelProfile) or not isinstance(budget, Budget):
        raise ValueError("An admitted ModelProfile and Budget are required")  # noqa: TRY004 - invalid admission is consistently ValueError
    if profile.provider in ("openai", "openai-compatible", "ollama"):
        local_default = (profile.provider in ("openai-compatible", "ollama") and _loopback_endpoint(profile.base_url)
                         and profile.api_key_env == "OPENAI_API_KEY")
        key = "ollama" if local_default else os.environ.get(profile.api_key_env)
        if not key:
            if profile.provider in ("openai-compatible", "ollama") and _loopback_endpoint(profile.base_url):
                # Ollama's local OpenAI endpoint requires a syntactic key but it
                # is not a cloud credential. Never source another provider key.
                key = "ollama"
            else:
                raise ValueError(f"Missing required model credential in {profile.api_key_env}")
        timeout = httpx.Timeout(float(budget.stage_timeout_seconds))
        http_client = httpx.AsyncClient(
            timeout=timeout,
            event_hooks={"response": [openai_usage_response_hook]},
        )
        native_client = AsyncOpenAI(
            base_url=profile.base_url,
            api_key=key,
            http_client=http_client,
            timeout=timeout,
            max_retries=0,
        )
        provider_class = OllamaProvider if profile.provider == "ollama" else OpenAIProvider
        provider = provider_class(openai_client=native_client)
        model = OpenAIChatModel(profile.model, provider=provider, settings=bounded_model_settings(profile, budget))
        return wrap_openai_usage(model, provider_name=profile.provider)
    if profile.provider == "bedrock":
        # BedrockProvider uses the configured native AWS SDK environment/profile.
        # No hand-written HTTP client or credential transport is introduced.
        region = profile.settings.get("region_name")
        profile_name = profile.settings.get("profile_name")
        if region is not None and not isinstance(region, str):
            raise ValueError("Bedrock region_name must be a string")
        if profile_name is not None and not isinstance(profile_name, str):
            raise ValueError("Bedrock profile_name must be a string")
        provider = BedrockProvider(region_name=region, profile_name=profile_name)
        settings = bounded_model_settings(profile, budget)
        settings.pop("region_name", None)
        settings.pop("profile_name", None)
        return BedrockConverseModel(profile.model, provider=provider, settings=settings)
    raise ValueError(f"Unsupported admitted provider {profile.provider!r}")


__all__ = ["bounded_model_settings", "build_model"]
