"""Operator-owned inference configuration, independent of any model SDK."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or not parts.path.rstrip("/").endswith("/v1")
        ):
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
    """Read and validate operator-supplied provider configuration when explicitly called."""
    return ProviderConfig.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
