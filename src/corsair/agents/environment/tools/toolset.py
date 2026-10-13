"""Explicit registration of the environment agent's model-facing tools, in offered order.

A module under tools/ is offered only once it is registered here; nothing is discovered by scanning.
"""

from dataclasses import asdict
from hashlib import sha256
import json

from pydantic_ai.toolsets import FunctionToolset

from ..dependencies import EnvironmentDependencies
from .list_toolchains import LIST_TOOLCHAINS_TOOL, list_toolchains
from .read_output import READ_OUTPUT_TOOL, read_output
from .read_source import READ_SOURCE_TOOL, read_source
from .run_setup_command import RUN_SETUP_COMMAND_TOOL, run_setup_command

TOOLSET_ID = "environment"
TOOL_RETRIES = 0


def environment_tools() -> FunctionToolset[EnvironmentDependencies]:
    tools = FunctionToolset[EnvironmentDependencies](id=TOOLSET_ID)
    tools.add_function(read_source, name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    tools.add_function(list_toolchains, name=LIST_TOOLCHAINS_TOOL, retries=TOOL_RETRIES)
    tools.add_function(run_setup_command, name=RUN_SETUP_COMMAND_TOOL, retries=TOOL_RETRIES)
    tools.add_function(read_output, name=READ_OUTPUT_TOOL, retries=TOOL_RETRIES)
    return tools


def toolset_sha256(toolset: FunctionToolset) -> str:
    """Digest of what the toolset offers: id, order, every tool definition field and retry limit."""
    offered = [asdict(tool.tool_def) | {"max_retries": tool.max_retries} for tool in toolset.tools.values()]
    return sha256(json.dumps({"id": toolset.id, "tools": offered}, sort_keys=True).encode()).hexdigest()


TOOLSET_SHA256 = toolset_sha256(environment_tools())
