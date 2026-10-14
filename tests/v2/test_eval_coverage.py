"""Regression coverage for operational failures versus conditional semantic quality."""
import asyncio
from dataclasses import replace
import json

import pytest

from evals import agent_summary
from evals.agent_eval import evaluate
from test_agent_eval import _root, _spec


@pytest.mark.parametrize(("mode", "set_name"), [("scripted", "dev"), ("live", "other")])
def test_out_of_scope_policy_cannot_pass(tmp_path, mode, set_name):
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: 1\napplies_to: {mode: live, sets: [dev]}\n"
                      "thresholds: {accuracy: {correctness: {min: 1.0}}}\n")
    result = agent_summary.apply_policy({"mode": mode, "set": set_name}, policy)
    assert result["in_scope"] is False and result["status"] == "not_applicable" and result["entries"] == {}


def _summary(evidence):
    return agent_summary.summarize(evidence, agent="builder", set_name="dev", language=None, mode="scripted",
                                   run="r", command={})


def test_native_runner_task_failure_keeps_quality_conditional_and_completion_visible(tmp_path):
    spec = _spec(_root(tmp_path))

    async def run(case, model, workdir):
        if case.language == "java":
            raise RuntimeError("fixture task failure")
        return await spec.run(case, model, workdir)

    evidence = tmp_path / "evidence"
    assert asyncio.run(evaluate(replace(spec, run=run), evidence, "dev")) is False
    summary = _summary(evidence)
    overall = summary["rollups"]["all"]
    assert overall["dimensions"]["correctness"] == {"passed": 1, "total": 1}
    assert overall["completion"] == {"attempted": 2, "completed": 1, "task_failures": 1,
                                      "evaluator_failures": 0, "unknown_failures": 0, "rate": 0.5}
    assert summary["rollups"]["by_language"]["java"]["completion"]["rate"] == 0
    policy = tmp_path / "policy.yaml"
    policy.write_text("hard_gates: {completion_rate: 1.0, evaluator_failures: 0}\n")
    result = agent_summary.apply_policy(summary, policy)
    assert result["status"] == "fail" and result["entries"]["hard_gates.completion_rate"]["status"] == "fail"
    assert "conditional on evaluated attempts" in agent_summary.compare(summary, None, None)


def test_evaluator_failure_is_not_a_task_failure(tmp_path):
    spec = _spec(_root(tmp_path))

    def broken_check(case, attempt):
        raise ValueError("fixture evaluator defect")

    evidence = tmp_path / "evidence"
    assert asyncio.run(evaluate(replace(spec, check=broken_check), evidence, "dev")) is False
    summary = _summary(evidence)
    assert summary["rollups"]["all"]["task_failures"] == 0
    coverage = summary["rollups"]["all"]["completion"]
    assert coverage["completed"] == 2 and coverage["rate"] == 1.0
    assert coverage["task_failures"] == 0 and coverage["evaluator_failures"] == 2
    rows = [json.loads(line) for line in (evidence / "attempts.jsonl").read_text().splitlines()[1:]]
    assert all(row["failure_kind"] == "evaluator" for row in rows)
    policy = tmp_path / "policy.yaml"
    policy.write_text("hard_gates: {completion_rate: 1.0, evaluator_failures: 0}\n")
    assert agent_summary.apply_policy(summary, policy)["entries"]["hard_gates.evaluator_failures"]["status"] == "fail"


def test_historical_unattributed_failure_keeps_completion_unknown(tmp_path):
    row = {"case": "old", "dimensions": {}, "passed": False, "failure": "unknown old error", "assertions": {}}
    overall = agent_summary.rollup([row])
    assert overall["completion"]["completed"] is None and overall["completion"]["rate"] is None
    policy = tmp_path / "policy.yaml"
    policy.write_text("hard_gates: {completion_rate: 1.0, evaluator_failures: 0}\n")
    summary = {"set": "dev", "mode": "scripted", "rollups": {"all": overall}}
    assert agent_summary.apply_policy(summary, policy)["status"] == "unknown"


def test_empty_attempts_have_unknown_completion():
    assert agent_summary.rollup([])["completion"]["rate"] is None


@pytest.mark.parametrize("legacy", [True, False])
def test_compare_preserves_baseline_completion_unknown_without_backfill(tmp_path, legacy):
    from copy import deepcopy

    evidence = tmp_path / "evidence"
    assert asyncio.run(evaluate(_spec(_root(tmp_path)), evidence, "dev")) is False  # Java intentionally misanswers
    current = _summary(evidence)
    assert current["rollups"]["all"]["clean_attempts"] == 1
    assert current["rollups"]["all"]["completion"]["completed"] == 2
    reference = deepcopy(current)
    reference["reference_kind"] = "committed_baseline"
    if legacy:
        reference["rollups"]["all"].pop("completion")
    saved = deepcopy(reference)
    report = agent_summary.compare(current, reference, "baseline")
    assert "Task completion: 2/2" in report
    if legacy:
        assert "Reference task completion: unknown" in report
        assert "Reference task completion: 2/2" not in report
    else:
        assert "Reference task completion: 2/2" in report
    assert reference == saved  # comparisons must not regenerate a committed historical baseline
