"""Producer agent construction with episode-private source tools and skills."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools.skill_toolset import SkillToolset

from corsair.agents.resources import load_agent_spec, prompt_text

from .contracts import ProducerDecision


def _tool_name(tool: Callable[..., Any]) -> str:
    name = getattr(tool, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError("producer source tools must have non-empty callable names")
    return name


def build_producer(
    model: str | BaseLlm,
    tools: Sequence[Callable[..., Any] | SkillToolset],
) -> LlmAgent:
    """Build the producer from its bound readers/helpers and native skill loader."""

    selected_tools = list(tools)
    spec = load_agent_spec("producer")
    expected_names = [*spec.source_tools, *spec.mechanical_tools]
    function_candidates = selected_tools[: len(expected_names)]
    loader_tools = selected_tools[len(expected_names) :]
    if len(loader_tools) != 1 or not isinstance(loader_tools[0], SkillToolset):
        raise ValueError("producer must receive exactly one native SkillToolset")
    if any(not callable(tool) for tool in function_candidates):
        raise ValueError("producer function tools must be native callables")
    function_tools = [cast(Callable[..., Any], tool) for tool in function_candidates]
    names = [_tool_name(tool) for tool in function_tools]
    if names != expected_names:
        raise ValueError(
            "producer function tools must exactly match approved metadata "
            f"{expected_names!r}; received {names!r}"
        )
    loader = loader_tools[0]
    if [skill.name for skill in loader.skills] != spec.runtime_skills:
        raise ValueError("producer SkillToolset skills do not match approved metadata")
    if loader.tool_filter != spec.loader_tools:
        raise ValueError("producer SkillToolset tools do not match approved metadata")
    if spec.instruction_resource != "corsair.agents.producer.instructions:system.md":
        raise ValueError("producer instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.ProducerDecision":
        raise ValueError("producer schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Proposes one declarative payload pair for trusted verification.",
        model=model,
        instruction=prompt_text("producer")
        + "\n\n"
        + "\n\n".join(
            f"## Runtime procedure: {skill.name}\n{skill.instructions}" for skill in loader.skills
        ),
        tools=selected_tools,
        output_schema=ProducerDecision,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
