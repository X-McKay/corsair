"""Offline checks for the disconnected, fixed direct issue-analysis sequence."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent
from corsair.agents.issue_analysis.review import create_evidence_reviewer
from corsair.agents.issue_analysis.sequence import (
    SequenceBudgets, SequenceResult, StageBudget, run_issue_analysis_sequence,
)

ROOT = Path(__file__).resolve().parents[2] / "evals" / "issue_analysis"
BUDGETS = SequenceBudgets(
    analyst=StageBudget(request_limit=3, tool_calls_limit=1, total_tokens_limit=5000,
                        response_tokens_limit=2048, timeout_seconds=10),
    reviewer=StageBudget(request_limit=3, tool_calls_limit=1, total_tokens_limit=5000,
                         response_tokens_limit=2048, timeout_seconds=10),
)


@pytest.fixture(autouse=True)
def no_provider_requests():
    with models.override_allow_model_requests(False):
        yield


def case(name="path_traversal"):
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())
    analysis = IssueAnalysis.model_validate(json.loads((ROOT / "oracles.json").read_text())["cases"][name])
    return inputs, analysis


def scripted_analyst(analysis, prompts):
    draft = analysis.model_dump(mode="json", exclude={"citations": {"__all__": {"quote"}}})

    async def respond(messages, info):
        if len(messages) == 1:
            prompts.append(messages[0].parts[0].content)
            return ModelResponse(parts=[ToolCallPart("read_source", {
                "path": "documents.py", "start_line": 1, "end_line": 4,
            })])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, draft)])

    return create_issue_analysis_agent(FunctionModel(respond))


def scripted_reviewer(*, first="supported", final="supported"):
    runs = []

    async def respond(messages, info):
        if len(messages) == 1:
            runs.append(1)
            return ModelResponse(parts=[ToolCallPart("read_source", {
                "path": "documents.py", "start_line": 1, "end_line": 4,
            })])
        verdict = first if len(runs) == 1 else final
        finding = {"field_path": "hypothesis.preconditions", "problem": "Check an unstated condition.",
                   "citations": [{"path": "documents.py", "start_line": 4, "end_line": 4}]}
        output = {"assessment": verdict, "scope": "component",
                  "findings": [] if verdict == "supported" else [finding],
                  "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
                  "condition_audit": [{"operation": "A resource action may occur",
                                       "required_condition": "The input is usable",
                                       "coverage": "entailed", "basis": "Candidate preconditions cover it.",
                                       "candidate_locator": {"field": "preconditions", "index": 0}}],
                  "limitations": ["No execution evidence was supplied."]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return create_evidence_reviewer(FunctionModel(respond))


def test_supported_ready_is_admitted_with_two_attributable_attempts():
    inputs, analysis = case()
    prompts = []
    result = asyncio.run(run_issue_analysis_sequence(
        inputs, scripted_analyst(analysis, prompts), scripted_reviewer(), BUDGETS))
    assert result.status == "admitted_ready" and result.draft_admitted
    assert [attempt.name for attempt in result.attempts] == ["initial_analysis", "initial_review"]
    assert all(attempt.output is not None and attempt.failure is None for attempt in result.attempts)
    assert all(attempt.usage.requests == 2 and attempt.usage.tool_calls == 1
               and attempt.messages and attempt.elapsed_seconds >= 0 for attempt in result.attempts)
    assert inputs.fixture_id not in prompts[0]


def test_needs_revision_causes_one_fresh_analysis_and_one_final_review():
    inputs, analysis = case()
    prompts = []
    result = asyncio.run(run_issue_analysis_sequence(
        inputs, scripted_analyst(analysis, prompts),
        scripted_reviewer(first="needs_revision", final="supported"), BUDGETS))
    assert result.status == "admitted_ready"
    assert [attempt.name for attempt in result.attempts] == [
        "initial_analysis", "initial_review", "revised_analysis", "final_review",
    ]
    assert [attempt.usage.tool_calls for attempt in result.attempts] == [1, 1, 1, 1]
    assert len(prompts) == 2 and "Review findings:" in prompts[1]
    assert "Read relevant saved source again" in prompts[1]
    assert inputs.fixture_id not in prompts[1]
    assert analysis.citations[0].quote not in prompts[1]


def test_final_needs_revision_stops_without_another_repair():
    inputs, analysis = case()
    result = asyncio.run(run_issue_analysis_sequence(
        inputs, scripted_analyst(analysis, []),
        scripted_reviewer(first="needs_revision", final="needs_revision"), BUDGETS))
    assert result.status == "blocked" and not result.draft_admitted
    assert len(result.attempts) == 4
    assert result.review.assessment == "needs_revision"


def test_insufficient_evidence_stops_before_revision():
    inputs, analysis = case()
    result = asyncio.run(run_issue_analysis_sequence(
        inputs, scripted_analyst(analysis, []),
        scripted_reviewer(first="insufficient_evidence"), BUDGETS))
    assert result.status == "blocked" and len(result.attempts) == 2


def test_supported_missing_information_never_admits_drafting():
    inputs, analysis = case("missing_source")
    analyst_draft = analysis.model_dump(mode="json", exclude={"citations": {"__all__": {"quote"}}})
    analyst = create_issue_analysis_agent(TestModel(call_tools=[], custom_output_args=analyst_draft))
    reviewer = create_evidence_reviewer(TestModel(call_tools=[], custom_output_args={
        "assessment": "supported", "scope": "component", "findings": [], "citations": [],
        "condition_audit": [],
        "limitations": ["The source inventory is empty."],
    }))
    result = asyncio.run(run_issue_analysis_sequence(inputs, analyst, reviewer, BUDGETS))
    assert result.status == "supported_missing_information" and not result.draft_admitted
    assert len(result.attempts) == 2 and all(attempt.usage.tool_calls == 0 for attempt in result.attempts)


def test_failed_call_retains_partial_usage_messages_and_stops():
    inputs, analysis = case()

    async def fail(messages, info):
        raise RuntimeError("scripted reviewer unavailable")

    result = asyncio.run(run_issue_analysis_sequence(
        inputs, scripted_analyst(analysis, []), create_evidence_reviewer(FunctionModel(fail)), BUDGETS))
    assert result.status == "blocked" and len(result.attempts) == 2
    assert result.attempts[0].output == analysis
    assert isinstance(result.attempts[1].failure, RuntimeError)
    assert result.attempts[1].output is None and result.attempts[1].messages


def test_cancellation_propagates_with_partial_attempts():
    inputs, analysis = case()

    async def cancel(messages, info):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError) as raised:
        asyncio.run(run_issue_analysis_sequence(
            inputs, scripted_analyst(analysis, []),
            create_evidence_reviewer(FunctionModel(cancel)), BUDGETS))
    attempts = raised.value.sequence_attempts
    assert [attempt.name for attempt in attempts] == ["initial_analysis", "initial_review"]
    assert isinstance(attempts[-1].failure, asyncio.CancelledError)


@pytest.mark.parametrize("field", [
    "request_limit", "tool_calls_limit", "total_tokens_limit", "response_tokens_limit",
])
@pytest.mark.parametrize("bad", [True, 1.5, "3", float("inf"), float("nan")])
def test_operator_count_budgets_reject_nonintegers(field, bad):
    values = BUDGETS.analyst.model_dump() | {field: bad}
    with pytest.raises(ValidationError):
        StageBudget.model_validate(values)


@pytest.mark.parametrize("bad", [True, "5", float("inf"), float("nan"), 0, -1])
def test_operator_timeout_rejects_nonfinite_or_invalid_values(bad):
    with pytest.raises(ValidationError):
        StageBudget.model_validate(BUDGETS.analyst.model_dump() | {"timeout_seconds": bad})


def test_zero_tool_budget_is_valid_and_false_admission_is_fail_closed():
    zero = StageBudget.model_validate(BUDGETS.analyst.model_dump() | {"tool_calls_limit": 0})
    assert zero.usage_limits().tool_calls_limit == 0
    _, missing = case("missing_source")
    fabricated = SequenceResult(status="admitted_ready", analysis=missing, review=None, attempts=())
    assert not fabricated.draft_admitted
