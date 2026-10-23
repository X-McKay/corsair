"""The outcome-blind auditor SDK-agent factory."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models import Model

from corsair.agents.resources import instruction, validate_agent_spec
from corsair.domain.verification import AuditResult, Submission


def instructions() -> str:
    """Lazily load the outcome-blind audit instruction."""
    return instruction(__package__)


def build_auditor(model: Model) -> Agent[None, AuditResult]:
    """Build the spec-validated tool-free blind auditor."""
    validate_agent_spec(__package__, tool_names=())
    return Agent(model, output_type=AuditResult, instructions=instructions(), retries=0, name="auditor")


def render(submission: Submission) -> str:
    return (
        f"Hypothesis:\n{submission.hypothesis.model_dump_json(indent=2)}\n\n"
        f"Differential probe:\n```python\n{submission.probe}\n```"
    )


async def audit(agent: Agent[None, AuditResult], submission: Submission) -> AuditResult:
    from pydantic_ai import UsageLimits

    result = await agent.run(render(submission), usage_limits=UsageLimits(request_limit=1))
    return result.output
