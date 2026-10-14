from __future__ import annotations

import asyncio
import csv
import json
import stat
from pathlib import Path

import pytest
from pydantic_evals import Case, Dataset

from corsair.v2.contracts import (
    AnalysisInput,
    AnalysisResult,
    Budget,
    Citation,
    ModelProfile,
    OperatorConfig,
    SandboxProfile,
    SourceAssessment,
    StageMetrics,
)
from corsair.v2.evaluation import evaluate_dataset, evaluator_policy_identity
from corsair.v2.reports import compare_reports, export_report, promote_baseline


def _config(tmp_path: Path) -> OperatorConfig:
    policy_path = tmp_path / "operator-policy.yaml"
    policy_path.write_text("version: test-policy\n", encoding="utf-8")
    return OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
        sandbox=SandboxProfile(image="example@sha256:" + "a" * 64, policy_path=str(policy_path)), budget=Budget(request_limit=2, tool_calls_limit=2))


def _dataset(kind: str = "upstream") -> Dataset:
    inputs = AnalysisInput(files={"source/a.py": "x = 1\n"}, language="python")
    return Dataset[AnalysisInput, str, dict](name="report-dataset", cases=[Case(name="case", inputs=inputs,
        expected_output="vulnerable", metadata={"input_kind": "source", "language": "python", "framework": "none",
        "cwe": ["CWE-22"], "agent": "analysis", "model": "test", "source_digest": "a" * 64,
        "suite_id": "suite", "suite_kind": kind, "split": "public-dev", "task_mode": "source"})])


def _unknown_usage_stage() -> StageMetrics:
    return StageMetrics(role="analysis", model="test", latency_seconds=0.1, status="completed",
        field_availability={"requests": "unknown", "tool_calls": "unknown", "input_tokens": "unknown",
                            "output_tokens": "unknown"})


def _result(answer: str, stage: StageMetrics | None = None) -> AnalysisResult:
    return AnalysisResult(assessment=SourceAssessment(prediction=answer, rationale="grounded fixture assessment",
        citations=(Citation(path="source/a.py", start_line=1, end_line=1),)), metrics=stage or _unknown_usage_stage())


def _report(tmp_path: Path, answer: str = "vulnerable", *, repeat: int = 1):
    async def task(_: AnalysisInput) -> AnalysisResult:
        return _result(answer)
    return asyncio.run(evaluate_dataset(_dataset(), _config(tmp_path), tmp_path, repeat=repeat, task=task))


def _meta(**updates):
    value = {"dataset_digest": "d" * 64, "evaluator_policy": evaluator_policy_identity(), "execution_profile": "local-profile",
             "agent": "baseline", "model": "model-a", "prompt": "prompt-a"}
    value.update(updates)
    return value


def test_export_preserves_native_cases_complete_summary_and_dimension_rollups(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert report.cases[0].assertions["EqualsExpected"].value is True
    result = export_report(report, tmp_path / "out", _meta())
    document = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    markdown = Path(result["summary_markdown"]).read_text(encoding="utf-8")

    assert Path(result["records"]).is_file() and Path(result["human"]).is_file()
    assert document["summary"]["all_attempts"] == 1
    assert document["summary"]["correct"] == 1
    assert document["records"][0]["metrics"]["input_tokens"] is None
    assert document["summary"]["input_tokens"] is None
    assert document["summary"]["input_tokens_known_attempts"] == 0
    assert document["summary"]["input_tokens_unknown_attempts"] == 1
    assert document["immutable_identity"]["dataset_digest"] == "d" * 64
    assert set(document["by_dimension"]) == {"language", "framework", "cwe", "agent", "model"}
    assert document["by_dimension"]["language"]["strata"][0]["language"] == "python"
    assert "Source-only classifications are not executed security verdicts." in markdown
    assert "unknown (0/1 known)" in markdown


def test_export_is_private_new_only_and_csv_formula_safe(tmp_path: Path) -> None:
    report = _report(tmp_path)
    report.cases[0].expected_output = "=FORMULA()"
    result = export_report(report, tmp_path / "out", _meta())

    output_dir = tmp_path / "out"
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    for key in ("report", "records", "strata", "human", "summary_markdown"):
        assert stat.S_IMODE(Path(result[key]).stat().st_mode) == 0o600
    with Path(result["records"]).open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    assert row["expected_output"] == "'=FORMULA()"
    with pytest.raises(FileExistsError):
        export_report(report, output_dir, _meta())


def test_export_failure_attempt_does_not_fabricate_status_truth_or_usage(tmp_path: Path) -> None:
    async def task(_: AnalysisInput) -> AnalysisResult:
        raise RuntimeError("fixture transport failure")

    report = asyncio.run(evaluate_dataset(_dataset(), _config(tmp_path), tmp_path, task=task))
    result = export_report(report, tmp_path / "out", _meta())
    document = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    row = document["records"][0]

    assert row["row_kind"] == "task_failure"
    assert row["expected_output"] == "vulnerable"
    assert row["promotion_eligible"] is True and row["generated"] is False
    assert row["outcome"] == {"terminal_status": None, "correct": None, "denominator_class": "task_error"}
    assert row["metrics"]["input_tokens"] is None
    assert "assertions" not in row and "scores" not in row and "labels" not in row
    assert document["immutable_identity"]["evaluator_policy"] == evaluator_policy_identity()
    assert document["summary"]["all_attempts"] == 1
    assert document["summary"]["task_errors"] == 1
    assert document["summary"]["scored"] == 0
    assert document["summary"]["false_negative"] == 0


def test_export_rejects_caller_evaluator_policy_conflicting_with_native_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="native evaluator_policy"):
        export_report(_report(tmp_path), tmp_path / "out", _meta(evaluator_policy="operator-policy-v1"))


