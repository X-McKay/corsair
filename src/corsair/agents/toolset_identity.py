"""Digest of what a native toolset offers the model, for eval run identity (SPEC-0052)."""

from dataclasses import asdict
from hashlib import sha256
import json

from pydantic_ai.toolsets import FunctionToolset


def toolset_sha256(toolset: FunctionToolset) -> str:
    """Digest of the toolset id and, in offered order, every tool definition field and retry limit."""
    offered = [asdict(tool.tool_def) | {"max_retries": tool.max_retries} for tool in toolset.tools.values()]
    return sha256(json.dumps({"id": toolset.id, "tools": offered}, sort_keys=True).encode()).hexdigest()
