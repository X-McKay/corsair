"""Native factory for the independent ordinary-behavior specialist."""
from corsair.agents.spec import load_agent_spec, build_agent, factory_identity
from pydantic_ai.capabilities import Capability, Instrumentation
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
_SPEC = load_agent_spec('control_authoring')
CONFIG_VERSION = _SPEC.metadata.config_version
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__)
SPEC_SHA256 = _SPEC.spec_sha256
CAPABILITY_SELECTION_SHA256 = _SPEC.selection_sha256

def create_control_agent(model, *, output_retries=1, durability: TemporalDurability[SpecialistDependencies] | None = None):
    agent = build_agent(_SPEC, model=model, deps_type=SpecialistDependencies,
        output_type=finalize_draft, output_retries=output_retries,
        capability_registry={
            CONTROL_SKILL_ID: lambda: Capability(id=CONTROL_SKILL_ID, instructions=CONTROL_SKILL_TEXT, toolsets=[specialist_tools()]),
            COMMON_SKILL_ID: lambda: Capability(id=COMMON_SKILL_ID, instructions=COMMON_SKILL_TEXT),
            'tool-budget': tool_budget,
            'prompted-output': prompted_output,
            'instrumentation': lambda: Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        }, extra_capabilities=([durability] if durability is not None else ()))
    @agent.instructions
    def own_input(ctx):
        if not isinstance(ctx.deps.inputs, ControlInput):
            raise ValueError('control factory requires the narrow ControlInput')
        return 'Author only the supplied benign control.'
    return agent
