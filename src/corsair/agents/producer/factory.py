"""Producer agent construction.

The dynamic source tools are created by the activity runner and passed here;
this factory intentionally owns no session state or source handles.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from google.adk.agents import LlmAgent

from corsair.runtime.models import load_agent_spec, prompt_text


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", "")))


def build_producer(
    model: Any,
    private_tools: Sequence[Any] | None = None,
    *,
    tools: Sequence[Any] | None = None,
) -> LlmAgent:
    """Build the producer with only its episode-private approved tools.

    ``tools`` is retained as a keyword alias for callers that naturally name
    the private capability collection that way. Passing both names is rejected
    rather than silently selecting one.
    """

    if private_tools is not None and tools is not None:
        raise ValueError("pass private_tools or tools, not both")
    selected_tools = list(tools if tools is not None else private_tools or [])
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
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
