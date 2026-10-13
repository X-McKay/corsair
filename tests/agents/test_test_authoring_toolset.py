"""The authoring toolsets offer exactly their registered tools; any change to what they offer changes the digest."""

from corsair.agents.test_authoring.tools import TOOLSET_SHA256, authoring_tools, source_tools
from corsair.agents.toolset_identity import toolsets_sha256

# Recorded after the intentional unit-observation write_test_file guidance change.
# Keep this explicit identity synchronized with reviewed model-facing tool changes.
UNIT_OBSERVATION_SHA256 = "40f832e60ff04a26565da8c7941f4e3746d8b7106a253fb3768a651e196c580e"


def test_toolsets_offer_exactly_the_registered_tools():
    source, authoring = source_tools(), authoring_tools()
    assert (source.id, list(source.tools)) == ("test_authoring_source", ["read_source"])
    assert (authoring.id, list(authoring.tools)) == ("test_authoring", ["write_test_file", "run_tests"])
    assert all(tool.max_retries == 0 for tool in (*source.tools.values(), *authoring.tools.values()))
    assert authoring.tools["run_tests"].sequential and not authoring.tools["write_test_file"].sequential


def test_toolset_digest_records_unit_observation_tool_guidance():
    assert TOOLSET_SHA256 == toolsets_sha256(source_tools(), authoring_tools()) == UNIT_OBSERVATION_SHA256
