"""The environment toolset offers exactly its registered tools; any change to what it offers changes its digest."""

from corsair.agents.environment.tools import TOOLSET_SHA256, environment_tools, toolset_sha256

# Recorded from the pre-split tools.py on a9ba2b0 (SPEC-0052); change only with a reviewed tool change.
OFFERED_SHA256 = "cdaf4dcd511993860421106f4858fc0448a4b053b8c337d9d0587ad76c0dd0a1"


def test_toolset_offers_exactly_the_registered_tools_in_order():
    tools = environment_tools()
    assert tools.id == "environment"
    assert list(tools.tools) == ["read_source", "list_toolchains", "run_setup_command", "read_output"]
    assert {name: tool.max_retries for name, tool in tools.tools.items()} == dict.fromkeys(tools.tools, 0)


def test_toolset_digest_is_unchanged_by_the_package_split():
    assert TOOLSET_SHA256 == toolset_sha256(environment_tools()) == OFFERED_SHA256


def test_digest_changes_when_an_offered_definition_changes():
    tools = environment_tools()
    tools.add_function(lambda: None, name="unreviewed")
    assert toolset_sha256(tools) != OFFERED_SHA256
