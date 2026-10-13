"""Explicit registration of the authoring agent's model-facing tools, in offered order.

Two toolsets keep their own ids (their durable activity identity): source reads, and test writes and runs.
"""

from pydantic_ai.toolsets import FunctionToolset

from ...source.tools import READ_SOURCE_TOOL, TOOL_RETRIES
from ...toolset_identity import toolsets_sha256
from ..dependencies import AuthoringDependencies
from ._preparation import while_edits_can_help
from .read_source import read_source
from .run_tests import RUN_TOOL, run_tests
from .write_test_file import WRITE_TOOL, write_test_file

TOOLSET_ID = "test_authoring"
SOURCE_TOOLSET_ID = "test_authoring_source"


def authoring_tools() -> FunctionToolset[AuthoringDependencies]:
    tools = FunctionToolset[AuthoringDependencies](id=TOOLSET_ID)
    tools.add_function(write_test_file, name=WRITE_TOOL, retries=TOOL_RETRIES, prepare=while_edits_can_help)
    tools.add_function(run_tests, name=RUN_TOOL, retries=TOOL_RETRIES, sequential=True, prepare=while_edits_can_help)
    return tools


def source_tools() -> FunctionToolset[AuthoringDependencies]:
    """Bounded windows over saved source and the author's own written tests."""
    tools = FunctionToolset[AuthoringDependencies](id=SOURCE_TOOLSET_ID)
    tools.add_function(read_source, name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    return tools


# Offered order: source reads first, then writes and runs (agent.py).
TOOLSET_SHA256 = toolsets_sha256(source_tools(), authoring_tools())
