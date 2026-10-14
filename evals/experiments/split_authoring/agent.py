"""One native factory, explicit role; no runner, production wiring or execution authority."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings
from corsair.agents.budget import tool_budget
from corsair.agents.prompted_output import prompted_output
from .contracts import Role
from .dependencies import DraftingDependencies
from .prompts import INSTRUCTIONS, SKILL_ID, SKILL_TEXT, role_skills
from .tools import drafting_tools
from .validation import finalize_draft

CONFIG_VERSION = "split-authoring-experiment-config-v2"


def create_drafting_agent(model, *, role: Role, output_retries=1, guidance="tailored"):
    if not isinstance(model, Model):
        raise TypeError("an explicit PydanticAI Model instance is required")
    if role not in ("control", "exploit", "pair"):
        raise ValueError("unknown drafting role")
    specialized = [Capability(id=name, instructions=text) for name, text in role_skills(role, guidance).items()]
    agent = Agent(model, name=f"split_authoring_{role}", deps_type=DraftingDependencies,
        output_type=finalize_draft, instructions=INSTRUCTIONS,
        retries={"tools": 0, "output": output_retries},
        capabilities=[Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[drafting_tools()]),
                      *specialized, tool_budget(), prompted_output(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5))])

    @agent.instructions
    def assigned_role(ctx):
        if ctx.deps.inputs.role != role:
            raise ValueError("factory role must equal the operator-owned input role")
        return f"Your assigned role is {role}."

    return agent
