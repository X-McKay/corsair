"""The authoring toolsets offer exactly their registered tools; any change to what they offer changes the digest."""

from corsair.agents.test_authoring.tools import TOOLSET_SHA256, authoring_tools, source_tools
from corsair.agents.toolset_identity import toolsets_sha256

# Recorded from the pre-split tools.py (SPEC-0052); change only with a reviewed tool change.
OFFERED_SHA256 = "6ffc0788bafce223e5ed44f6900fe8cdde7bfd25abd7625d370325cd0d181b57"


def test_toolsets_offer_exactly_the_registered_tools():
    source, authoring = source_tools(), authoring_tools()
    assert (source.id, list(source.tools)) == ("test_authoring_source", ["read_source"])
    assert (authoring.id, list(authoring.tools)) == ("test_authoring", ["write_test_file", "run_tests"])
    assert all(tool.max_retries == 0 for tool in (*source.tools.values(), *authoring.tools.values()))
    assert authoring.tools["run_tests"].sequential and not authoring.tools["write_test_file"].sequential


def test_toolset_digest_is_unchanged_by_the_package_split():
    assert TOOLSET_SHA256 == toolsets_sha256(source_tools(), authoring_tools()) == OFFERED_SHA256
