"""Eval-only property planner: frozen input reuse and trusted current-run citation binding."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.exceptions import UnexpectedModelBehavior

from corsair.agents.test_planning.dependencies import PlanningDependencies
from corsair.agents.test_planning.prompts import planning_prompt
from evals.test_planning.evaluate import dataset
from evals.test_planning.property_plan import (
    CASES, INSTRUCTIONS, EvaluationBudget, PropertyDraft, create_property_agent, evaluate, passed,
    property_prompt, reference_property,
)
from pydantic import TypeAdapter


@pytest.mark.parametrize("cases", CASES)
def test_property_planner_native_report_reuses_exact_frozen_inputs(tmp_path, cases):
    report = asyncio.run(evaluate(tmp_path / "evidence", EvaluationBudget(repeat=1), cases=cases))
    assert passed(report)
    frozen = {case.name: case.inputs for case in dataset(cases).cases}
    for case in report.cases:
        assert case.inputs == frozen[case.name]
        assert "contract_completion" in case.assertions
        assert case.output.citations
        for citation in case.output.citations:
            source = next(s for s in case.inputs.source_files if s.path == citation.path)
            assert citation.quote == "\n".join(source.content.splitlines()[citation.start_line - 1:citation.end_line])
    config = json.loads((tmp_path / "evidence" / "configuration.json").read_text())
    assert "unqualified" in config["semantic_fidelity"]
    assert len(config["draft_schema_sha256"]) == len(config["output_schema_sha256"]) == 64
    assert "no authoring or execution" in config["qualification"]


def test_property_planner_refuses_unread_citations():
    case = dataset("unit-first").cases[0]
    draft = reference_property(case.inputs, case.metadata)
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"plan": draft})])
    async def run():
        with models.override_allow_model_requests(False):
            return await create_property_agent(FunctionModel(respond), output_retries=0).run(
                property_prompt(case.inputs), deps=PlanningDependencies(case.inputs))
    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        asyncio.run(run())


def test_property_draft_has_no_execution_fields_or_agent_supplied_quotes():
    case = dataset("unit-first").cases[0]
    draft = reference_property(case.inputs, case.metadata)
    TypeAdapter(PropertyDraft).validate_python(draft)
    for field in ("discovery_command", "test_id", "failure_type"):
        with pytest.raises(ValidationError):
            TypeAdapter(PropertyDraft).validate_python(draft | {field: "invented"})
    quoted = dict(draft)
    quoted["citations"] = [dict(draft["citations"][0], quote="agent invented quotation")]
    with pytest.raises(ValidationError):
        TypeAdapter(PropertyDraft).validate_python(quoted)


def test_property_experiment_uses_candidate_task_rendering_and_keeps_generic_roles():
    for cases in CASES:
        for case in dataset(cases).cases:
            assert property_prompt(case.inputs) == planning_prompt(case.inputs)
    assert "one benign control and one exploit probe" in INSTRUCTIONS
    assert "integration evidence" in INSTRUCTIONS
    assert "ordinary behavior the benign" in INSTRUCTIONS
