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
from .contracts import IssueIdentification
from .dependencies import FixtureDependencies, RepositoryDependencies
from .prompts import (
    INSTRUCTIONS, PROMPT_VERSION, REPOSITORY_INSTRUCTIONS, REPOSITORY_PROMPT_VERSION, REPOSITORY_SKILL_ID,
    REPOSITORY_SKILL_SHA256, REPOSITORY_SKILL_TEXT, SKILL_ID, SKILL_SHA256, SKILL_TEXT, identification_prompt,
    repository_identification_prompt,
)
from .tools import REPOSITORY_TOOLSET_SHA256, TOOL_RETRIES, TOOLSET_SHA256, identification_tools, repository_tools
from .validation import finalize_identification, finalize_repository_identification

CONFIG_VERSION = "issue-identification-config-v4-grounding-3"
REPOSITORY_CONFIG_VERSION = "issue-identification-repository-config-v3-grounding-3"


def create_issue_identification_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[FixtureDependencies] | None = None,
) -> Agent[FixtureDependencies, IssueIdentification]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")
    return Agent[FixtureDependencies, IssueIdentification](
        model, name="issue_identification", deps_type=FixtureDependencies, output_type=finalize_identification,
        instructions=INSTRUCTIONS, retries={"tools": TOOL_RETRIES, "output": output_retries},
        capabilities=[Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[identification_tools()]),
                      tool_budget(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
                      *([durability] if durability is not None else [])],
    )


def create_repository_identification_agent(
    model: Model, *, output_retries: int = 1,
) -> Agent[RepositoryDependencies, IssueIdentification]:
    """Explicit model seam; no configured provider fallback and no inline-source fallback."""
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")
    return Agent[RepositoryDependencies, IssueIdentification](
        model, name="issue_identification_repository", deps_type=RepositoryDependencies,
        output_type=finalize_repository_identification, instructions=REPOSITORY_INSTRUCTIONS,
        retries={"tools": TOOL_RETRIES, "output": output_retries},
        capabilities=[Capability(id=REPOSITORY_SKILL_ID, instructions=REPOSITORY_SKILL_TEXT, toolsets=[repository_tools()]),
                      tool_budget(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5))],
    )


__all__ = ["CONFIG_VERSION", "PROMPT_VERSION", "REPOSITORY_CONFIG_VERSION", "REPOSITORY_PROMPT_VERSION",
           "REPOSITORY_SKILL_SHA256", "REPOSITORY_TOOLSET_SHA256", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_issue_identification_agent", "create_repository_identification_agent", "identification_prompt",
           "repository_identification_prompt"]
