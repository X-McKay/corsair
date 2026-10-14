"""SPEC-0035 assessment dataset: native round-trip, inputs-only task, scripted plumbing and evaluator sensitivity."""
import asyncio

import pytest
from pydantic_ai import models

from corsair.agents.evidence_assessment import assessment_prompt
from corsair.core.disposition import Disposition
from evals.cases import load_set
from evals.evidence_assessment.evaluate import (SPLITS, SUITE, EvaluationBudget, dataset, evaluate, load, passed,
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


def test_dataset_round_trips_through_the_typed_contracts():
    loaded = {case.name: case for case in load().cases}
    for split in SPLITS:
        for frozen in load_set(SUITE, split):
            case = loaded[frozen.name]
            assert case.inputs.model_dump(mode="json") == frozen.input, frozen.key
            assert case.metadata.model_dump(mode="json", exclude_defaults=True) == {
                key: value for key, value in frozen.oracle.items() if value not in (None, [], ())}, frozen.key


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


def test_verified_claim_citing_only_junit_is_refused_by_the_stage_and_recorded(tmp_path):
    # The stage's output function (SPEC-0030, witness rule) refuses it before the evaluator sees an output.
    report = run(tmp_path, ("true_pair",), true_pair={"cite_witness": False})
    assert not report.cases and [failure.name for failure in report.failures] == ["true_pair"]
    assert not passed(report)


@pytest.mark.parametrize('revision', ['baseline', 'candidate'])
def test_witness_grounding_evaluator_detects_uncited_repeat(tmp_path, revision):
    from types import SimpleNamespace
    from evals.evidence_assessment.evaluate import ScoredAssessment

    # Development inputs only; add an equivalent repeat without changing the frozen corpus.
    case = next(case for case in dataset('development').cases if case.name == 'true_pair')
    report = run(tmp_path, ('true_pair',))
    output = report.cases[0].output
    runs = getattr(case.inputs.evidence, revision)
    witness = next(item for item in case.inputs.items if item.kind == 'witness' and item.revision == revision)
    repeat = witness.model_copy(update={'item_id': witness.item_id + '-repeat', 'run': 1})
    inputs = case.inputs.model_copy(update={
        'evidence': case.inputs.evidence.model_copy(update={revision: runs + runs}),
        'items': case.inputs.items + (repeat,)})
    oracle = case.metadata.model_copy(update={'witness_items': case.metadata.witness_items | {
        revision: case.metadata.witness_items[revision] + (repeat.item_id,)}})
    ctx = SimpleNamespace(inputs=inputs, output=output, metadata=oracle)
    assert not ScoredAssessment().evaluate(ctx)['witness_grounded']
    citation = next(c for observation in (*output.application_observations, output.interpretation)
                    for c in observation.citations if c.item_id == witness.item_id)
    ctx.output = output.model_copy(update={'interpretation': output.interpretation.model_copy(update={
        'citations': output.interpretation.citations + (citation.model_copy(update={'item_id': repeat.item_id}),)})})
    assert ScoredAssessment().evaluate(ctx)['witness_grounded']