def test_language_rollup_has_meaningful_two_class_scores_and_known_usage(tmp_path: Path) -> None:
    cases = []
    for name, expected in (("tp", "vulnerable"), ("fn", "vulnerable"), ("tn", "safe_in_scope"), ("fp", "safe_in_scope")):
        cases.append(Case(name=name, inputs=AnalysisInput(concern=name, files={"source/a.py": "x = 1\n"}), expected_output=expected,
            metadata={"input_kind": "source", "language": "python|fixture\nv1", "framework": "pytest", "cwe": ["CWE-22"],
                      "agent": "analysis", "model": "test", "source_digest": name * 64, "suite_id": "suite",
                      "suite_kind": "upstream", "split": "public-dev", "task_mode": "source"}))
    dataset = Dataset[AnalysisInput, str, dict](name="metric-fixtures", cases=cases)
    outcomes = {"tp": "vulnerable", "fn": "safe_in_scope", "tn": "safe_in_scope", "fp": "vulnerable"}
    stage = StageMetrics(role="analysis", model="test", latency_seconds=0.2, requests=1, tool_calls=0,
        input_tokens=10, output_tokens=5, status="completed", field_availability={"requests": "reported",
        "tool_calls": "reported_zero", "input_tokens": "reported", "output_tokens": "reported"})

    async def task(inputs: AnalysisInput) -> AnalysisResult:
        return _result(outcomes[inputs.concern], stage)

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, task=task))
    result = export_report(report, tmp_path / "out", _meta())
    document = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    row = document["by_dimension"]["language"]["strata"][0]
    markdown = Path(result["summary_markdown"]).read_text(encoding="utf-8")

    assert row["all_attempts"] == 4 and row["scored"] == 4 and row["correct"] == 2
    assert (row["true_positive"], row["true_negative"], row["false_positive"], row["false_negative"]) == (1, 1, 1, 1)
    assert row["precision"] == row["recall"] == row["f1"] == 0.5
    assert row["input_tokens"] == row["input_tokens_known_sum"] == 40
    assert row["output_tokens"] == row["output_tokens_known_sum"] == 20
    assert row["input_tokens_known_attempts"] == 4 and row["input_tokens_unknown_attempts"] == 0
    assert "python\\|fixture<br>v1" in markdown


