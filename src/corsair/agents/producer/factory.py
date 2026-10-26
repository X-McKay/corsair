"""Producer agent construction with episode-private source tools and a preloaded procedure."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.skills import Skill

from corsair.agents.resources import load_agent_spec, load_runtime_skills, prompt_text

from .contracts import ProducerDecision


def _tool_name(tool: Callable[..., Any]) -> str:
    name = getattr(tool, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError("producer source tools must have non-empty callable names")
    return name


def producer_instruction(skills: Sequence[Skill]) -> str:
    """Compose the producer prompt with each admitted procedure preloaded after it."""

    return (
        prompt_text("producer")
        + "\n\n"
        + "\n\n".join(
            f"## Runtime procedure: {skill.name}\n{skill.instructions}" for skill in skills
        )
    )


def build_producer(model: str | BaseLlm, tools: Sequence[Callable[..., Any]]) -> LlmAgent:
    """Build the producer from exactly its two bound source tools and preloaded procedure."""

    selected_tools = list(tools)
    spec = load_agent_spec("producer")
    if spec.loader_tools or spec.tools != spec.source_tools:
        raise ValueError("producer metadata must grant only its source tools")
    if any(not callable(tool) for tool in selected_tools):
        raise ValueError("producer source tools must be native callables")
    names = [_tool_name(tool) for tool in selected_tools]
    if names != spec.tools:
        raise ValueError(
            "producer tools must exactly match approved metadata "
            f"{spec.tools!r}; received {names!r}"
        )
    skills = load_runtime_skills("producer")
    if [skill.name for skill in skills] != spec.runtime_skills:
        raise ValueError("producer preloaded skills do not match approved metadata")
    if spec.instruction_resource != "corsair.agents.producer.instructions:system.md":
        raise ValueError("producer instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.ProducerDecision":
        raise ValueError("producer schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Proposes one declarative payload pair for trusted verification.",
        model=model,
        instruction=producer_instruction(skills),
        tools=selected_tools,
        output_schema=ProducerDecision,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
