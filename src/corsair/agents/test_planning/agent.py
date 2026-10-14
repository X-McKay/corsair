"""Read-only test planning stage over saved source and supplied environment evidence."""
from pathlib import Path

from pydantic_ai import Agent
from ..agent_identity import factory_identity
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..budget import tool_budget
from ..prompted_output import prompted_output
from .contracts import TestPlan
from .dependencies import PlanningDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_ID, SKILL_SHA256, SKILL_TEXT, planning_prompt
from .tools import TOOL_RETRIES, TOOLSET_ID, TOOLSET_SHA256, offered_tools, withdraw_when_read
from .validation import _symbol_occurs, finalize_plan

# CONFIG_VERSION covers budgets, instrumentation and provider composition; PROMPT_VERSION
# (prompts.py) covers everything the model sees.
from .prompts import _SPEC
CONFIG_VERSION = _SPEC.metadata['config_version']
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__, Path(__file__).with_name('agent.yaml'))
SPEC_SHA256 = MANIFEST_IDENTITY['spec_sha256']

# Re-exported for existing callers of corsair.agents.test_planning.agent.
__all__ = ["MANIFEST_IDENTITY", "SPEC_SHA256", "CONFIG_VERSION", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_ID",
           "TOOLSET_SHA256", "PlanningDependencies", "_symbol_occurs", "create_test_planning_agent", "finalize_plan",
           "planning_prompt", "withdraw_when_read"]


def create_test_planning_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[PlanningDependencies] | None = None,
) -> Agent[PlanningDependencies, TestPlan]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    return Agent.from_spec(_SPEC, model=model, deps_type=PlanningDependencies,
        output_type=finalize_plan,
        validation_context=lambda ctx: ctx.deps.inputs,
        retries={'tools': TOOL_RETRIES, 'output': output_retries},
        capabilities=[
            Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[offered_tools()]),
            tool_budget(),
            prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
            *([durability] if durability is not None else []),
        ])
