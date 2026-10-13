"""Explicit native vLLM (OpenAI Chat Completions) composition for an operator endpoint."""

from contextlib import asynccontextmanager
import os
from typing import Literal
from urllib.parse import urlsplit

from httpx2 import AsyncClient
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_ai import InlineDefsJsonSchemaTransformer
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.vllm import VLLMProvider
from pydantic_ai.settings import ModelSettings

# Explicit server selection: each admitted server maps to its native provider.
PROVIDERS = {"vllm": VLLMProvider}

# Overrides the recorded live evidence requires on top of the native provider
# profile. VLLMProvider already supplies a single leading system message for every
# model; the inline-definitions schema transformer it supplies only for some model
# families (for example Qwen), so it stays pinned here rather than depending on the
# served model name.
PROFILE_OVERRIDES = OpenAIModelProfile(
    json_schema_transformer=InlineDefsJsonSchemaTransformer,
    default_structured_output_mode="prompted",
    supports_json_schema_output=False,
    supports_json_object_output=False,
    openai_supports_strict_tool_definition=False,
)

# Model-level settings, so direct, evaluation and durable runs send the same request.
# The response cap (default 2048) comes from the explicit configuration below.
MODEL_SETTINGS = ModelSettings(temperature=0, parallel_tool_calls=False)


class LocalModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server: Literal["vllm"]
    base_url: str
    model_name: str = Field(min_length=1, max_length=256)
    api_key_env: Literal["CORSAIR_LOCAL_MODEL_API_KEY"] | None = None
    # A full 16384-token response took ~126 s on the local server (PLAN-0030), so 120 s cannot hold it;
    # a full 32768-token response took 234.8 s (PLAN-0048), so that cap needs about 300 s.
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    # Per-request cap covering reasoning and answer tokens; each caller selects its own.
    # Thinking budgets stay a separate control below.
    response_token_limit: Literal[2048, 4096, 8192, 16384, 24576, 32768] = 2048
    thinking_mode: Literal["server_default", "disabled"] = "server_default"
    thinking_token_budget: int | None = Field(default=None, ge=1, le=2048, strict=True)

    @model_validator(mode="after")
    def distinct_thinking_controls(self) -> "LocalModelConfig":
        if self.thinking_mode == "disabled" and self.thinking_token_budget is not None:
            raise ValueError("a thinking budget cannot be combined with disabled thinking")
        return self

    @field_validator("base_url")
    @classmethod
    def explicit_verified_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path.rstrip("/") != "/v1"):
            raise ValueError("explicit HTTPS /v1 endpoint without credentials/query is required")
        return value.rstrip("/")


def model_settings(config: LocalModelConfig) -> ModelSettings:
    """One model-level mapping: fixed request controls, response cap and explicit thinking control."""
    settings = ModelSettings(**MODEL_SETTINGS, max_tokens=config.response_token_limit)
    if config.thinking_mode == "disabled":
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    if config.thinking_token_budget is not None:
        settings["extra_body"] = {"thinking_token_budget": config.thinking_token_budget}
    return settings


@asynccontextmanager
async def local_model(config: LocalModelConfig, *, http_client: AsyncClient | None = None):
    """No environment model/endpoint/key fallback; native SDK owns request translation."""
    key = "corsair-local-anonymous"
    if config.api_key_env is not None:
        key = os.environ.get(config.api_key_env, "")
        if not key:
            raise ValueError("configured local model credential is unavailable")
    async with AsyncOpenAI(base_url=config.base_url, api_key=key,
                           organization="", project="", max_retries=0,
                           timeout=config.timeout_seconds, http_client=http_client) as client:
        yield OpenAIChatModel(config.model_name, provider=PROVIDERS[config.server](openai_client=client),
                              profile=PROFILE_OVERRIDES, settings=model_settings(config))
