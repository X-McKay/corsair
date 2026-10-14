"""Grounding placeholder: intake rules, fixture retrieval, deterministic citations and the advisory agent."""
import asyncio

import pytest
from pydantic import ValidationError
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel

from corsair.v2.agents.grounding.agent import create_agent, ground, render_prompt
from corsair.v2.agents.grounding.citations import validate_citations
from corsair.v2.agents.grounding.contracts import (FindingInput, GroundingBrief, GroundingContext,
                                                   Precedent, Skip)
from corsair.v2.agents.grounding.graph import (CWE_PEERS, InMemoryGraph, gather, hops_in_range, query_text_for,
                                               source_location)
from corsair.v2.agents.grounding.intake import (FixtureWorkItems, InMemoryWriteBack, IntakeTooLarge,
                                                backfill_location_from_graph, check_wiql, parse_scan_header,
                                                work_item_to_finding)
from corsair.v2.agents.grounding.tools import render_context
from corsair.v2.contracts import Finding
from tests.v2.agent_scripts import Script, tool_returns

HEADER = ("<div>Scanner report</div><div>Project:   Payments</div><p>Repository: payments-api</p>"
          "<p>Branch: main</p><p>Commit: 3f9c1a0e5b7d2c4f6a8b0d1e2f3a4b5c6d7e8f90</p>"
          "<p>Run ID: ado-contoso-20260914-1731</p>")


def item(item_id=7, **fields):
    return {"id": item_id, "fields": {"System.Title": "SQL built from input", "System.Description": HEADER,
                                      "System.CreatedBy": "A Person", **fields}}


def test_work_item_maps_from_header_and_never_guesses():
    finding = work_item_to_finding(item(**{"Custom.CWE": "89", "Custom.StartLine": " 12 "}))
    assert isinstance(finding, FindingInput)
    assert finding.repo_url == "https://dev.azure.com/contoso/Payments/_git/payments-api"
    assert finding.revision == "3f9c1a0e5b7d2c4f6a8b0d1e2f3a4b5c6d7e8f90"
    assert (finding.cwe, finding.start_line, finding.ado_work_item_id) == ("CWE-89", 12, 7)
    assert finding.source_tool is None and "Scanner report\nProject:   Payments" in finding.description
    skipped = work_item_to_finding(item(**{"System.Description": "<p>Repository: payments-api</p>"}))
    assert skipped == Skip(external_id="7", reason="the work item establishes no repository")


def test_only_a_commit_field_pins_the_revision_and_the_last_occurrence_wins():
    ref = parse_scan_header("Commit: v1.2.3\nBranch: release\nhash deadbeefdeadbeef")
    assert ref.commit is None and ref.branch == "release"
    ref = parse_scan_header("Commit: abc1234\n- **Commit:** def5678\nProject: A  Repository: r")
    assert (ref.commit, ref.project, ref.repository) == ("def5678", "A", "r")
    ref = parse_scan_header("Project: X\nsee https://dev.azure.com/org/Proj/_git/repo for details")
    assert (ref.organization, ref.project, ref.repository) == ("org", "Proj", "repo")


def test_wiql_shape_and_intake_cap():
    check_wiql("SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'New'")
    for bad in ("SELECT 1 FROM WorkItems; DELETE", "SELECT 1 FROM WorkItemLinks", "SELECT 1 FROM WorkItems -- x",
                "UPDATE WorkItems", "x" * 4001):
        with pytest.raises(ValueError):
            check_wiql(bad)
    source = FixtureWorkItems([item(1), item(2), item(3)], max_items=2)
    assert [i["id"] for i in source.fetch_work_items([2, 1, 2])] == [2, 1]
    with pytest.raises(IntakeTooLarge):
        source.fetch_work_items(wiql="SELECT [System.Id] FROM WorkItems")


def test_write_back_is_off_by_default_and_one_comment_per_item():
    assert InMemoryWriteBack().upsert_comment(7, "body") is None
    sink = InMemoryWriteBack(enabled=True)
    assert sink.upsert_comment(7, "first") == sink.upsert_comment(7, "second") == "comment-7"
    assert sink.comments == {7: "second"}


GRAPH = InMemoryGraph(
    issues=[
        {"id": "7", "title": "SQL built from input in report query", "state": "Active", "cwe": "CWE-89",
         "source_file": "/src/report.py:40"},
        {"id": "11", "title": "SQL built from input in export", "state": "Closed", "cwe": "CWE-89"},
        {"id": "12", "title": "Unrelated open SQL issue", "state": "Active", "cwe": "CWE-89"},
        {"id": "20", "properties": None, "title": "SQL built from report query input", "state": "Resolved"},
    ],
    comments={"11": [{"author": "rev", "created_at": "2026-01-02",
                      "text": "<div><span>Not exploitable: the export parameters are bound.</span></div>"},
                     {"author": "rev", "created_at": "2026-01-01", "text": "Looking into it"}],
              "12": [{"author": "rev", "created_at": "2026-02-01", "text": "Still open, argument in progress"}]})


