"""SDK contract checks; these are not native finding-specific validation tests."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis import (
    FixtureDependencies, IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent, fixture_prompt,
)
from evals.issue_analysis.evaluate import scripted_model

FIXTURES = Path(__file__).resolve().parents[2] / "evals/issue_analysis"


@pytest.fixture(autouse=True)
def no_provider_requests():
    with models.override_allow_model_requests(False):
        yield


def load_case(name="path_traversal"):
    inputs = IssueAnalysisInput.model_validate_json((FIXTURES / "fixtures" / f"{name}.json").read_text())
    oracle = json.loads((FIXTURES / "oracles.json").read_text())["cases"][name]
    return inputs, IssueAnalysis.model_validate(oracle)


def run(agent, inputs, *, request_limit=3, tool_limit=1):
    return agent.run_sync(fixture_prompt(inputs), deps=FixtureDependencies(inputs),
                          usage_limits=UsageLimits(request_limit=request_limit, tool_calls_limit=tool_limit))


def test_native_function_model_reads_cited_source_and_override_restores_model():
    inputs, expected = load_case()
    original = TestModel(call_tools=[])
    agent = create_issue_analysis_agent(original)
    with agent.override(model=scripted_model(expected)):
        result = run(agent, inputs)
    assert result.output == expected
    assert result.usage.requests == 2
    assert result.usage.tool_calls == 1
    assert agent.model is original
    # Neither source content nor the oracle is included in the initial user prompt.
    prompt = fixture_prompt(inputs)
    assert inputs.source_files[0].content not in prompt
    assert expected.hypothesis.observable_effect not in prompt


def test_native_test_model_returns_explicit_missing_facts_without_tools():
    inputs, expected = load_case("missing_source")
    result = run(create_issue_analysis_agent(TestModel(call_tools=[], custom_output_args=expected.model_dump(mode="json"))), inputs)
    assert result.output == expected
    assert result.usage.tool_calls == 0


@pytest.mark.parametrize("path", [".", "../secret", "/etc/passwd", "a/../secret", "a\\secret", "./documents.py", "documents.py\n", "missing.py"])
def test_confined_fixture_read_refuses_unlisted_or_noncanonical_paths(path):
    inputs, _ = load_case()
    with pytest.raises(ValueError):
        FixtureDependencies(inputs).read_source(path, 1, 1)


@pytest.mark.parametrize("start,end", [(0, 1), (2, 1), (1, 5)])
def test_fixture_read_refuses_invalid_ranges(start, end):
    inputs, _ = load_case()
    with pytest.raises(ValueError):
        FixtureDependencies(inputs).read_source("documents.py", start, end)


@pytest.mark.parametrize("mutation", ["quote", "scope", "unread", "extra_verdict"])
def test_native_output_validation_rejects_unfounded_output(mutation):
    inputs, expected = load_case()
    output = expected.model_dump(mode="json")
    if mutation == "quote":
        output["citations"][0]["quote"] = "invented source"
    elif mutation == "scope":
        output["scope"] = "application_path"
    elif mutation == "extra_verdict":
        output["fix"] = "verified"
    if mutation == "unread":
        model = TestModel(call_tools=[], custom_output_args=output)
    else:
        response = deepcopy(output)
        async def respond(messages, info):
            if len(messages) == 1:
                return ModelResponse(parts=[ToolCallPart("read_source", {"path": "documents.py", "start_line": 1, "end_line": 4})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, response)])
        model = FunctionModel(respond)
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_analysis_agent(model, output_retries=0), inputs)


def test_native_request_and_tool_limits_stop_before_next_operation():
    inputs, output = load_case()
    with pytest.raises(UsageLimitExceeded):
        run(create_issue_analysis_agent(scripted_model(output)), inputs, request_limit=1)
    with pytest.raises(UsageLimitExceeded):
        run(create_issue_analysis_agent(scripted_model(output)), inputs, tool_limit=0)
    with pytest.raises(UsageLimitExceeded):
        create_issue_analysis_agent(scripted_model(output)).run_sync(
            fixture_prompt(inputs), deps=FixtureDependencies(inputs),
            usage_limits=UsageLimits(output_tokens_limit=1))


def test_model_failure_is_preserved_and_explicit_model_is_required():
    inputs, _ = load_case()
    async def unavailable(messages, info):
        raise RuntimeError("scripted model response unavailable")
    with pytest.raises(RuntimeError, match="scripted model response unavailable"):
        run(create_issue_analysis_agent(FunctionModel(unavailable)), inputs)
    with pytest.raises(TypeError, match="explicit PydanticAI Model"):
        create_issue_analysis_agent(None)


def test_native_tool_refusal_preserves_contract_failure():
    inputs, output = load_case()
    with pytest.raises(UnexpectedModelBehavior, match="read_source"):
        run(create_issue_analysis_agent(scripted_model(output, path="../credentials")), inputs)


def test_prior_run_source_reads_do_not_authorize_current_citations():
    prior_inputs, output = load_case()
    prior = run(create_issue_analysis_agent(scripted_model(output)), prior_inputs)
    current_inputs = prior_inputs.model_copy(update={"fixture_id": "distinct-new-fixture"})
    agent = create_issue_analysis_agent(TestModel(call_tools=[], custom_output_args=output.model_dump(mode="json")),
                                         output_retries=0)
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync(fixture_prompt(current_inputs), deps=FixtureDependencies(current_inputs),
                       message_history=prior.all_messages(),
                       usage_limits=UsageLimits(request_limit=1, tool_calls_limit=0))


def test_evaluation_cli_refuses_existing_attempt_without_running(monkeypatch, tmp_path):
    from evals.issue_analysis import evaluate
    destination = tmp_path / "original.json"
    destination.write_text("original report")
    monkeypatch.setattr("sys.argv", ["evaluate", "--report", str(destination)])
    def unexpected_evaluation():
        pytest.fail("existing output must be refused before evaluation")
    monkeypatch.setattr(evaluate, "evaluate_fixture", unexpected_evaluation)
    with pytest.raises(SystemExit) as exc:
        evaluate.main()
    assert exc.value.code == 2
    assert destination.read_text() == "original report"


def test_ready_hypothesis_requires_citations_and_cannot_carry_missing_facts():
    _, output = load_case()
    for changed in ({"citations": []}, {"hypothesis": None}, {"missing_facts": ["entry point unknown"]}):
        with pytest.raises(ValidationError):
            IssueAnalysis.model_validate(output.model_dump() | changed)


def test_fixture_contract_bounds_unique_source_and_read_size():
    inputs, _ = load_case()
    with pytest.raises(ValidationError):
        IssueAnalysisInput.model_validate(inputs.model_dump() | {"source_files": [inputs.source_files[0], inputs.source_files[0]]})
    many_lines = inputs.model_dump() | {"source_files": [{"path": "many.py", "content": "x\n" * 81}]}
    with pytest.raises(ValueError, match="80 lines"):
        FixtureDependencies(IssueAnalysisInput.model_validate(many_lines)).read_source("many.py", 1, 81)


def test_native_evals_repeat_with_local_span_coverage():
    from evals.issue_analysis.evaluate import evaluate_fixture
    report = asyncio.run(evaluate_fixture())
    assert len(report.cases) == 6
    assert not report.failures and not report.report_evaluator_failures
    for case in report.cases:
        assert not case.evaluator_failures
        assert case.assertions and all(assertion.value for assertion in case.assertions.values())
        assert case.trace_id and case.span_id
        assert case.task_duration >= 0
        assert case.metrics["native_requests"] in (1, 2)
        assert case.attributes["observed_native_tool_calls"] in (0, 1)
        assert case.attributes["input_digest"] == case.inputs.input_digest
    groups = report.case_groups()
    assert len(groups) == 3
    assert all(group.runs[0].output == group.runs[1].output for group in groups)


def test_native_evals_missing_agent_spans_fail_coverage():
    from pydantic_evals import Case, Dataset
    from pydantic_evals.evaluators import HasMatchingSpan
    async def uninstrumented_task(value):
        return value
    report = asyncio.run(Dataset(name="missing-agent-spans", cases=[Case(inputs="fixture")],
                                 evaluators=[HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}})])
                         .evaluate(uninstrumented_task, progress=False))
    assert not report.cases[0].assertions["HasMatchingSpan"].value
