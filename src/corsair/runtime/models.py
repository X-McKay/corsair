"""Shared ADK model and package-resource helpers.

Role-specific factories, prompts, and tools intentionally remain beside their
agents.  This module only owns the small set of runtime-wide model and metadata
helpers that activities need when they construct a bounded ADK invocation.
"""

from __future__ import annotations

from importlib import resources
from typing import Literal

from google.adk.models import BaseLlm
from pydantic import Field, field_validator

from corsair.contracts import Contract
from corsair.settings import ModelSettings, Settings

RoleName = Literal["producer", "auditor"]
AgentModel = str | BaseLlm

_RESOURCE_PACKAGES: dict[RoleName, str] = {
    "producer": "corsair.agents.producer",
    "auditor": "corsair.agents.auditor",
}


class AgentSpec(Contract):
    """Declarative role metadata, deliberately separate from wire schemas."""

    name: RoleName
    contract_version: Literal["corsair.agent/1"]
    execution_class: Literal["durable"]
    governance_tier: str = Field(min_length=1, max_length=120)
    risk_path: str = Field(min_length=1, max_length=240)
    tools: list[str]
    instruction_resource: str = Field(min_length=1, max_length=240)
    schema_ref: str = Field(min_length=1, max_length=240)

    @field_validator("tools")
    @classmethod
    def unique_tool_names(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item for item in value):
            raise ValueError("tools must contain unique non-empty names")
        return value


def _resource_package(role: RoleName) -> str:
    try:
        return _RESOURCE_PACKAGES[role]
    except KeyError as error:  # Defensive if a caller bypasses Literal validation.
        raise ValueError(f"unknown Corsair role: {role!r}") from error


def load_agent_spec(role: RoleName) -> AgentSpec:
    """Read and validate a role's declarative metadata from package resources."""

    content = (
        resources.files(_resource_package(role)).joinpath("agent.json").read_text(encoding="utf-8")
    )
    spec = AgentSpec.model_validate_json(content)
    if spec.name != role:
        raise ValueError(f"agent metadata name does not match requested role {role!r}")
    return spec


def prompt_text(role: RoleName) -> str:
    """Return the immutable system prompt used for manifest prompt digests."""

    return (
        resources.files(f"{_resource_package(role)}.instructions")
        .joinpath("system.md")
        .read_text(encoding="utf-8")
    )


def model_for_role(settings: Settings | ModelSettings, role: RoleName) -> AgentModel:
    """Resolve a role model without reading or accepting provider credentials.

    Gemini model IDs are left for ADK to resolve natively.  LiteLLM receives
    only the allowlisted endpoint and generation controls from ModelSettings;
    provider API keys remain in the worker process environment.
    """

    model_settings = settings.models if isinstance(settings, Settings) else settings
    model_name = getattr(model_settings, role)
    if model_settings.connector == "gemini":
        if model_settings.api_base is not None:
            raise ValueError("api_base is supported only when connector is 'litellm'")
        return model_name

    # LiteLlm is intentionally imported only when configured.  The optional
    # provider dependency is therefore not required for a normal Gemini worker.
    from google.adk.models import LiteLlm

    return LiteLlm(
        model=model_name,
        api_base=model_settings.api_base,
        timeout=model_settings.request_timeout_seconds,
        num_retries=0,
        extra_body=dict(model_settings.extra_body),
    )
