"""Proposal-only crystallization of repeated deterministic gate friction."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models import Model

from corsair.agents.resources import instruction, skill_inventory, validate_agent_spec
from corsair.agents.skill_crystallizer.types import SkillPatchProposal
from corsair.domain.verification import GateVerdict


def instructions() -> str:
    """Lazily load the proposal-only crystallizer instruction."""
    return instruction(__package__)


def build_skill_crystallizer(model: Model) -> Agent[None, SkillPatchProposal]:
    """Build a spec-validated tool-free proposal agent."""
    validate_agent_spec(__package__, tool_names=())
    return Agent(
        model,
        output_type=SkillPatchProposal,
        retries=0,
        name="skill-crystallizer",
        instructions=instructions(),
    )


async def optimize_skills_from_trace(
    model: Model, verdict: str, rejections: list[GateVerdict], skills_dir: Path
) -> SkillPatchProposal | None:
    """Crystallize repeated friction from a successful trace into a reviewed Markdown proposal."""
    if verdict not in ("LIKELY_EXPLOITABLE", "VULNERABILITY_PROVEN") or len(rejections) < 2:
        return None
    # Keep public proposal identifiers stable: foo.md identifies foo/SKILL.md; no apply path is provided.
    skills = tuple(f"{name}.md" for name in skill_inventory(skills_dir))
    if not skills:
        raise ValueError("no operator-owned skills are available")
    trace = "\n".join(f"{rejection.stage}: {rejection.reason[:500]}" for rejection in rejections[:32])
    result = await build_skill_crystallizer(model).run(
        f"Allowed skills: {', '.join(skills)}\nRejections:\n{trace}",
        usage_limits=UsageLimits(request_limit=1),
    )
    proposal = result.output
    if proposal.skill_file not in skills or len(proposal.markdown_append_block.strip().splitlines()) > 3:
        raise ValueError("skill proposal must name an existing skill and contain at most three lines")
    return proposal
