from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from corsair.v2.contracts import (
    AnalysisInput,
    AnalysisResult,
    Budget,
    Citation,
    ModelProfile,
    OperatorConfig,
    RunResult,
    SandboxProfile,
    SourceAssessment,
    StageMetrics,
    Verdict,
    digest,
)
from corsair.v2.evaluation import evaluate_dataset, report_summary


def _config(tmp_path: Path) -> OperatorConfig:
    policy_path = tmp_path / "operator-policy.yaml"
    policy_path.write_text("version: test-policy\n", encoding="utf-8")
    return OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
                          sandbox=SandboxProfile(image="example@sha256:" + "a" * 64, policy_path=str(policy_path)),
                          budget=Budget(request_limit=2, tool_calls_limit=3))


def _stage(**updates) -> StageMetrics:
    values = {"role": "analysis", "model": "test", "latency_seconds": 0.1, "requests": 1, "tool_calls": 0,
              "input_tokens": 12, "output_tokens": 4, "status": "completed",
              "field_availability": {"requests": "reported", "tool_calls": "reported_zero",
                  "input_tokens": "reported", "output_tokens": "reported"}}
    values.update(updates)
    return StageMetrics(**values)


def _analysis(prediction: str, inputs: AnalysisInput, *, metrics: StageMetrics | None = None) -> AnalysisResult:
    path = next(iter(inputs.files))
    return AnalysisResult(assessment=SourceAssessment(prediction=prediction, rationale="bounded source evidence",
                          citations=(Citation(path=path, start_line=1, end_line=1),)), metrics=metrics or _stage())


def _metadata(language: str = "python") -> dict:
    return {"input_kind": "source", "language": language, "framework": "none", "cwe": ["CWE-22"],
            "source_digest": "fixture", "suite_kind": "upstream", "split": "public-dev"}


def _source_case() -> Dataset:
    inputs = AnalysisInput(files={"source/a.py": "def f():\n    return 1\n"}, language="python")
    return Dataset[AnalysisInput, str, dict](name="source", cases=[Case(name="a", inputs=inputs,
        expected_output="vulnerable", metadata=_metadata())])


def test_source_runner_uses_native_results_and_preserves_reported_zero(tmp_path: Path) -> None:
    async def task(inputs: AnalysisInput) -> AnalysisResult:
        return _analysis("vulnerable", inputs)

    report = asyncio.run(evaluate_dataset(_source_case(), _config(tmp_path), tmp_path, task=task))
    case = report.cases[0]
    totals, _ = report_summary(report)
    assert case.output == "vulnerable"
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["GroundedCitations"].value is True
    assert case.attributes["usage_snapshot"]["aggregate"]["tool_calls"] == 0
    assert case.labels["DeclaredTrajectory"].value == "unknown"
    assert totals["scored"] == totals["correct"] == 1


def test_bare_string_known_prediction_is_blocked_despite_native_equality(tmp_path: Path) -> None:
    async def task(_: AnalysisInput) -> str:
        return "vulnerable"

    report = asyncio.run(evaluate_dataset(_source_case(), _config(tmp_path), tmp_path, task=task))
    case = report.cases[0]
    totals, _ = report_summary(report)
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["GroundedCitations"].value is False
    assert totals["all_attempts"] == totals["blocked"] == 1
    assert totals["scored"] == totals["correct"] == 0
    assert totals["correct_all"] == 0
    assert totals["correct_scored"] is None


def test_invalid_citation_is_blocked_and_does_not_count_as_correct(tmp_path: Path) -> None:
    async def task(inputs: AnalysisInput) -> AnalysisResult:
        return AnalysisResult(assessment=SourceAssessment(prediction="vulnerable", rationale="claim",
                              citations=(Citation(path="other.py", start_line=1, end_line=1),)),
                              metrics=_stage(requests=0, tool_calls=0, input_tokens=0, output_tokens=0,
                                             field_availability={}, usage_details={}))

    report = asyncio.run(evaluate_dataset(_source_case(), _config(tmp_path), tmp_path, task=task))
    case = report.cases[0]
    totals, _ = report_summary(report)
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["GroundedCitations"].value is False
    assert case.attributes["usage_snapshot"]["aggregate"]["input_tokens"] is None
    assert case.attributes["usage_snapshot"]["field_availability"]["input_tokens"] == "unknown"
    assert totals["blocked"] == 1
    assert totals["scored"] == totals["correct"] == 0
    assert totals["correct_all"] == 0


