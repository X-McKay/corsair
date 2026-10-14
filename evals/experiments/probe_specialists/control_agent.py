"""Native factory for the independent ordinary-behavior specialist."""
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings
from corsair.agents.budget import tool_budget
from corsair.agents.prompted_output import prompted_output
from .contracts import ControlInput
from .dependencies import SpecialistDependencies
from .prompts import CONTROL_INSTRUCTIONS, CONTROL_SKILL_ID, CONTROL_SKILL_TEXT
from .prompts import COMMON_INSTRUCTIONS, COMMON_SKILL_ID, COMMON_SKILL_TEXT
from .tools import specialist_tools
from .validation import finalize_draft
CONFIG_VERSION = 'control-probe-author-config-v1'

def create_control_agent(model, *, output_retries=1):
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    agent = Agent(model, name='control_probe_author', deps_type=SpecialistDependencies,
        output_type=finalize_draft, instructions=COMMON_INSTRUCTIONS + "\n" + CONTROL_INSTRUCTIONS,
        retries={'tools': 0, 'output': output_retries},
        capabilities=[Capability(id=CONTROL_SKILL_ID, instructions=CONTROL_SKILL_TEXT, toolsets=[specialist_tools()]),
                      Capability(id=COMMON_SKILL_ID, instructions=COMMON_SKILL_TEXT),
                      tool_budget(), prompted_output(),
                      Instrumentation(settings=InstrumentationSettings(include_content=False, version=5))])
    @agent.instructions
    def own_input(ctx):
        if not isinstance(ctx.deps.inputs, ControlInput):
            raise ValueError('control factory requires the narrow ControlInput')
        return 'Author only the supplied benign control.'
    return agent
