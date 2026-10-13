"""Digest of what a native toolset offers the model, for eval run identity (SPEC-0052)."""

from dataclasses import asdict
from hashlib import sha256
import json

from pydantic_ai.toolsets import AbstractToolset, FunctionToolset, WrapperToolset


def _offered(toolset: AbstractToolset) -> dict:
    if isinstance(toolset, WrapperToolset):
        # A wrapper (for example a native PreparedToolset) changes what is offered by its own rule.
        rule = getattr(toolset, "prepare_func", None)
        return {"wrapper": type(toolset).__name__,
                "rule": f"{rule.__module__}.{rule.__qualname__}" if rule is not None else None,
                "wrapped": _offered(toolset.wrapped)}
    if not isinstance(toolset, FunctionToolset):
        raise TypeError(f"no offered-surface digest for {type(toolset).__name__}")
    return {"id": toolset.id,
            "tools": [asdict(tool.tool_def) | {"max_retries": tool.max_retries} for tool in toolset.tools.values()]}


def toolset_sha256(toolset: AbstractToolset) -> str:
    """Digest of the toolset id and, in offered order, every tool definition field and retry limit."""
    return sha256(json.dumps(_offered(toolset), sort_keys=True).encode()).hexdigest()


def toolsets_sha256(*toolsets: AbstractToolset) -> str:
    """Digest of several toolsets in offered order; a single toolset keeps its own digest."""
    digests = [toolset_sha256(toolset) for toolset in toolsets]
    return digests[0] if len(digests) == 1 else sha256(json.dumps(digests).encode()).hexdigest()
