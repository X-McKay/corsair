"""The planning toolset offers exactly the shared reader under its own id; any change to what it offers changes the digest."""

from corsair.agents.test_planning.tools import TOOLSET_SHA256, offered_tools, planning_tools, withdraw_when_read
from corsair.agents.toolset_identity import toolset_sha256

# The reader's definitions, recorded from the pre-split agent.py on 311d8cd (SPEC-0052).
READER_SHA256 = "80bdf2426bd922d65a0ebefa41198c10cd64ea62dcd6bae06d91ef471dc5c1c9"
# What is offered: that reader inside the PreparedToolset and its withdraw_when_read rule.
# Change either value only with a reviewed tool change.
OFFERED_SHA256 = "68bfbba4a0385ec77a98571a8170bbeafe5c782f5a51fea0e94fce1f1e41bee7"


def test_toolset_offers_exactly_the_shared_reader_withdrawn_once_read():
    tools = planning_tools()
    assert tools.id == "test_planning_source"
    assert {name: tool.max_retries for name, tool in tools.tools.items()} == {"read_source": 0}
    offered = offered_tools()
    assert offered.prepare_func is withdraw_when_read and offered.wrapped.id == "test_planning_source"


def test_reader_definitions_are_unchanged_by_the_package_split():
    assert toolset_sha256(planning_tools()) == READER_SHA256


def test_digest_covers_the_offered_toolset_and_its_preparation_rule():
    assert TOOLSET_SHA256 == toolset_sha256(offered_tools()) == OFFERED_SHA256 != READER_SHA256
