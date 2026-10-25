"""Producer agent construction.

The dynamic source tools are created by the activity runner and passed here;
this factory intentionally owns no session state or source handles.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

from corsair.agents.resources import load_agent_spec, prompt_text
from corsair.contracts import Submission


def _tool_name(tool: Callable[..., Any]) -> str:
    name = getattr(tool, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError("producer tools must have non-empty callable names")
    return name


def build_producer(
    model: str | BaseLlm,
    tools: Sequence[Callable[..., Any]],
) -> LlmAgent:
    """Build the producer with only its episode-private approved tools.

    The caller supplies the one approved, episode-private capability collection.
    """

    selected_tools = list(tools)
    spec = load_agent_spec("producer")
    names = [_tool_name(tool) for tool in selected_tools]
    if names != spec.tools:
        raise ValueError(
            "producer tools must exactly match approved metadata "
            f"{spec.tools!r}; received {names!r}"
        )
    if spec.instruction_resource != "corsair.agents.producer.instructions:system.md":
        raise ValueError("producer instruction resource metadata is not canonical")
    if spec.schema_ref != "corsair.contracts.Submission":
        raise ValueError("producer schema metadata is not canonical")

    return LlmAgent(
        name=spec.name,
        description="Proposes one declarative payload pair for trusted verification.",
        model=model,
        instruction=prompt_text("producer"),
        tools=selected_tools,
        output_schema=Submission,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
