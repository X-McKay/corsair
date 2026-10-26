"""Concrete producer tool composition for one fresh ADK episode."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from corsair.agents.resources import load_agent_spec
from corsair.contracts import ProducerInput
from corsair.ports.scm import SourceReader

from .tools import create_list_files, create_read_file


def _callable_name(tool: Callable[..., Any]) -> str:
    name = getattr(tool, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError("producer source tool creators must return named callables")
    return name


def build_producer_toolset(
    producer_input: ProducerInput, sources: SourceReader
) -> list[Callable[..., Any]]:
    """Return exactly the two episode-bound source reads; the procedure is preloaded."""

    spec = load_agent_spec("producer")
    source_tools = [
        create_read_file(producer_input, sources),
        create_list_files(producer_input, sources),
    ]
    names = [_callable_name(tool) for tool in source_tools]
    if names != spec.tools:
        raise ValueError("producer source tool creators do not match approved metadata")
    return source_tools
