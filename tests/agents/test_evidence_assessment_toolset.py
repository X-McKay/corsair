"""The assessment toolset offers exactly its registered tool; any change to what it offers changes its digest."""

from corsair.agents.evidence_assessment.tools import TOOLSET_SHA256, evidence_tools
from corsair.agents.toolset_identity import toolset_sha256

# Recorded from the pre-split tools.py on 0ad9900 (SPEC-0052); change only with a reviewed tool change.
OFFERED_SHA256 = "b488713db6baab0ebda72b27e6818788f7113bddebf07e537e4aae4ee001e802"


def test_toolset_offers_exactly_the_registered_tool():
    tools = evidence_tools()
    assert tools.id == "evidence_assessment_evidence"
    assert {name: tool.max_retries for name, tool in tools.tools.items()} == {"read_evidence": 0}


def test_toolset_digest_is_unchanged_by_the_package_split():
    assert TOOLSET_SHA256 == toolset_sha256(evidence_tools()) == OFFERED_SHA256