def test_gather_retrieves_decided_neighbours_and_names_failures():
    context = gather(GRAPH, "7", query_text_for("SQL built from input in report query", "CWE-89", "body"))
    assert context.issue.id == "7" and context.comments == ()  # an undecided issue yields no comments
    assert [(r.issue.id, r.relation) for r in context.related] == [("11", "cwe"), ("20", "similarity")]
    assert context.related[0].comments[0].text == "Not exploitable: the export parameters are bound."
    assert context.degraded == ()
    missing = gather(GRAPH, "404", "nothing similar at all")
    assert missing.issue is None and missing.degraded == ("issue lookup failed: IssueNotFound: 404",)
    off = gather(None, "7", "anything")
    assert off.empty and "not configured" in off.degraded[0]
    assert render_context(off) != render_context(GroundingContext())


def test_queries_stay_parameterised_reads():
    with pytest.raises(ValueError):
        GRAPH.query("MATCH (n) DETACH DELETE n", {})
    with pytest.raises(ValueError):
        GRAPH.query("MATCH (n) RETURN n", {"id": "7"})
    assert GRAPH.query(CWE_PEERS, {"id": "7", "states": ["closed"], "top_k": 5}) == [{"peer": GRAPH.issues[1]}]
    for bad in (True, 0, 5, "2"):
        with pytest.raises(ValueError):
            hops_in_range(bad)
    assert source_location("/src/a.py:40") == ("src/a.py", 40) and source_location("../a.py:3") == (None, None)


def test_backfill_fills_only_missing_fields_and_fails_soft():
    finding = work_item_to_finding(item(**{"Custom.CWE": "CWE-79"}))
    filled, note = backfill_location_from_graph(finding, GRAPH)
    assert (filled.file_path, filled.start_line, filled.cwe) == ("src/report.py", 40, "CWE-79")
    assert note == "backfilled file_path, start_line"
    unknown = finding.model_copy(update={"ado_work_item_id": 999})
    assert backfill_location_from_graph(unknown, GRAPH) == (unknown, "graph holds no issue 999")


CONTEXT = gather(GRAPH, "7", "SQL built from input in report query")
QUOTE = "the export   parameters are BOUND"


def precedent(issue_id="11", quote=QUOTE):
    return Precedent(issue_id=issue_id, disposition="not_exploitable", relation="cwe", quote=quote)


def test_citations_keep_supported_precedents_and_drop_the_rest_with_caveats():
    brief = GroundingBrief(summary="One prior decision.", precedents=(
        precedent(), precedent("99"), precedent(quote="bound"), precedent(quote="the parameters are escaped")))
    checked = validate_citations(brief, CONTEXT.model_copy(update={"degraded": ("similarity search failed: X",)}))
    assert checked.precedents == (precedent(),)
    assert checked.caveats[0] == "similarity search failed: X"
    assert checked.caveats[1] == ("Unsupported precedents were dropped because the retrieved context does not "
                                  "contain them: 99: not in the retrieved context; 11: quote too short to verify; "
                                  "11: quote not found in the retrieved text")
    lone = GroundingBrief(summary="s", precedents=(precedent("99"),), prior_disposition="fixed")
    assert validate_citations(lone, CONTEXT).prior_disposition is None
    with pytest.raises(ValidationError):
        GroundingBrief(summary="s", prior_disposition="fixed")


FINDING = Finding(title="SQL built from input in report query", cwe="CWE-89")


def test_empty_context_yields_no_brief_and_no_model_call():
    script = Script([])
    brief, usage = asyncio.run(ground(FINDING, gather(None, "7", "x"), script.model))
    assert brief is None and script.index == 0
    assert (usage.agent, usage.requests, usage.input_tokens, usage.tool_calls) == ("grounding", None, None, None)


def test_agent_reads_the_context_with_tools_and_its_brief_is_checked():
    script = Script([("read_issue_comments", {"issue_id": "11"}), ("read_issue", {"issue_id": "nope"}),
                     {"summary": "One prior decision found the export safe.",
                      "precedents": [precedent().model_dump(), precedent(quote="invented reviewer sentence").model_dump()],
                      "caveats": []}])
    brief, usage = asyncio.run(ground(FINDING, CONTEXT, script.model))
    returns = tool_returns(script.seen[-1])
    assert "Not exploitable: the export parameters are bound." in returns[0][2]
    assert "not in the retrieved context" in returns[1][2]
    assert brief.precedents == (precedent(),) and "quote not found" in brief.caveats[-1]
    assert (usage.status, usage.requests, usage.tool_calls) == ("ok", 3, 2)
    prompt = render_prompt(FINDING, CONTEXT)
    assert "<retrieved_context>" in prompt and "[11] relation=cwe" in prompt


def test_factory_direct_and_durable_construction():
    assert create_agent(TestModel()).name == "grounding"
    assert create_agent(TestModel(), durability=TemporalDurability()).name == "grounding"
