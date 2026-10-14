"""Issue identification factories: inline saved files (SPEC-0024) and a saved repository commit (SPEC-0038).

Same output contract and shared finalizer; separate factories and dependency types, no fallback
between source modes. Repository mode is direct only: the tree is not serializable into a durable
activity payload yet.
"""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..budget import tool_budget
from ..prompted_output import prompted_output
from ..spec import build_agent, load_agent_spec, factory_identity
from .contracts import IssueIdentification
from .dependencies import FixtureDependencies, RepositoryDependencies
from .prompts import (
    INSTRUCTIONS, PROMPT_VERSION, REPOSITORY_INSTRUCTIONS, REPOSITORY_PROMPT_VERSION, REPOSITORY_SKILL_ID,
    REPOSITORY_SKILL_SHA256, REPOSITORY_SKILL_TEXT, SKILL_ID, SKILL_SHA256, SKILL_TEXT, identification_prompt,
    repository_identification_prompt,
)
from .tools import REPOSITORY_TOOLSET_SHA256, TOOL_RETRIES, TOOLSET_SHA256, identification_tools, repository_tools
from .validation import finalize_identification, finalize_repository_identification

_SPEC = load_agent_spec('identification')
_REPOSITORY_SPEC = load_agent_spec('repository_identification')
CONFIG_VERSION = _SPEC.metadata.config_version
REPOSITORY_CONFIG_VERSION = _REPOSITORY_SPEC.metadata.config_version
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__)
SPEC_IDENTITY = MANIFEST_IDENTITY
SPEC_SHA256 = _SPEC.spec_sha256
CAPABILITY_SELECTION_SHA256 = _SPEC.selection_sha256
REPOSITORY_MANIFEST_IDENTITY = factory_identity(_REPOSITORY_SPEC, __file__)
REPOSITORY_SPEC_IDENTITY = REPOSITORY_MANIFEST_IDENTITY
REPOSITORY_SPEC_SHA256 = _REPOSITORY_SPEC.spec_sha256
REPOSITORY_CAPABILITY_SELECTION_SHA256 = _REPOSITORY_SPEC.selection_sha256


def create_issue_identification_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[FixtureDependencies] | None = None,
) -> Agent[FixtureDependencies, IssueIdentification]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    return build_agent(
        _SPEC, model=model, deps_type=FixtureDependencies, output_type=finalize_identification,
        output_retries=output_retries, tool_retries=TOOL_RETRIES,
        extra_capabilities=() if durability is None else (durability,),
        capability_registry={
            SKILL_ID: lambda: Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[identification_tools()]),
            'tool-budget': tool_budget, 'prompted-output': prompted_output,
            'instrumentation': lambda: Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        },
    )


def create_repository_identification_agent(
    model: Model, *, output_retries: int = 1,
) -> Agent[RepositoryDependencies, IssueIdentification]:
    """Explicit model seam; no configured provider fallback and no inline-source fallback."""
    return build_agent(
        _REPOSITORY_SPEC, model=model, deps_type=RepositoryDependencies,
        output_type=finalize_repository_identification, output_retries=output_retries, tool_retries=TOOL_RETRIES,
        capability_registry={
            REPOSITORY_SKILL_ID: lambda: Capability(id=REPOSITORY_SKILL_ID, instructions=REPOSITORY_SKILL_TEXT, toolsets=[repository_tools()]),
            'tool-budget': tool_budget, 'prompted-output': prompted_output,
            'instrumentation': lambda: Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        },
    )


__all__ = ["MANIFEST_IDENTITY", "SPEC_SHA256", "CAPABILITY_SELECTION_SHA256", "REPOSITORY_MANIFEST_IDENTITY", "REPOSITORY_SPEC_SHA256", "REPOSITORY_CAPABILITY_SELECTION_SHA256", "CONFIG_VERSION", "PROMPT_VERSION", "REPOSITORY_CONFIG_VERSION", "REPOSITORY_PROMPT_VERSION",
           "REPOSITORY_SKILL_SHA256", "REPOSITORY_TOOLSET_SHA256", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_issue_identification_agent", "create_repository_identification_agent", "identification_prompt",
           "repository_identification_prompt"]
