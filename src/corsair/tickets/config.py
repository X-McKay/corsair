"""Read-only source selection and bounded capture settings."""
from typing import Annotated, Literal
from pydantic import Field, field_validator
from corsair.inference.config import EnvName, Frozen


class TicketLimits(Frozen):
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_pages: int = Field(default=10, ge=1, le=100)
    max_bytes: int = Field(default=1048576, ge=1024, le=8388608)


class GitHubConfig(TicketLimits):
    provider: Literal['github']
    repository: str = Field(pattern=r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
    token_env: EnvName | None = None


    @field_validator('repository')
    @classmethod
    def no_dot_segments(cls, value):
        if any(part in ('.', '..') for part in value.split('/')):
            raise ValueError('repository owner/name cannot be dot segments')
        return value


class AzureConfig(TicketLimits):
    provider: Literal['azure_devops']
    organization: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]*$')
    project: str = Field(min_length=1, max_length=128)
    token_env: EnvName
    auth: Literal['pat', 'bearer'] = 'pat'


TicketConfig = Annotated[GitHubConfig | AzureConfig, Field(discriminator='provider')]
