"""Explicit native registration shared by two distinct independent consumers."""
from pydantic_ai.toolsets import FunctionToolset
from corsair.agents.toolset_identity import toolset_sha256
from ..dependencies import SpecialistDependencies
from .read_source import read_source
from .write_test_file import write_test_file
TOOLSET_ID = 'control_authoring'

def specialist_tools():
    tools = FunctionToolset[SpecialistDependencies](id=TOOLSET_ID)
    tools.add_function(read_source, name='read_source', retries=0)
    tools.add_function(write_test_file, name='write_test_file', retries=0)
    return tools

TOOLSET_SHA256 = toolset_sha256(specialist_tools())
