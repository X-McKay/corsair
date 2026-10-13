"""Two-test authoring stage: confined writes, capped development runs, withheld security outcome."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..budget import tool_budget
from ..prompted_output import prompted_output
from ..source.tools import TOOL_RETRIES
from .contracts import AuthoringResult
from .dependencies import AuthoringDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_ID, SKILL_SHA256, SKILL_TEXT, authoring_prompt
from .tools import TOOLSET_SHA256, authoring_tools, source_tools
from .validation import finalize_authoring

CONFIG_VERSION = "test-authoring-config-v4"

# Re-exported for existing callers of corsair.agents.test_authoring.agent.
__all__ = ["CONFIG_VERSION", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "authoring_prompt", "create_test_authoring_agent"]


def create_test_authoring_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[AuthoringDependencies] | None = None,
) -> Agent[AuthoringDependencies, AuthoringResult]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")
    return Agent[AuthoringDependencies, AuthoringResult](
        model, name="test_authoring", deps_type=AuthoringDependencies, output_type=finalize_authoring,
        instructions=INSTRUCTIONS, retries={"tools": TOOL_RETRIES, "output": output_retries},
        capabilities=[Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[source_tools(), authoring_tools()]),
                      tool_budget(), prompted_output(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
                      *([durability] if durability is not None else [])],
    )
