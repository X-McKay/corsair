"""The Control Prober's tools: the native Harness ``FileSystem``, read-only, over the revision's tree, plus its one
write, ``write_test_file``, under this agent's own durable toolset id. The functions are shared with the other
Prober (``agents/probing``). There is deliberately no tool that runs a test (D3).
"""
from ..probing.source import TOOL_NAMES as SOURCE_TOOLS

TOOLSET_ID = "control_prober"
TOOL_NAMES = (*SOURCE_TOOLS, "write_test_file")
