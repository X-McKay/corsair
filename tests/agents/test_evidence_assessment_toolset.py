"""The assessment toolset offers exactly its registered tool; any change to what it offers changes its digest."""

from corsair.agents.evidence_assessment.tools import TOOLSET_SHA256, evidence_tools
from corsair.agents.toolset_identity import toolset_sha256

# Reviewed inventory-id and bounded-window guidance; registration and retry limits stay unchanged.
OFFERED_SHA256 = "d8c696c4c61a869606a3b8b2624f48946bf1641afc87bc4dcb8e55dcad92be94"


def test_toolset_offers_exactly_the_registered_tool():
    tools = evidence_tools()
    assert tools.id == "evidence_assessment_evidence"
    assert {name: tool.max_retries for name, tool in tools.tools.items()} == {"read_evidence": 0}


def test_toolset_digest_covers_reviewed_navigation_guidance():
    assert TOOLSET_SHA256 == toolset_sha256(evidence_tools()) == OFFERED_SHA256


def test_reader_feedback_names_admitted_items_and_stops_at_last_line():
    import asyncio
    from types import SimpleNamespace
    import pytest
    from pydantic_ai import ModelRetry
    from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
    from corsair.agents.evidence_assessment.tools.read_evidence import read_evidence
    from tests.agents.test_evidence_assessment import inputs
    context = SimpleNamespace(deps=AssessmentDependencies(inputs()))
    with pytest.raises(ModelRetry, match='use an inventory id: plan, baseline-0-junit'):
        asyncio.run(read_evidence(context, 'unlisted-source.py'))
    read = asyncio.run(read_evidence(context, 'plan'))
    assert read.end_line == 1
    with pytest.raises(ModelRetry, match=r'plan has lines 1\.\.1; requested start_line 2'):
        asyncio.run(read_evidence(context, 'plan', 2))
