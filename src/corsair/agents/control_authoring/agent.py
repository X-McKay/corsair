"""Native factory for the independent ordinary-behavior specialist."""
from pathlib import Path
from pydantic_ai import Agent
from ..agent_identity import factory_identity
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai_harness import Skills
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.models import Model
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.instrumented import InstrumentationSettings
from corsair.agents.budget import tool_budget
from corsair.agents.prompted_output import prompted_output
from .contracts import ControlInput
from .dependencies import SpecialistDependencies
from .prompts import INSTRUCTIONS, CONTROL_SKILL_ID, CONTROL_SKILL_TEXT
from .prompts import COMMON_SKILL_ID, COMMON_SKILL_TEXT
from .tools import TOOLSET_SHA256, specialist_tools
from .prompts import PROMPT_VERSION, SKILL_SHA256
from .validation import finalize_draft
from .prompts import _SPEC
CONFIG_VERSION = _SPEC.metadata['config_version']
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__, Path(__file__).with_name('agent.yaml'))
SPEC_SHA256 = MANIFEST_IDENTITY['spec_sha256']

def create_control_agent(model, *, output_retries=1, durability: TemporalDurability[SpecialistDependencies] | None = None):
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    agent = Agent.from_spec(_SPEC, model=model, deps_type=SpecialistDependencies,
        output_type=finalize_draft, retries={'tools': 0, 'output': output_retries},
        toolsets=[specialist_tools()],
        capabilities=[
            LocalWorkspace(Path(__file__).parent, read_only=True),
            Skills('skills', include={CONTROL_SKILL_ID}),
            Skills('../probe_authoring/skills', include={COMMON_SKILL_ID}),
            tool_budget(),
            prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
            *([durability] if durability is not None else []),
        ])
    @agent.instructions
    def own_input(ctx):
        if not isinstance(ctx.deps.inputs, ControlInput):
            raise ValueError('control factory requires the narrow ControlInput')
        return 'Author only the supplied benign control.'
    return agent
