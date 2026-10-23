"""The producer's reviewed-playbook reader."""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from corsair.agents.producer.dependencies import ProducerDeps
from corsair.agents.resources import read_skill_file, skill_body


def register_read_skill(agent: Agent[ProducerDeps, str]) -> None:
    """Register the SDK tool that reads only spec-allowlisted, non-symlinked guides."""

    @agent.tool
    def read_skill(ctx: RunContext[ProducerDeps], name: str) -> str:
        """Read operator-owned guidance by name; an unknown name returns the available guides."""
        text = read_skill_file(ctx.deps.skills_dir, name, ctx.deps.allowed_skills)
        if text is None:
            return f"No skill {name!r}. Available: {', '.join(ctx.deps.allowed_skills)}"
        return skill_body(text)
