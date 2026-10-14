"""Evidence assessment proposes; the deterministic disposition gates decide."""
from pathlib import Path

from pydantic_ai import Agent
from ..agent_identity import factory_identity
from pydantic_ai.capabilities import Capability, Instrumentation
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings

from .contracts import EvidenceAssessment
from .dependencies import AssessmentDependencies
from .prompts import INSTRUCTIONS, PROMPT_VERSION, SKILL_BYTES, SKILL_ID, SKILL_SHA256, SKILL_TEXT, assessment_prompt
from .tools import TOOL_RETRIES, TOOLSET_SHA256, evidence_tools
from .validation import finalize_assessment

from ..budget import tool_budget
from ..prompted_output import prompted_output

from .prompts import _SPEC
CONFIG_VERSION = _SPEC.metadata['config_version']
MANIFEST_IDENTITY = factory_identity(_SPEC, __file__, Path(__file__).with_name('agent.yaml'))
SPEC_SHA256 = MANIFEST_IDENTITY['spec_sha256']

# Re-exported for existing callers of corsair.agents.evidence_assessment.agent.
__all__ = ["MANIFEST_IDENTITY", "SPEC_SHA256", "CONFIG_VERSION", "INSTRUCTIONS", "PROMPT_VERSION", "SKILL_BYTES", "SKILL_ID", "SKILL_SHA256", "SKILL_TEXT",
           "TOOLSET_SHA256", "assessment_prompt", "create_evidence_assessment_agent"]


def create_evidence_assessment_agent(
    model: Model, *, output_retries: int = 1,
    durability: TemporalDurability[AssessmentDependencies] | None = None,
) -> Agent[AssessmentDependencies, EvidenceAssessment]:
    """Explicit model seam reusable by native durability; no configured provider fallback."""
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    return Agent.from_spec(_SPEC, model=model, deps_type=AssessmentDependencies,
        output_type=finalize_assessment,

        retries={'tools': TOOL_RETRIES, 'output': output_retries},
        capabilities=[
            Capability(id=SKILL_ID, instructions=SKILL_TEXT, toolsets=[evidence_tools()]),
            tool_budget(),
            prompted_output(),
            Instrumentation(settings=InstrumentationSettings(include_content=False, version=5)),
            *([durability] if durability is not None else []),
        ])
