"""Isolated environment agent factory; same factory for any later durable mode."""
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai_harness import Skills
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from ..prompted_output import prompted_output
from ..agent_identity import factory_identity

from .contracts import EnvironmentResult
from .dependencies import EnvironmentDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_ID, SKILL_SHA256, SKILL_TEXT, environment_prompt
from .tools import TOOL_RETRIES, TOOLSET_SHA256, environment_tools
from .validation import finalize_environment

from .prompts import _SPEC
CONFIG_VERSION = _SPEC.metadata['config_version']
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__, Path(__file__).with_name('agent.yaml'))
SPEC_IDENTITY = MANIFEST_IDENTITY
SPEC_SHA256 = MANIFEST_IDENTITY['spec_sha256']

# Re-exported for existing callers of corsair.agents.environment.agent.
__all__ = ["CONFIG_VERSION", "MANIFEST_IDENTITY", "SPEC_IDENTITY", "SPEC_SHA256", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT", "TOOLSET_SHA256",
           "create_environment_agent", "environment_prompt"]


def create_environment_agent(model: Model, *, output_retries: int = 1) -> Agent[EnvironmentDependencies, EnvironmentResult]:
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    return Agent.from_spec(
        _SPEC, model=model, deps_type=EnvironmentDependencies, output_type=finalize_environment,
        retries={'tools': TOOL_RETRIES, 'output': output_retries},
        toolsets=[environment_tools()],
        capabilities=[
            LocalWorkspace(Path(__file__).parent, read_only=True),
            Skills('skills', include={SKILL_ID}),
            prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
        ],
    )
