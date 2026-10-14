"""Stage 6 entry for the Reviewer, matching ``stages.Review``. It has no input that could carry an outcome."""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.models import Model

from ...contracts import AgentUsage, Case, FrozenPatch, ProbePlan, Validity
from ..common.usage import run_recorded
from ..probing.agent import limits
from ..probing.source import source_workspace
from .agent import NAME, SPEC, create_agent
from .review import ReviewDeps, not_reviewed, render_prompt


def review_deps(patch: FrozenPatch, source_root: Path) -> ReviewDeps:
    return ReviewDeps(source_root=source_root, drafts={"control": patch.control, "exploit": patch.exploit})


async def review(case: Case, plan: ProbePlan, patch: FrozenPatch, model: Model, *, source_root: Path,
                 revision: str = "vulnerable") -> tuple[Validity, AgentUsage]:
    """Judge both probes on ``revision``'s source; a review that does not complete is negative for both."""
    agent = create_agent(model)
    output, usage = await run_recorded(agent, NAME, render_prompt(case, plan, patch), model=model,
                                       deps=review_deps(patch, source_root), usage_limits=limits(SPEC),
                                       workspace=source_workspace(source_root))
    control, exploit = output if output is not None else (not_reviewed("control", usage.status),
                                                          not_reviewed("exploit", usage.status))
    return Validity(patch_sha256=patch.sha256, revision=revision, control=control, exploit=exploit), usage
