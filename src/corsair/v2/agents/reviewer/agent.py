"""Native factory for the outcome-blind Reviewer: ``agent.yaml`` plus read-only tools and its skills."""
from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.agent.spec import AgentSpec
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai_harness import Skills

from ..common.budget import tool_budget
from ..common.prompted_output import prompted_output
from ..probing.agent import PROTOCOL_SKILLS, framework_skills, skills_home
from ..probing.source import source_tools
from .review import ReviewDeps, finalize_review

NAME = "reviewer"
SPEC = AgentSpec.from_file(Path(__file__).with_name("agent.yaml"))
SKILLS = "agents/reviewer/skills"


def create_agent(model: Model, *, durability: TemporalDurability[ReviewDeps] | None = None) -> Agent:
    """One definition for direct and durable modes. Every present framework skill is offered; none is required."""
    if not isinstance(model, Model):
        raise TypeError("an explicit native Model instance is required")
    return Agent.from_spec(SPEC, model=model, deps_type=ReviewDeps, output_type=PromptedOutput(finalize_review),
                           capabilities=[
                               source_tools(),
                               Skills([SKILLS, PROTOCOL_SKILLS], workspace=skills_home()),
                               *framework_skills(None),
                               tool_budget(),
                               prompted_output(),
                               Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
                               *([durability] if durability is not None else []),
                           ])
