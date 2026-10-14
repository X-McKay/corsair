"""Isolated environment agent factory; same factory for any later durable mode."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..prompted_output import prompted_output
from ..spec import build_agent, load_agent_spec, factory_identity

from .contracts import EnvironmentResult
from .dependencies import EnvironmentDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_ID, SKILL_SHA256, SKILL_TEXT, environment_prompt
from .tools import TOOL_RETRIES, TOOLSET_SHA256, environment_tools
from .validation import finalize_environment

_SPEC = load_agent_spec('environment')
CONFIG_VERSION = _SPEC.metadata.config_version
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__)
SPEC_IDENTITY = MANIFEST_IDENTITY
SPEC_SHA256 = _SPEC.spec_sha256
CAPABILITY_SELECTION_SHA256 = _SPEC.selection_sha256

# Re-exported for existing callers of corsair.agents.environment.agent.
__all__ = ["CONFIG_VERSION", "MANIFEST_IDENTITY", "SPEC_IDENTITY", "SPEC_SHA256", "CAPABILITY_SELECTION_SHA256", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_environment_agent", "environment_prompt"]


def create_environment_agent(model: Model, *, output_retries: int = 1) -> Agent[EnvironmentDependencies, EnvironmentResult]:
    return build_agent(
        _SPEC, model=model, deps_type=EnvironmentDependencies, output_type=finalize_environment,
        output_retries=output_retries, tool_retries=TOOL_RETRIES,
        capability_registry={
            SKILL_ID: lambda: Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[environment_tools()]),
            'prompted-output': prompted_output,
            'instrumentation': lambda: Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        },
    )
