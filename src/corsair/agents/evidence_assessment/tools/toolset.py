"""Explicit registration of the assessment agent's model-facing tools, in offered order."""

from pydantic_ai.toolsets import FunctionToolset

from ...toolset_identity import toolset_sha256
from ..dependencies import AssessmentDependencies
from .read_evidence import READ_EVIDENCE_TOOL, read_evidence

TOOLSET_ID = "evidence_assessment_evidence"
# Native per-tool budget: an invented or failing read is refused at once.
TOOL_RETRIES = 0


def evidence_tools() -> FunctionToolset[AssessmentDependencies]:
    tools = FunctionToolset[AssessmentDependencies](id=TOOLSET_ID)
    tools.add_function(read_evidence, name=READ_EVIDENCE_TOOL, retries=TOOL_RETRIES)
    return tools


TOOLSET_SHA256 = toolset_sha256(evidence_tools())
