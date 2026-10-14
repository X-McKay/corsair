"""The whole-chain scorer (evals/e2e/evaluate.py) in scripted mode: real routing, Select and Decide, replayed stages."""
import asyncio
import dataclasses
import json

import pytest

from evals import agent_summary, run as eval_run
from evals.agent_eval import evaluate
from evals.cases import CHAIN, load_set
from evals.e2e import evaluate as chain

CASES = {case.key: case for case in load_set(chain.ROOT, "v2")}


def _rows(evidence):
    return [json.loads(line) for line in (evidence / "attempts.jsonl").read_text().splitlines()[1:]]


def _attempt(case, tmp_path):
    attempt = asyncio.run(chain.run(case, chain.scripted(case), tmp_path))
    return attempt, chain.check(case, attempt)


def test_scripted_set_runs_clean(tmp_path):
    assert asyncio.run(evaluate(chain.SPEC, tmp_path / "evidence", "v2")) is True
    rows = _rows(tmp_path / "evidence")
    assert len(rows) == len(CASES) and all(row["passed"] for row in rows)
    assert all(row["label"] == row["expected_label"] for row in rows)  # the replays follow each oracle's own path
    summary = agent_summary.summarize(tmp_path / "evidence", agent=CHAIN, set_name="v2", language=None,
                                      mode="scripted", run="r", command={})
    found = summary["rollups"]["all"]["dispositions"]
    assert found["runs"] == len(CASES) and found["decisive_correct"] == found["decisive"]
    assert set(summary["rollups"]["by_language"]) == {case.language for case in CASES.values()}
    policy = agent_summary.apply_policy(summary, chain.ROOT / "release-policy.yaml")
    assert policy["policy"] and policy["entries"]["hard_gates.safety_failures"]["status"] == "pass"


def test_language_narrowing(tmp_path):
    suite = eval_run.v2_suite(CHAIN)
    assert suite.module == "evals.e2e.evaluate" and eval_run.narrows_by_language(suite, "v2")
    assert chain.main(chain.SPEC, ["--evidence", str(tmp_path / "evidence"), "--set", "v2",
                                   "--language", "perl"]) == 0
    rows = _rows(tmp_path / "evidence")
    assert rows and {row["language"] for row in rows} == {"perl"}
    assert len(rows) == sum(case.language == "perl" for case in CASES.values())


def test_wrong_recorded_outcome_fails_label(tmp_path):
    case = next(case for case in CASES.values() if case.oracle["expected_rule"] == "R4")
    oracle = json.loads(json.dumps(case.oracle))
    oracle["replay"]["outcomes"]["vulnerable"]["exploit"] = "assertion_failed"  # the PoV did not demonstrate it
    attempt, results = _attempt(dataclasses.replace(case, oracle=oracle), tmp_path)
    assert attempt.output.label.value == "LIKELY_NOT_EXPLOITABLE"
    assert results["label"] is False and results["terminal_reason"] is True and results["contract"] is True


def test_missing_replay_is_an_attributable_error(tmp_path):
    case = next(case for case in CASES.values() if case.oracle["expected_runtime_row"] is not None)
    oracle = {key: value for key, value in case.oracle.items() if key != "replay"}
    attempt, results = _attempt(dataclasses.replace(case, oracle=oracle), tmp_path)
    assert attempt.output.label.value == "ERROR" and attempt.output.terminal_reason.value == "infra_error"
    assert results["label"] is False


def test_oracle_text_in_a_stage_input_fails_safety(tmp_path):
    case = next(case for case in CASES.values() if case.oracle["expected_runtime_row"] is not None)
    attempt, results = _attempt(case, tmp_path)
    assert results["safety"] is True
    attempt.stage_inputs.append(json.dumps({"hint": case.oracle["expected_label"]}))
    assert chain.check(case, attempt)["safety"] is False


def test_live_mode_refuses_without_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(chain.shutil, "which", lambda name: None)
    case = next(iter(CASES.values()))
    with pytest.raises(RuntimeError, match="needs Docker"):
        asyncio.run(chain.run(case, {}, tmp_path))


def test_a_wrong_fix_result_fails_outcome_fields(tmp_path):
    case = next(case for case in CASES.values() if case.oracle.get("expected_fix") == "verified")
    attempt, results = _attempt(case, tmp_path)
    assert results["outcome_fields"]
    attempt = dataclasses.replace(attempt, output=attempt.output.model_copy(update={"fix": "not_verified"}))
    assert chain.check(case, attempt)["outcome_fields"] is False
