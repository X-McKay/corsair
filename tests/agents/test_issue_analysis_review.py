"""Isolated native contract checks for the issue evidence reviewer."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput
from corsair.agents.issue_analysis.review import (
    ReviewDependencies, ReviewDraft, ReviewReport, create_evidence_reviewer, review_prompt,
)

ROOT = Path(__file__).resolve().parents[2] / "evals" / "issue_analysis"
AUDIT = [{"operation": "A sensitive operation may run.",
          "required_condition": "Its input and resource are available.",
          "coverage": "entailed", "basis": "The candidate's stated preconditions cover this."}]


@pytest.fixture(autouse=True)
def no_provider_requests():
    with models.override_allow_model_requests(False):
        yield


def case(name="path_traversal"):
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())
    analysis = IssueAnalysis.model_validate(json.loads((ROOT / "oracles.json").read_text())["cases"][name])
    return inputs, analysis


def run(inputs, analysis, model, *, output_retries=0, history=None):
    return create_evidence_reviewer(model, output_retries=output_retries).run_sync(
        review_prompt(inputs, analysis), deps=ReviewDependencies(inputs, analysis),
        message_history=history, usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1),
    )


def scripted_review(draft, *, read=True, read_path="documents.py", read_start=1, read_end=4):
    draft = {"condition_audit": AUDIT if draft["assessment"] == "supported" else []} | draft
    async def respond(messages, info):
        if read and len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("read_source", {
                "path": read_path, "start_line": read_start, "end_line": read_end,
            })])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, draft)])
    return FunctionModel(respond)


def test_supported_review_reads_source_and_materializes_current_run_quote():
    inputs, analysis = case()
    draft = {"assessment": "supported", "scope": "component", "findings": [],
             "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
             "limitations": ["Application caller and runtime state are not established."]}
    result = run(inputs, analysis, scripted_review(draft))
    assert isinstance(result.output, ReviewReport)
    assert result.output.assessment == "supported" and result.output.findings == ()
    assert result.output.citations[0].quote == "\n".join(inputs.source_files[0].content.splitlines()[2:4])
    assert result.usage.tool_calls == 1
    prompt = review_prompt(inputs, analysis)
    assert inputs.fixture_id not in prompt
    assert analysis.citations[0].quote not in prompt


def test_targeted_finding_has_independent_source_provenance_and_no_rewrite():
    inputs, analysis = case()
    draft = {"assessment": "needs_revision", "scope": "component", "findings": [{
        "field_path": "hypothesis.preconditions", "problem": "A necessary condition was not stated.",
        "citations": [{"path": "documents.py", "start_line": 4, "end_line": 4}],
    }], "citations": [], "limitations": ["The caller is not shown."]}
    result = run(inputs, analysis, scripted_review(draft))
    assert result.output.findings[0].field_path == "hypothesis.preconditions"
    assert result.output.findings[0].citations[0].quote == inputs.source_files[0].content.splitlines()[3]
    assert not hasattr(result.output, "hypothesis")
    assert analysis.status == "ready"


@pytest.mark.parametrize("draft", [
    {"assessment": "supported", "scope": "component", "findings": [],
     "citations": [{"path": "documents.py", "start_line": 1, "end_line": 4}],
     "limitations": ["No execution evidence."]},
    {"assessment": "needs_revision", "scope": "component", "findings": [{
        "field_path": "citations", "problem": "The cited range was not read in this run.",
        "citations": [{"path": "documents.py", "start_line": 1, "end_line": 4}],
    }], "citations": [], "limitations": ["No execution evidence."]},
])
def test_unread_and_prior_run_citations_do_not_authorize_review(draft):
    inputs, analysis = case()
    prior = run(inputs, analysis, scripted_review({
        "assessment": "supported", "scope": "component", "findings": [],
        "citations": [{"path": "documents.py", "start_line": 1, "end_line": 4}],
        "limitations": ["No execution evidence."],
    }))
    with pytest.raises(UnexpectedModelBehavior):
        run(inputs, analysis, scripted_review(draft, read=False), history=prior.all_messages())


def test_absent_source_can_be_reviewed_without_invented_citation():
    inputs, analysis = case("missing_source")
    draft = {"assessment": "supported", "scope": "component", "findings": [],
             "citations": [], "condition_audit": [],
             "limitations": ["No source was supplied, so the missing-information conclusion is bounded."]}
    result = run(inputs, analysis, TestModel(call_tools=[], custom_output_args=draft))
    assert result.output.assessment == "supported" and result.output.citations == ()
    assert result.usage.tool_calls == 0

    insufficient = {"assessment": "insufficient_evidence", "scope": "component", "findings": [{
        "field_path": "missing_facts", "problem": "No application source is listed for an independent review.",
        "citations": [],
    }], "citations": [], "condition_audit": [], "limitations": ["No source is available."]}
    second = run(inputs, analysis, TestModel(call_tools=[], custom_output_args=insufficient))
    assert second.output.assessment == "insufficient_evidence"
    assert second.output.findings[0].citations == ()


def test_supported_source_review_requires_citation_and_scope():
    inputs, analysis = case()
    for draft in (
        {"assessment": "supported", "scope": "component", "findings": [], "citations": [],
         "limitations": ["No execution evidence."]},
        {"assessment": "supported", "scope": "application_path", "findings": [],
         "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
         "limitations": ["No execution evidence."]},
        {"assessment": "needs_revision", "scope": "component", "findings": [{
            "field_path": "hypothesis.observable_effect", "problem": "The effect is unsupported.",
            "citations": [],
        }], "citations": [], "limitations": ["No execution evidence."]},
    ):
        with pytest.raises(UnexpectedModelBehavior):
            run(inputs, analysis, scripted_review(draft))


def test_supported_review_rejects_candidate_fabricated_or_absent_quote():
    inputs, analysis = case()
    supported = {"assessment": "supported", "scope": "component", "findings": [],
                 "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
                 "limitations": ["No execution evidence."]}
    for candidate in (
        analysis.model_copy(update={"citations": (
            analysis.citations[0].model_copy(update={"quote": "fabricated source"}),
        )}),
        analysis.model_copy(update={"citations": (
            analysis.citations[0].model_copy(update={"path": "absent.py"}),
        )}),
    ):
        with pytest.raises(UnexpectedModelBehavior):
            run(inputs, candidate, scripted_review(supported))


def test_unknown_tool_is_refused_without_authority_expansion():
    inputs, analysis = case()
    calls = []

    async def respond(messages, info):
        calls.append(len(messages))
        return ModelResponse(parts=[ToolCallPart("run_shell", {"command": "true"})])

    with pytest.raises(UnexpectedModelBehavior, match="run_shell"):
        run(inputs, analysis, FunctionModel(respond), output_retries=2)
    assert len(calls) == 1


@pytest.mark.parametrize("assessment,findings", [
    ("supported", [{"field_path": "citations", "problem": "A defect was found.", "citations": []}]),
    ("needs_revision", []),
    ("insufficient_evidence", []),
])
@pytest.mark.parametrize("contract", [ReviewDraft, ReviewReport])
def test_review_contract_rejects_inconsistent_assessment(assessment, findings, contract):
    with pytest.raises(ValidationError):
        contract.model_validate({"assessment": assessment, "scope": "component",
                                 "findings": findings, "citations": [], "condition_audit": [],
                                 "limitations": ["Only the listed source was reviewed."]})


def test_condition_audit_blocks_unmet_condition_and_ungrounded_support():
    inputs, analysis = case()
    supported = {"assessment": "supported", "scope": "component", "findings": [],
                 "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
                 "condition_audit": [], "limitations": ["No execution evidence."]}
    with pytest.raises(UnexpectedModelBehavior):
        run(inputs, analysis, scripted_review(supported))

    missing = {"operation": "A claimed operation", "required_condition": "An ordinary prerequisite",
               "coverage": "missing", "basis": "The candidate omits it."}
    with pytest.raises(ValidationError):
        ReviewDraft.model_validate(supported | {"condition_audit": [missing]})
    with pytest.raises(ValidationError):
        ReviewDraft.model_validate(supported | {
            "assessment": "insufficient_evidence", "condition_audit": [missing],
            "findings": [{"field_path": "hypothesis.preconditions", "problem": "Known prerequisite missing.",
                          "citations": []}],
        })
    with pytest.raises(ValidationError):
        ReviewDraft.model_validate(supported | {
            "assessment": "needs_revision", "condition_audit": [missing],
            "findings": [{"field_path": "citations", "problem": "Unrelated finding.", "citations": []}],
        })
    ReviewDraft.model_validate(supported | {
        "assessment": "needs_revision", "condition_audit": [missing],
        "findings": [{"field_path": "hypothesis.preconditions", "problem": "A prerequisite is absent.",
                      "citations": []}],
    })
