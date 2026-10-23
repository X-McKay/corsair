"""The producer SDK-agent factory and only its registered capability surface."""

from __future__ import annotations

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from corsair.agents.producer.dependencies import ProducerDeps
from corsair.agents.producer.tools.bash import register_bash
from corsair.agents.producer.tools.read_skill import register_read_skill
from corsair.agents.producer.tools.submit import register_submit
from corsair.agents.resources import instruction, validate_agent_spec


def instructions() -> str:
    """Lazily load the producer instruction so importing agents has no filesystem I/O."""
    return instruction(__package__)


def build_producer(model: Model, *, max_submissions: int = 4) -> Agent[ProducerDeps, str]:
    """Build a spec-validated PydanticAI producer with its three declared tools."""
    validate_agent_spec(__package__, tool_names=("bash", "read_skill", "submit"))
    agent: Agent[ProducerDeps, str] = Agent(
        model,
        deps_type=ProducerDeps,
        output_type=str,
        instructions=instructions(),
        retries=1,
        name="producer",
    )
    register_submit(agent, retries=max_submissions)

    @agent.output_validator
    def final_text(ctx: RunContext[ProducerDeps], text: str) -> str:
        """Reject empty or leaked-template final responses while leaving verdicts to the kernel."""
        cleaned = text.strip()
        if not cleaned or "<|im_" in cleaned or "<|endoftext|>" in cleaned:
            raise ModelRetry(
                "Reply with one plain sentence: either call submit with a probe, or state why you stop."
            )
        return cleaned

    register_bash(agent)
    register_read_skill(agent)
    return agent
