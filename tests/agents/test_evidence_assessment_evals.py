"""SPEC-0035 assessment dataset: native round-trip, inputs-only task, scripted plumbing and evaluator sensitivity."""
import asyncio

import pytest
from pydantic_ai import models

from corsair.agents.evidence_assessment import assessment_prompt
from corsair.core.disposition import Disposition
from evals.evidence_assessment.evaluate import (CASES, EvaluationBudget, dataset, evaluate, load, passed,
                                                scripted_model)


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def assertions(report, case):
    (result,) = [c for c in report.cases if c.name.startswith(case)]
    return {name: item.value for name, item in result.assertions.items()}


def run(tmp_path, cases, **scripted):
    corpus = {case.name: case for case in dataset().cases}
    models_ = {name: scripted_model(corpus[name].inputs, corpus[name].metadata, **kwargs)
               for name, kwargs in scripted.items()}
    return asyncio.run(evaluate(tmp_path / "evidence", EvaluationBudget(repeat=1), split="all", cases=cases,
                                scripted=models_ or None))


def test_dataset_round_trips_through_the_native_file_format(tmp_path):
    load().to_file(tmp_path / "cases.yaml", schema_path=None)
    assert (tmp_path / "cases.yaml").read_bytes() == CASES.read_bytes()


def test_agent_inputs_carry_no_oracle_or_variant_text():
    for case in load().cases:
        oracle = case.metadata
        visible = assessment_prompt(case.inputs) + "".join(item.content for item in case.inputs.items)
        hidden = (case.name, "vulnerable", "held_out", oracle.split, *([oracle.honest_note] if oracle.honest_note else ()))
        assert not any(text in visible for text in hidden), case.name
        assert set(oracle.required_reads) <= {item.item_id for item in case.inputs.items}


def test_scripted_honest_proposals_pass_every_evaluator_on_every_case(tmp_path):
    report = asyncio.run(evaluate(tmp_path / "evidence", EvaluationBudget(repeat=1), split="all"))
    assert len(report.cases) == len(load().cases) and passed(report)
    assert {"configuration.json", "report.json"} <= {path.name for path in (tmp_path / "evidence").iterdir()}


def test_over_claim_fails_admission_and_calibration_and_weakening_fails_calibration_only(tmp_path):
    report = run(tmp_path, ("candidate_sandbox_denial", "true_pair"),
                 candidate_sandbox_denial={"proposal": Disposition(execution="completed", finding="reproduced",
                                                                   fix="verified")},
                 true_pair={"proposal": Disposition(execution="completed", finding="reproduced", fix="not_verified")})
    over, weak = assertions(report, "candidate_sandbox_denial"), assertions(report, "true_pair")
    assert not over["admitted"] and not over["calibrated"]
    assert not weak["calibrated"] and all(value for name, value in weak.items() if name != "calibrated")


def test_verified_claim_citing_only_junit_is_not_witness_grounded(tmp_path):
    report = run(tmp_path, ("true_pair",), true_pair={"cite_witness": False})
    result = assertions(report, "true_pair")
    assert not result["witness_grounded"] and all(value for name, value in result.items() if name != "witness_grounded")
