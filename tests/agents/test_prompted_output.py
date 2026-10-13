"""Prompted final answers: one JSON object kept, two refused, reasoning with no output named (gap 10, PLAN-0082)."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry, capture_run_messages, models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.usage import UsageLimits

from corsair.agents.environment.agent import create_environment_agent
from corsair.agents.evidence_assessment.agent import create_evidence_assessment_agent
from corsair.agents.issue_identification import create_issue_identification_agent
from corsair.agents.issue_identification.agent import create_repository_identification_agent
from corsair.agents.prompted_output import NO_OUTPUT, PROSE_KEY, keep_trailing_object, trailing_object
from corsair.agents.test_authoring.agent import create_test_authoring_agent
from corsair.agents.test_planning import PlanningDependencies, TestPlanningInput, create_test_planning_agent
from corsair.agents.test_planning.prompts import planning_prompt
from corsair.composition.direct import output_refusals

RECORD = json.loads((Path(__file__).parent / "recorded" / "corpus-pathtraversal-2-planning.json").read_text())
PROMPTED = OpenAIModelProfile(default_structured_output_mode="prompted")


def planning_inputs():
    data = json.loads(RECORD["prompt"].split("\nSaved source inventory")[0])
    lines = {path.split(":", 1)[1]: [line["text"] for line in read["lines"]] for path, read in RECORD["reads"].items()}
    data["source_files"] = [{"path": path, "content": "\n".join(text) + "\n"} for path, text in lines.items()]
    target = data["identification"]["target"]["source"]
    target["quote"] = "\n".join(lines["app.py"][target["start_line"] - 1:target["end_line"]])
    return TestPlanningInput.model_validate(data)


def repository_deps():
    from tests.agents.test_repository_source import RepositoryDependencies, inputs, tree
    return RepositoryDependencies(inputs(), tree())


def authoring_deps():
    from tests.agents.test_test_authoring import AuthoringDependencies, case, runner
    return AuthoringDependencies(case().inputs.inputs, runner())


# Every chain stage's agent; deps only where its tools read them before the first request.
STAGES = {create_environment_agent: lambda: None, create_issue_identification_agent: lambda: None,
          create_repository_identification_agent: repository_deps,
          create_test_planning_agent: lambda: PlanningDependencies(planning_inputs()),
          create_test_authoring_agent: authoring_deps, create_evidence_assessment_agent: lambda: None}


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


@pytest.mark.parametrize(("text", "dropped"), [
    ('Done.\n\n{"a": {"b": 1}}', "Done."),
    ('{"a": "}"} That is the answer.', "That is the answer."),
    ('Here it is:\n```json\n{"a": 1}\n```\nThanks.', "Here it is:\n```json\n\n```\nThanks."),
    ('{"a": 1}', ""),
])
def test_exactly_one_complete_object_is_kept_with_the_rest_dropped(text, dropped):
    assert trailing_object(text) == (dropped, '{"a": "}"}' if '"}"' in text else text[text.index("{"):text.rindex("}") + 1])


@pytest.mark.parametrize("text", ["No object here", 'Truncated {"a": [1, 2', 'Two {"a": 1} and {"b": 2}'])
def test_no_object_or_several_is_not_kept(text):
    assert trailing_object(text) is None


def hook(*parts):
    return asyncio.run(keep_trailing_object(None, request_context=None, response=ModelResponse(parts=list(parts))))


def test_two_objects_are_refused_not_resolved_to_either():
    with pytest.raises(ModelRetry, match="2 complete JSON objects"):
        hook(TextPart('Draft: {"plan": 1}\nFinal:\n```json\n{"plan": 2}\n```'))


def test_reasoning_with_no_output_is_its_own_refusal_and_tool_calls_pass_untouched():
    with pytest.raises(ModelRetry, match=NO_OUTPUT.format(9008)):
        hook(ThinkingPart("x" * 9008), TextPart("  "))
    call = ModelResponse(parts=[TextPart('{"a": 1} {"b": 2}'), ToolCallPart("read_source", {"path": "app.py"})])
    assert asyncio.run(keep_trailing_object(None, request_context=None, response=call)) is call


def test_kept_object_records_the_dropped_text():
    response = hook(ThinkingPart("why"), TextPart('Answer follows.\n{"a": 1}'))
    assert [type(p) for p in response.parts] == [ThinkingPart, TextPart] and response.parts[-1].content == '{"a": 1}'
    assert response.provider_details[PROSE_KEY] == "Answer follows."


@pytest.mark.parametrize("factory", STAGES, ids=lambda f: f.__name__)
def test_every_chain_stage_names_reasoning_with_no_output(factory):
    deps = STAGES[factory]()
    async def respond(messages, info):
        return ModelResponse(parts=[ThinkingPart("r" * 120)])
    with capture_run_messages() as messages, pytest.raises(UnexpectedModelBehavior) as failure:
        factory(FunctionModel(respond, profile=PROMPTED), output_retries=1).run_sync("answer", deps=deps)
    assert str(failure.value.__cause__).startswith(NO_OUTPUT.format(120))
    assert output_refusals(tuple(messages)) == (NO_OUTPUT.format(120) + "; return the final JSON object as text",)


def planning_replay(edit=lambda text: text):
    """The corpus rerun's planner answers, replayed in order against the real planner and its contract."""
    inputs = planning_inputs()

    def part(recorded):
        if recorded["part_kind"] == "thinking":
            return ThinkingPart(recorded["content"].ljust(recorded["length"], "."))
        if recorded["part_kind"] == "text":
            return TextPart(edit(recorded["content"]))
        return ToolCallPart(recorded["tool_name"], recorded["args"])
    responses = [ModelResponse(parts=[part(p) for p in response]) for response in RECORD["responses"]]

    async def respond(messages, info):
        return responses[sum(isinstance(m, ModelResponse) for m in messages)]
    agent = create_test_planning_agent(FunctionModel(respond, profile=PROMPTED), output_retries=1)
    with capture_run_messages() as messages:
        try:
            return agent.run_sync(planning_prompt(inputs), deps=PlanningDependencies(inputs),
                                  usage_limits=UsageLimits(request_limit=8)), tuple(messages)
        except UnexpectedModelBehavior as failure:
            return failure, tuple(messages)


def test_corpus_rerun_planning_stop_names_both_refusals():
    """Recorded corpus rerun: reasoning with no output spent the correction, then the fenced plan had no limitation.

    Before: the stop reason was only "Exceeded maximum output retries (1)". The fenced answer itself parses (PydanticAI
    strips a fence); the contract refused its empty ``limitations``.
    """
    assert RECORD["failure"]["detail"] == "Exceeded maximum output retries (1)"
    failure, messages = planning_replay()
    assert isinstance(failure, UnexpectedModelBehavior)
    assert output_refusals(messages) == (NO_OUTPUT.format(9008) + "; return the final JSON object as text",)
    assert "limitations" in str(failure.__cause__)


def test_corpus_rerun_fenced_plan_parses_and_its_next_refusal_is_the_directory_approved_as_a_test_path():
    """With a limitation stated, the same fenced answer still fails the contract, not the parser: the environment
    stage approved the directory ``tests`` where approved test paths name the files the tests will create."""
    limited = '"limitations": ["Fixtures are created under the module data directory."]'
    failure, messages = planning_replay(lambda text: text.replace('"limitations": []', limited))
    assert isinstance(failure, UnexpectedModelBehavior)
    assert "tests/test_read_doc_control.py is not an approved test path" in str(failure.__cause__)
    assert output_refusals(messages) == (NO_OUTPUT.format(9008) + "; return the final JSON object as text",)