def test_expected_unknown_is_an_abstention_not_accuracy_or_coverage(tmp_path: Path) -> None:
    inputs = _source_case().cases[0].inputs
    dataset = Dataset[AnalysisInput, str, dict](name="unknown", cases=[Case(name="unknown", inputs=inputs,
        expected_output="unknown", metadata=_metadata())])

    async def task(value: AnalysisInput) -> AnalysisResult:
        return AnalysisResult(assessment=SourceAssessment(prediction="unknown", rationale="insufficient slice"), metrics=_stage())

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, task=task))
    case = report.cases[0]
    totals, _ = report_summary(report)
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["GroundedCitations"].value is True
    assert totals["all_attempts"] == totals["abstained"] == 1
    assert totals["scored"] == totals["correct"] == 0
    assert totals["correct_all"] == 0
    assert totals["correct_scored"] is None
    assert totals["coverage"] == 0


def test_invalid_domain_string_is_blocked_while_exception_is_a_separate_task_failure(tmp_path: Path) -> None:
    inputs = _source_case().cases[0].inputs
    dataset = Dataset[AnalysisInput, str, dict](name="errors", cases=[
        Case(name="returned", inputs=inputs, expected_output="outside-domain", metadata=_metadata()),
        Case(name="raised", inputs=inputs.model_copy(update={"concern": "raise"}), expected_output="vulnerable",
             metadata=_metadata()),
    ])

    async def task(value: AnalysisInput) -> str:
        if value.concern == "raise":
            raise RuntimeError("transport unavailable")
        return "outside-domain"

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, task=task))
    totals, _ = report_summary(report)
    case = report.cases[0]
    assert len(report.cases) == 1 and case.output == "outside-domain"
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["OutputDomain"].value is False
    assert len(report.failures) == 1
    assert totals["all_attempts"] == 2
    assert totals["blocked"] == totals["task_errors"] == 1
    assert totals["scored"] == totals["correct"] == 0
    assert totals["coverage"] == totals["correct_all"] == 0
    assert totals["requests"] is None
    assert totals["requests_known_sum"] is None
    assert totals["requests_known_attempts"] == 0
    assert totals["requests_unknown_attempts"] == 2


def test_evaluator_failure_is_separate_from_task_failure(tmp_path: Path) -> None:
    class BrokenEvaluator(Evaluator):
        def evaluate(self, ctx):
            raise RuntimeError("frozen evaluator defect")

    dataset = _source_case().model_copy(update={"evaluators": [BrokenEvaluator()]})

    async def task(value: AnalysisInput) -> AnalysisResult:
        return _analysis("vulnerable", value)

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, task=task))
    totals, _ = report_summary(report)
    assert len(report.failures) == 0
    assert len(report.cases[0].evaluator_failures) == 1
    assert totals["evaluator_errors"] == 1
    assert totals["task_errors"] == 0


def test_evidence_free_confirmed_run_is_blocked_despite_native_equality(tmp_path: Path) -> None:
    from corsair.v2.contracts import RunSpec, SourceRequest

    spec = RunSpec(request_id="run", source=SourceRequest(path=str(tmp_path)), concern="x", language="java")
    dataset = Dataset[RunSpec, str, dict](name="runs", cases=[Case(name="run", inputs=spec,
        expected_output="confirmed_finding", metadata={"input_kind": "run", "language": "java", "framework": "maven",
        "cwe": ["CWE-20"], "source_digest": "run", "suite_kind": "upstream", "split": "public-dev"})])

    async def task(value: RunSpec) -> RunResult:
        return RunResult(run_id=value.request_id, spec_sha256="a" * 64, config_sha256="b" * 64,
                         verdict=Verdict(status="confirmed_finding", reason="test", rule_id="r", summary="s"),
                         qualification="qualified", cleanup="confirmed", duration_seconds=0.1)

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, mode="run", task=task))
    case = report.cases[0]
    totals, _ = report_summary(report)
    assert case.assertions["EqualsExpected"].value is True
    assert case.assertions["EvidenceBackedDisposition"].value is False
    assert totals["all_attempts"] == totals["blocked"] == 1
    assert totals["scored"] == totals["correct"] == 0
    assert totals["correct_all"] == 0


