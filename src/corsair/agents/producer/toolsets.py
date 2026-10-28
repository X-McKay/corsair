"""Concrete producer tool composition for one fresh ADK episode."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.tools.skill_toolset import SkillDiscoveryMode, SkillToolset

from corsair.agents.resources import load_agent_spec, load_runtime_skills
from corsair.contracts import ProducerInput
from corsair.ports.scm import SourceReader

from .tools import (
    create_list_files,
    create_preview_invocation,
    create_read_file,
    create_relative_path,
)


def _callable_name(tool: Callable[..., Any]) -> str:
    name = getattr(tool, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError("producer source tool creators must return named callables")
    return name


def build_producer_toolset(
    producer_input: ProducerInput, sources: SourceReader
) -> list[Callable[..., Any] | SkillToolset]:
    """Return episode-bound source reads, pure helpers and the finite native loader."""

    spec = load_agent_spec("producer")
    function_tools = [
        create_read_file(producer_input, sources),
        create_list_files(producer_input, sources),
        create_preview_invocation(producer_input),
        create_relative_path(producer_input),
    ]
    names = [_callable_name(tool) for tool in function_tools]
    if names != [*spec.source_tools, *spec.mechanical_tools]:
        raise ValueError("producer function tool creators do not match approved metadata")
    return [
        *function_tools,
        SkillToolset(
            skills=load_runtime_skills("producer"),
            discovery_mode=SkillDiscoveryMode.EAGER,
            tool_filter=list(spec.loader_tools),
        ),
    ]
