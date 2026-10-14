"""Explicit ordered native registration; same offered surface for all three roles."""

from pydantic_ai.toolsets import FunctionToolset
from corsair.agents.toolset_identity import toolset_sha256
from ..dependencies import DraftingDependencies
from .read_source import read_source
from .write_test_file import write_test_file

TOOLSET_ID = "split_authoring_experiment"


def drafting_tools():
    tools = FunctionToolset[DraftingDependencies](id=TOOLSET_ID)
    tools.add_function(read_source, name="read_source", retries=0)
    tools.add_function(write_test_file, name="write_test_file", retries=0)
    return tools


TOOLSET_SHA256 = toolset_sha256(drafting_tools())
