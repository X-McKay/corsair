"""Named model profiles, selected independently per agent. No implicit provider fallback."""
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .vllm import LocalModelConfig

AgentName = Literal['identification', 'repository_identification', 'environment', 'planning', 'authoring', 'assessment']
AGENTS = frozenset(AgentName.__args__)
EnvName = Annotated[str, Field(pattern=r'^[A-Z_][A-Z0-9_]*$')]


class Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class VllmConfig(LocalModelConfig):
    provider: Literal['vllm'] = 'vllm'
    server: Literal['vllm'] = 'vllm'
    api_key_env: EnvName | None = None


class OpenAIConfig(Frozen):
    provider: Literal['openai_compatible']
    base_url: str
    model_name: str = Field(min_length=1, max_length=256)
    api_key_env: EnvName | None = None
    timeout_seconds: float = Field(default=60, gt=0, le=240)
    response_token_limit: int = Field(default=2048, ge=1, le=65536)
    temperature: float | None = Field(default=None, ge=0, le=2)

    @field_validator('base_url')
    @classmethod
    def endpoint(cls, value):
        p = urlsplit(value)
        if (p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment
                or not p.path.rstrip('/').endswith('/v1')):
            raise ValueError('explicit HTTPS /v1 endpoint without credentials/query required')
        return value.rstrip('/')


class BedrockConfig(Frozen):
    provider: Literal['bedrock']
    model_name: str = Field(min_length=1, max_length=256)
    region: str = Field(pattern=r'^[a-z]{2}(?:-[a-z]+)+-\d+$')
    aws_profile: str | None = Field(default=None, min_length=1)
    timeout_seconds: float = Field(default=60, gt=0, le=240)
    response_token_limit: int = Field(default=2048, ge=1, le=65536)
    temperature: float | None = Field(default=None, ge=0, le=2)


ModelConfig = Annotated[VllmConfig | OpenAIConfig | BedrockConfig, Field(discriminator='provider')]
MODEL_CONFIG = TypeAdapter(ModelConfig)


class InferenceConfig(Frozen):
    models: dict[str, ModelConfig] = Field(min_length=1)
    default: str | None = None
    agents: dict[AgentName, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def references(self):
        if any(not name or len(name) > 128 for name in self.models):
            raise ValueError('model profile names must be nonempty and at most 128 characters')
        for name in [*self.agents.values(), *([self.default] if self.default is not None else [])]:
            if name not in self.models:
                raise ValueError(f'unknown model profile: {name}')
        return self

    def resolve(self, agent: str) -> ModelConfig:
        if agent not in AGENTS:
            raise ValueError(f'unknown agent: {agent}')
        name = self.agents.get(agent, self.default)
        if name is None:
            raise ValueError(f'no model configured for agent {agent}; set agents.{agent} or default')
        return self.models[name]


def inference_config(value) -> InferenceConfig:
    if isinstance(value, InferenceConfig):
        return value
    if isinstance(value, LocalModelConfig):
        value = value.model_dump()
    if not isinstance(value, dict):
        raise ValueError('provider configuration must be an object')
    if 'server' in value and 'models' not in value:
        # Validate old vLLM files as before, including rejecting unknown servers/keys.
        old = LocalModelConfig.model_validate(value)
        return InferenceConfig(models={'default': VllmConfig(**old.model_dump())}, default='default')
    return InferenceConfig.model_validate(value)


def load_inference(path: Path) -> InferenceConfig:
    import json
    value = json.loads(path.read_text())
    if isinstance(value, dict) and 'inference' in value:
        from corsair.configuration import ProviderConfig
        return ProviderConfig.model_validate(value).inference
    return inference_config(value)


def load_agent_config(path: Path, agent: str) -> ModelConfig:
    return load_inference(path).resolve(agent)
