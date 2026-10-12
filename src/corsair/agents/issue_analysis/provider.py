"""Explicit native vLLM (OpenAI Chat Completions) composition for an operator endpoint."""

from contextlib import asynccontextmanager
import os
from typing import Literal
from urllib.parse import urlsplit

from httpx2 import AsyncClient
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
MODEL_SETTINGS = ModelSettings(temperature=0, max_tokens=2048, parallel_tool_calls=False)


class LocalModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server: Literal["vllm"]
    base_url: str
    model_name: str = Field(min_length=1, max_length=256)
    api_key_env: Literal["CORSAIR_LOCAL_MODEL_API_KEY"] | None = None
    timeout_seconds: float = Field(default=60, gt=0, le=120)

    @field_validator("base_url")
    @classmethod
    def explicit_verified_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path.rstrip("/") != "/v1"):
            raise ValueError("explicit HTTPS /v1 endpoint without credentials/query is required")
        return value.rstrip("/")


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
                              profile=PROFILE_OVERRIDES, settings=MODEL_SETTINGS)
