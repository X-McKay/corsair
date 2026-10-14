"""Issue identification factories: inline saved files (SPEC-0024) and a saved repository commit (SPEC-0038).

Same output contract and shared finalizer; separate factories and dependency types, no fallback
between source modes. Repository mode is direct only: the tree is not serializable into a durable
activity payload yet.
"""
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai_harness import Skills
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..budget import tool_budget
from ..prompted_output import prompted_output
from ..agent_identity import factory_identity
from .contracts import IssueIdentification
from .dependencies import FixtureDependencies, RepositoryDependencies
from .prompts import (
    INSTRUCTIONS, PROMPT_VERSION, REPOSITORY_INSTRUCTIONS, REPOSITORY_PROMPT_VERSION, REPOSITORY_SKILL_ID,
    REPOSITORY_SKILL_SHA256, REPOSITORY_SKILL_TEXT, SKILL_ID, SKILL_SHA256, SKILL_TEXT, identification_prompt,
    repository_identification_prompt,
)
from .tools import REPOSITORY_TOOLSET_SHA256, TOOL_RETRIES, TOOLSET_SHA256, identification_tools, repository_tools
from .validation import finalize_identification, finalize_repository_identification

from .prompts import _SPEC
from .prompts import _REPOSITORY_SPEC
CONFIG_VERSION = _SPEC.metadata['config_version']
REPOSITORY_CONFIG_VERSION = _REPOSITORY_SPEC.metadata['config_version']
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__, Path(__file__).with_name('agent.yaml'))
SPEC_IDENTITY = MANIFEST_IDENTITY
SPEC_SHA256 = MANIFEST_IDENTITY['spec_sha256']
REPOSITORY_MANIFEST_IDENTITY = factory_identity(_REPOSITORY_SPEC, __file__, Path(__file__).with_name('repository-agent.yaml'))
REPOSITORY_SPEC_IDENTITY = REPOSITORY_MANIFEST_IDENTITY
REPOSITORY_SPEC_SHA256 = REPOSITORY_MANIFEST_IDENTITY['spec_sha256']


def create_issue_identification_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[FixtureDependencies] | None = None,
) -> Agent[FixtureDependencies, IssueIdentification]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    return Agent.from_spec(
        _SPEC, model=model, deps_type=FixtureDependencies, output_type=finalize_identification,
        retries={'tools': TOOL_RETRIES, 'output': output_retries},
        toolsets=[identification_tools()],
        capabilities=[
            LocalWorkspace(Path(__file__).parent, read_only=True),
            Skills('skills', include={SKILL_ID}),
            tool_budget(), prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
                *([durability] if durability is not None else []),
        ],
    )


def create_repository_identification_agent(
    model: Model, *, output_retries: int = 1,
) -> Agent[RepositoryDependencies, IssueIdentification]:
    """Explicit model seam; no configured provider fallback and no inline-source fallback."""
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    return Agent.from_spec(
        _REPOSITORY_SPEC, model=model, deps_type=RepositoryDependencies,
        output_type=finalize_repository_identification, retries={'tools': TOOL_RETRIES, 'output': output_retries},
        toolsets=[repository_tools()],
        capabilities=[
            LocalWorkspace(Path(__file__).parent, read_only=True),
            Skills('skills', include={REPOSITORY_SKILL_ID}),
            tool_budget(), prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        ],
    )


__all__ = ["MANIFEST_IDENTITY", "SPEC_SHA256", "REPOSITORY_MANIFEST_IDENTITY", "REPOSITORY_SPEC_SHA256", "CONFIG_VERSION", "PROMPT_VERSION", "REPOSITORY_CONFIG_VERSION", "REPOSITORY_PROMPT_VERSION",
           "REPOSITORY_SKILL_SHA256", "REPOSITORY_TOOLSET_SHA256", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_issue_identification_agent", "create_repository_identification_agent", "identification_prompt",
           "repository_identification_prompt"]
