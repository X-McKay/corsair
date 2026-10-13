"""Isolated environment agent factory; same factory for any later durable mode."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..prompted_output import prompted_output

from .contracts import EnvironmentResult
from .dependencies import EnvironmentDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_ID, SKILL_SHA256, SKILL_TEXT, environment_prompt
from .tools import TOOL_RETRIES, TOOLSET_SHA256, environment_tools
from .validation import finalize_environment

# Re-exported for existing callers of corsair.agents.environment.agent.
__all__ = ["INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_environment_agent", "environment_prompt"]


def create_environment_agent(model: Model, *, output_retries: int = 1) -> Agent[EnvironmentDependencies, EnvironmentResult]:
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")
    return Agent[EnvironmentDependencies, EnvironmentResult](
        model, name="environment", deps_type=EnvironmentDependencies, output_type=finalize_environment,
        instructions=INSTRUCTIONS, retries={"tools": TOOL_RETRIES, "output": output_retries},
        capabilities=[Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[environment_tools()]), prompted_output(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5))],
    )