def test_summary_language_grouping_confusion_and_known_usage_denominators(tmp_path: Path) -> None:
    cases = [
        Case(name="python-positive", inputs=AnalysisInput(files={"src/alpha.py": "def transform(value):\n    return value\n"}, language="python"),
             expected_output="vulnerable", metadata=_metadata("python")),
        Case(name="python-negative", inputs=AnalysisInput(files={"src/beta.py": "def transform(value):\n    return value\n"}, language="python"),
             expected_output="safe_in_scope", metadata=_metadata("python")),
        Case(name="java-positive", inputs=AnalysisInput(files={"src/Alpha.java": "class Alpha { Object f(Object v) { return v; } }\n"}, language="java"),
             expected_output="vulnerable", metadata=_metadata("java")),
        Case(name="java-negative", inputs=AnalysisInput(files={"src/Beta.java": "class Beta { Object f(Object v) { return v; } }\n"}, language="java"),
             expected_output="safe_in_scope", metadata=_metadata("java")),
    ]
    outputs = {"src/alpha.py": "vulnerable", "src/beta.py": "safe_in_scope", "src/Alpha.java": "safe_in_scope",
               "src/Beta.java": "vulnerable"}
    dataset = Dataset[AnalysisInput, str, dict](name="two-class-two-language", cases=cases)

    async def task(value: AnalysisInput) -> AnalysisResult:
        return _analysis(outputs[next(iter(value.files))], value)

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, task=task))
    totals, rows = report_summary(report, group_by=("language",))
    by_language = {row["language"]: row for row in rows}
    assert set(by_language) == {"java", "python"}
    assert all(row["framework"] == row["cwe"] == row["agent"] == row["model"] == "all" for row in rows)
    assert totals["all_attempts"] == totals["scored"] == 4
    assert totals["correct"] == 2
    assert totals["true_positive"] == totals["true_negative"] == 1
    assert totals["false_positive"] == totals["false_negative"] == 1
    assert totals["correct_all"] == pytest.approx(totals["correct"] / totals["all_attempts"])
    assert totals["correct_scored"] == pytest.approx(totals["correct"] / totals["scored"])
    assert totals["coverage"] == pytest.approx(totals["scored"] / totals["all_attempts"])
    assert totals["precision"] == pytest.approx(totals["true_positive"] /
                                                  (totals["true_positive"] + totals["false_positive"]))
    assert totals["recall"] == pytest.approx(totals["true_positive"] /
                                               (totals["true_positive"] + totals["false_negative"]))
    assert totals["f1"] == pytest.approx(2 * totals["true_positive"] /
                                           (2 * totals["true_positive"] + totals["false_positive"] + totals["false_negative"]))
    assert totals["requests"] == totals["requests_known_sum"] == 4
    assert totals["requests_known_attempts"] == 4
    assert totals["requests_unknown_attempts"] == 0


def test_source_production_seam_receives_fresh_attempt_id_without_mutating_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = _source_case().cases[0].inputs
    before = inputs.model_dump(mode="json")
    calls: list[tuple[AnalysisInput, str]] = []
    dataset = Dataset[AnalysisInput, str, dict](name="production-source", cases=[Case(name="source", inputs=inputs,
        expected_output="vulnerable", metadata=_metadata())])

    async def analyze_case(value: AnalysisInput, config: OperatorConfig, *, attempt_id: str) -> AnalysisResult:
        assert config == _config_instance
        calls.append((value, attempt_id))
        return _analysis("vulnerable", value)

    _config_instance = _config(tmp_path)
    monkeypatch.setattr("corsair.v2.runtime.analyze_case", analyze_case)
    report = asyncio.run(evaluate_dataset(dataset, _config_instance, tmp_path))
    case = report.cases[0]
    assert len(calls) == 1
    assert calls[0][0] is inputs
    assert calls[0][0].model_dump(mode="json") == before
    assert calls[0][1] == case.attributes["attempt_request_id"]
    assert case.attributes["logical_case_id"] == digest(inputs)


def test_run_repeat_uses_fresh_request_and_trial_ids_without_reusing_a_cached_attempt(tmp_path: Path) -> None:
    from corsair.v2.contracts import RunSpec, SourceRequest

    logical_request_id = "full-run-logical-case"
    source = SourceRequest(path=str(tmp_path / "captured-source"))
    source_before = source.model_dump(mode="json")
    spec = RunSpec(request_id=logical_request_id, source=source, concern="x", language="python")
    dataset = Dataset[RunSpec, str, dict](name="repeat-runs", cases=[Case(
        name="full-run", inputs=spec, expected_output="inconclusive",
        metadata={"input_kind": "run", "language": "python", "framework": "pytest", "cwe": ["CWE-20"],
                  "source_digest": "source-id", "suite_kind": "upstream", "split": "public-dev"},
    )])
    calls: list[RunSpec] = []

    async def task(value: RunSpec) -> RunResult:
        calls.append(value)
        return RunResult(run_id=value.request_id, spec_sha256="a" * 64, config_sha256="b" * 64,
                         verdict=Verdict(status="inconclusive", reason="fixture", rule_id="fixture", summary="fixture"),
                         qualification="qualified", cleanup="confirmed", duration_seconds=0.1)

    report = asyncio.run(evaluate_dataset(dataset, _config(tmp_path), tmp_path, mode="run", repeat=2, task=task))
    assert len(calls) == 2
    assert {call.request_id for call in calls} == {case.attributes["attempt_request_id"] for case in report.cases}
    assert len({call.request_id for call in calls}) == 2
    assert all(call.request_id != logical_request_id and call.source == source for call in calls)
    assert source.model_dump(mode="json") == source_before
    assert {case.attributes["logical_case_id"] for case in report.cases} == {logical_request_id}
    assert len({case.attributes["trial_id"] for case in report.cases}) == 2
    assert {case.source_case_name for case in report.cases} == {"full-run"}
