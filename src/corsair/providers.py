"""Operator-owned model selection: one named profile per agent (producer, auditor), no fallback.

A provider config (JSON) names model profiles and maps each agent to one of them::

    {"profiles": {"local": {"base_url": "https://host/v1", "model_name": "..."}},
     "agents": {"producer": "local", "auditor": "local"}}

Every agent must be mapped; an unknown profile, a missing agent or a missing credential is an explicit error.
Each profile becomes a native ``OpenAIChatModel`` over ``OpenAIProvider`` for an OpenAI-compatible endpoint.

Settings carried over from v1 (``corsair.inference.vllm``) because the local Qwen3 endpoint needed them:
temperature 0 and no parallel tool calls; client retries off (the workflow owns retries); a per-request response
cap that covers reasoning and answer tokens; an explicit thinking control sent as ``extra_body``; prompted
structured output with inlined schema definitions, since the served model does not honour JSON-schema output or
strict tool definitions. A full 16384-token response took about 126 s on that server, so the timeout default is
300 s.
"""
from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack, asynccontextmanager
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_ai.models import Model

AgentName = Literal["producer", "auditor"]
AGENTS: tuple[AgentName, ...] = AgentName.__args__


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelProfile(_Frozen):
    base_url: str
    model_name: str = Field(min_length=1, max_length=256)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")
    timeout_s: float = Field(default=300, gt=0, le=900)
    max_tokens: int = Field(default=8192, ge=1, le=65536, description="Per request, reasoning plus answer")
    temperature: float | None = Field(default=0, ge=0, le=2)
    thinking: Literal["server_default", "disabled"] = "server_default"
    thinking_token_budget: int | None = Field(default=None, ge=1, le=32768)

    @field_validator("base_url")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query
                or parts.fragment or not parts.path.rstrip("/").endswith("/v1")):
            raise ValueError("an explicit HTTPS .../v1 endpoint without credentials or query is required")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _thinking(self) -> ModelProfile:
        if self.thinking == "disabled" and self.thinking_token_budget is not None:
            raise ValueError("a thinking budget cannot be combined with disabled thinking")
        return self


class ProviderConfig(_Frozen):
    profiles: dict[str, ModelProfile] = Field(min_length=1)
    agents: dict[AgentName, str]

    @model_validator(mode="after")
    def _references(self) -> ProviderConfig:
        missing = [agent for agent in AGENTS if agent not in self.agents]
        if missing:
            raise ValueError(f"no model profile mapped for agents: {', '.join(missing)}")
        unknown = sorted({name for name in self.agents.values() if name not in self.profiles})
        if unknown:
            raise ValueError(f"unknown model profiles: {', '.join(unknown)}")
        return self

    def profile(self, agent: str) -> ModelProfile:
        if agent not in AGENTS:
            raise ValueError(f"unknown agent: {agent}")
        return self.profiles[self.agents[agent]]


def load_provider_config(path: Path) -> ProviderConfig:
    return ProviderConfig.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


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
        return "corsair-anonymous"  # the client requires a value; the endpoint is keyless
    key = os.environ.get(profile.api_key_env, "")
    if not key:
        raise ValueError(f"configured credential {profile.api_key_env} is unavailable")
    return key


def build_model(profile: ModelProfile, *, openai_client=None) -> Model:
    """A native OpenAIChatModel; the caller owns ``openai_client`` (built here with retries off when omitted)."""
    from openai import AsyncOpenAI
    from pydantic_ai import InlineDefsJsonSchemaTransformer
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.profiles.openai import OpenAIModelProfile
    from pydantic_ai.providers.vllm import VLLMProvider

    if openai_client is None:
        openai_client = AsyncOpenAI(base_url=profile.base_url, api_key=_api_key(profile), organization="",
                                    project="", max_retries=0, timeout=profile.timeout_s)
    model_profile = OpenAIModelProfile(json_schema_transformer=InlineDefsJsonSchemaTransformer,
                                       default_structured_output_mode="prompted", supports_json_schema_output=False,
                                       supports_json_object_output=False,
                                       openai_supports_strict_tool_definition=False,
                                       # The served chat template accepts exactly one system message, first.
                                       openai_chat_supports_multiple_system_messages=False)
    return OpenAIChatModel(profile.model_name, provider=VLLMProvider(openai_client=openai_client),
                           profile=model_profile, settings=model_settings(profile))


@asynccontextmanager
async def agent_models(config: ProviderConfig, agents: Iterable[str] = AGENTS) -> AsyncIterator[dict[str, Model]]:
    """One client per profile, shared by the agents mapped to it, closed on exit."""
    from openai import AsyncOpenAI

    agents = tuple(agents)
    profiles = {agent: config.profile(agent) for agent in agents}
    for profile in profiles.values():
        _api_key(profile)  # fail before any client exists
    async with AsyncExitStack() as stack:
        built: dict[ModelProfile, Model] = {}
        for profile in profiles.values():
            if profile not in built:
                client = await stack.enter_async_context(AsyncOpenAI(
                    base_url=profile.base_url, api_key=_api_key(profile), organization="", project="",
                    max_retries=0, timeout=profile.timeout_s))
                built[profile] = build_model(profile, openai_client=client)
        yield {agent: built[profile] for agent, profile in profiles.items()}
