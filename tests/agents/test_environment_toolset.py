"""The environment toolset offers exactly its registered tools; any change to what it offers changes its digest."""

from corsair.agents.environment.tools import TOOLSET_SHA256, environment_tools, toolset_sha256

# SPEC-0053 adds explicit bounded correction arguments and guidance after the SPEC-0052 split; PLAN-0079 offers a
# toolchain's language as the matrix row's pattern-checked name instead of a fixed list.
OFFERED_SHA256 = "75f1363f62dbfd89c765dc3acd6856726d6241858824d80744e349775aa586a8"


def test_toolset_offers_exactly_the_registered_tools_in_order():
    tools = environment_tools()
    assert tools.id == "environment"
    assert list(tools.tools) == ["read_source", "list_toolchains", "run_setup_command", "read_output"]
    assert {name: tool.max_retries for name, tool in tools.tools.items()} == dict.fromkeys(tools.tools, 0)


def test_toolset_digest_matches_reviewed_correction_contract():
    assert TOOLSET_SHA256 == toolset_sha256(environment_tools()) == OFFERED_SHA256


def test_digest_changes_when_an_offered_definition_changes():
    tools = environment_tools()
    tools.add_function(lambda: None, name="unreviewed")
    assert toolset_sha256(tools) != OFFERED_SHA256