def test_comparison_records_experiment_identity_deltas_and_visible_pair(tmp_path: Path) -> None:
    baseline = export_report(_report(tmp_path), tmp_path / "base", _meta())
    candidate_report = _report(tmp_path, "unknown")
    candidate_report.experiment_metadata["config_identity"] = {"changed": True}
    candidate_report.experiment_metadata["build_identity"] = {"code_sha256": "changed"}
    candidate_report.experiment_metadata["native_profile_hashes"] = {"analysis": "changed"}
    candidate = export_report(candidate_report, tmp_path / "candidate",
                              _meta(agent="candidate", model="model-b", prompt="prompt-b"))
    result = compare_reports(Path(baseline["report"]), Path(candidate["report"]), tmp_path / "comparison")
    payload = json.loads(Path(result["comparison"]).read_text(encoding="utf-8"))
    assert result["paired_rows"] == 1
    assert payload["experiment_deltas"]["model"] == {"baseline": "model-a", "candidate": "model-b"}
    assert payload["experiment_deltas"]["config_identity"]["candidate"] == {"changed": True}
    assert payload["experiment_deltas"]["config_identity"]["baseline"] != {"changed": True}
    assert "build_identity" in payload["experiment_deltas"]
    assert "native_profile_hashes" in payload["experiment_deltas"]
    assert payload["paired"][0]["candidate_status"] == "unknown"


def test_comparison_of_one_and_two_trials_shows_missing_attempt_not_dataset_difference(tmp_path: Path) -> None:
    baseline = export_report(_report(tmp_path, repeat=1), tmp_path / "base", _meta())
    candidate = export_report(_report(tmp_path, repeat=2), tmp_path / "candidate", _meta())
    result = compare_reports(Path(baseline["report"]), Path(candidate["report"]), tmp_path / "comparison")
    payload = json.loads(Path(result["comparison"]).read_text(encoding="utf-8"))

    assert result["paired_rows"] == 2 and result["missing_rows"] == 1
    assert payload["immutable_identity"]["cases"] == json.loads(Path(baseline["report"]).read_text())["immutable_identity"]["cases"]
    assert [row for row in payload["paired"] if row["trial"] == 2][0]["missing_side"] == "baseline"


@pytest.mark.parametrize("change", ("source", "truth", "mode"))
def test_repeated_trials_reject_changed_frozen_case_identity(tmp_path: Path, change: str) -> None:
    report = _report(tmp_path, repeat=2)
    if change == "source":
        report.cases[1].metadata = {**report.cases[1].metadata, "source_digest": "b" * 64}
    elif change == "truth":
        report.cases[1].expected_output = "safe_in_scope"
    else:
        report.cases[1].metadata = {**report.cases[1].metadata, "task_mode": "run"}

    with pytest.raises(ValueError, match="Repeated case identity"):
        export_report(report, tmp_path / change, _meta())


def test_comparison_rejects_immutable_profile_difference_and_smoke_upstream_mix(tmp_path: Path) -> None:
    baseline = export_report(_report(tmp_path), tmp_path / "base", _meta())
    changed_profile = export_report(_report(tmp_path), tmp_path / "changed", _meta(execution_profile="other"))
    with pytest.raises(ValueError, match="execution_profile"):
        compare_reports(Path(baseline["report"]), Path(changed_profile["report"]), tmp_path / "cmp")
    smoke_report = _report(tmp_path)
    smoke_report.cases[0].metadata["suite_kind"] = "smoke"
    smoke = export_report(smoke_report, tmp_path / "smoke", _meta())
    with pytest.raises(ValueError, match="smoke"):
        compare_reports(Path(baseline["report"]), Path(smoke["report"]), tmp_path / "cmp2")


@pytest.mark.parametrize("field, value", (("promotion_eligible", False), ("generated", True)))
def test_promote_rejects_explicitly_ineligible_all_failure_report(tmp_path: Path, field: str, value: bool) -> None:
    async def task(_: AnalysisInput) -> AnalysisResult:
        raise RuntimeError("fixture transport failure")

    report = asyncio.run(evaluate_dataset(_dataset(), _config(tmp_path), tmp_path, task=task))
    report.failures[0].metadata[field] = value
    exported = export_report(report, tmp_path / field, _meta())
    with pytest.raises(ValueError, match="ineligible"):
        promote_baseline(Path(exported["report"]), tmp_path / "baselines")


def test_promote_requires_immutable_non_smoke_evaluation_reference(tmp_path: Path) -> None:
    upstream = export_report(_report(tmp_path), tmp_path / "upstream", _meta())
    promoted = promote_baseline(Path(upstream["report"]), tmp_path / "baselines")
    assert Path(promoted["reference"]).is_file()
    smoke_report = _report(tmp_path)
    smoke_report.cases[0].metadata["suite_kind"] = "smoke"
    smoke = export_report(smoke_report, tmp_path / "smoke", _meta())
    with pytest.raises(ValueError, match="smoke"):
        promote_baseline(Path(smoke["report"]), tmp_path / "baselines")
