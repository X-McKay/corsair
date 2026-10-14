"""Stage 5 entry for the Control Prober, matching ``stages.Probe``."""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.models import Model

from ...contracts import AgentUsage, ProbeBrief, ProbeDraft, Runtime
from ..probing.agent import run_prober
from .agent import NAME, ROLE, SPEC, create_agent


async def probe(brief: ProbeBrief, runtime: Runtime, model: Model, *, source_root: Path,
                diagnostics: str | None = None, previous: ProbeDraft | None = None,
                review_feedback: str | None = None) -> tuple[ProbeDraft | None, AgentUsage]:
    """Write this role's draft from its own brief only; None when blocked or the run failed (see usage.status)."""
    if brief.role != ROLE:
        raise ValueError(f"the {NAME} takes only a {ROLE} brief")
    agent = create_agent(model, framework=runtime.skill)
    return await run_prober(agent, NAME, SPEC, brief, runtime, model, source_root=source_root,
                            diagnostics=diagnostics, previous=previous, review_feedback=review_feedback)
