"""Local report projection, compatible comparison, and immutable baseline promotion."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic_evals.reporting import EvaluationReport

from .contracts import digest
from .evaluation import _case_bucket, report_summary
from .storage import _private_directory

_SCHEMA = "corsair.evaluation-report.v1"


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "__dict__") and value.__class__.__module__.startswith("pydantic_evals"):
        return {key: _json_value(item) for key, item in vars(value).items() if key != "__orig_class__"}
    return value


def _duration_stats(values: Iterable[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"median": None, "p95": None}
    median = ordered[(len(ordered) - 1) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2 - 1] + ordered[len(ordered)//2]) / 2
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {"median": median, "p95": ordered[index]}


def _evaluation_results(values: dict[str, Any]) -> dict[str, Any]:
    return {name: {"value": item.value, "reason": item.reason, "evaluator_version": item.evaluator_version}
            for name, item in values.items()}


def _usage_metrics(case: Any) -> dict[str, Any]:
    snapshot = case.attributes.get("usage_snapshot", {})
    aggregate = snapshot.get("aggregate", {}) if isinstance(snapshot, dict) else {}
    availability = snapshot.get("field_availability", {}) if isinstance(snapshot, dict) else {}
    return {
        "model_requests": aggregate.get("requests", case.metrics.get("model_requests")),
        "tool_attempts": aggregate.get("tool_calls", case.metrics.get("successful_tool_calls")),
        "input_tokens": aggregate.get("input_tokens", case.metrics.get("input_tokens")),
        "output_tokens": aggregate.get("output_tokens", case.metrics.get("output_tokens")),
        "cache_read_tokens": aggregate.get("cache_read_tokens", case.metrics.get("cache_read_tokens")),
        "cache_write_tokens": aggregate.get("cache_write_tokens", case.metrics.get("cache_write_tokens")),
        "reasoning_tokens": aggregate.get("reasoning_tokens", case.metrics.get("reasoning_tokens")),
        "usage_availability": availability,
    }


def _record_for_case(case: Any, trial: int) -> dict[str, Any]:
    metadata = dict(case.metadata or {})
    expected = case.expected_output
    equals = case.assertions.get("EqualsExpected")
    denominator = _case_bucket(case)
    correct = bool(equals.value) if equals is not None and denominator == "scored" else None
    status = case.output
    return {
        "schema": "corsair.eval-record.v1", "row_kind": "case",
        "case": {"id": case.name, "source_case_name": case.source_case_name or case.name,
                 "source_digest": metadata.get("source_digest")},
        "trial": trial,
        "trial_id": case.attributes.get("trial_id"),
        "logical_case_id": case.attributes.get("logical_case_id", case.source_case_name or case.name),
        "attempt_request_id": case.attributes.get("attempt_request_id"),
        "dimensions": {key: metadata.get(key, "unknown") for key in ("language", "framework", "agent", "provider", "model")},
        "cwe": metadata.get("cwe", []), "suite_id": metadata.get("suite_id"), "suite_kind": metadata.get("suite_kind"),
        "split": metadata.get("split"), "task_mode": metadata.get("task_mode", metadata.get("input_kind")),
        "expected_output": expected,
        "promotion_eligible": metadata.get("promotion_eligible", True), "generated": metadata.get("generated", False),
        "outcome": {"terminal_status": status, "correct": correct, "denominator_class": denominator,
                    "evidence_status": case.attributes.get("evidence_status"), "citation_status": case.attributes.get("citation_status")},
        "metrics": {**_usage_metrics(case), "task_duration_seconds": case.task_duration,
                    "total_duration_seconds": case.total_duration},
        "usage_snapshot": case.attributes.get("usage_snapshot"), "attributes": case.attributes,
        "assertions": _evaluation_results(case.assertions), "scores": _evaluation_results(case.scores),
        "labels": _evaluation_results(case.labels),
        "evaluator_failures": [_json_value(item) for item in case.evaluator_failures],
        "trace_id": case.trace_id, "span_id": case.span_id,
    }


def _record_for_failure(failure: Any, trial: int) -> dict[str, Any]:
    metadata = dict(failure.metadata or {})
    return {
        "schema": "corsair.eval-record.v1", "row_kind": "task_failure",
        "case": {"id": failure.name, "source_case_name": failure.source_case_name or failure.name,
                 "source_digest": metadata.get("source_digest")}, "trial": trial,
        "trial_id": None, "logical_case_id": failure.source_case_name or failure.name, "attempt_request_id": None,
        "dimensions": {key: metadata.get(key, "unknown") for key in ("language", "framework", "agent", "provider", "model")},
        "cwe": metadata.get("cwe", []), "suite_id": metadata.get("suite_id"), "suite_kind": metadata.get("suite_kind"),
        "split": metadata.get("split"), "task_mode": metadata.get("task_mode", metadata.get("input_kind")),
        "expected_output": failure.expected_output,
        "promotion_eligible": metadata.get("promotion_eligible", True), "generated": metadata.get("generated", False),
        "outcome": {"terminal_status": None, "correct": None, "denominator_class": "task_error"},
        "metrics": {"model_requests": None, "tool_attempts": None, "input_tokens": None, "output_tokens": None,
                    "cache_read_tokens": None, "cache_write_tokens": None, "reasoning_tokens": None,
                    "task_duration_seconds": None, "total_duration_seconds": None},
        "error": {"message": failure.error_message, "stacktrace": failure.error_stacktrace},
        "trace_id": failure.trace_id, "span_id": failure.span_id,
    }


def _records(report: EvaluationReport) -> list[dict[str, Any]]:
    attempts: dict[str, int] = {}
    values: list[dict[str, Any]] = []
    for case in report.cases:
        source = case.source_case_name or case.name
        attempts[source] = attempts.get(source, 0) + 1
        values.append(_record_for_case(case, attempts[source]))
    for failure in report.failures:
        source = failure.source_case_name or failure.name
        attempts[source] = attempts.get(source, 0) + 1
        values.append(_record_for_failure(failure, attempts[source]))
    return values


def _immutable_identity(records: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    # Repeats are multiple attempts of one frozen source/truth/mode identity.
    # Task failures retain the same identity rules as returned cases.
    distinct: dict[str, dict[str, Any]] = {}
    for row in records:
        source_case_name = str(row["case"]["source_case_name"])
        case = {"id": source_case_name, "source_digest": row["case"].get("source_digest"),
                "expected_identity": digest({"expected_output": row.get("expected_output")}),
                "split": row.get("split"), "suite_id": row.get("suite_id"),
                "suite_kind": row.get("suite_kind"), "task_mode": row.get("task_mode")}
        if source_case_name in distinct and distinct[source_case_name] != case:
            raise ValueError("Repeated case identity changed source, truth, split, or task mode")
        distinct[source_case_name] = case
    cases = list(distinct.values())
    cases.sort(key=lambda value: (str(value["id"]), str(value.get("source_digest"))))
    return {"dataset_digest": metadata.get("dataset_digest") or hashlib.sha256(
                json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "cases": cases, "split": sorted({row.get("split") for row in records}),
            "suite_kinds": sorted({row.get("suite_kind") for row in records}),
            "task_mode": sorted({row.get("task_mode") for row in records}),
            "evaluator_policy": metadata.get("evaluator_policy"),
            "execution_profile": metadata.get("execution_profile")}


def _write_private(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json_dump(path: Path, value: Any) -> None:
    _write_private(path, (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())


def _csv_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        values = {field: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                  for field, value in row.items()}
        writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                         for key, value in values.items()})
    _write_private(path, stream.getvalue().encode())


def _markdown_cell(value: Any) -> str:
    """Render a safe one-line Markdown table cell without changing the source value."""
    if value is None:
        return "unknown"
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _markdown_number(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _markdown_ratio(value: Any) -> str:
    return "unknown" if value is None else f"{float(value) * 100:.1f}%"


def _markdown_usage(row: dict[str, Any], field: str) -> str:
    """Avoid presenting partial or provider-unknown usage as a zero total."""
    total = row.get(field)
    known_attempts = row.get(f"{field}_known_attempts", 0)
    all_attempts = row.get("all_attempts", 0)
    if total is not None:
        return _markdown_number(total)
    known_sum = row.get(f"{field}_known_sum")
    if known_sum is None:
        return f"unknown (0/{all_attempts} known)"
    return f"unknown (known sum {_markdown_number(known_sum)}; {known_attempts}/{all_attempts} known)"


def _confusion_metrics_usable(row: dict[str, Any]) -> bool:
    """Only source-only, grounded binary classifications populate this matrix."""
    return sum(int(row.get(field, 0)) for field in ("true_positive", "true_negative", "false_positive", "false_negative")) > 0


def _summary_markdown(summary: dict[str, Any], language_rows: list[dict[str, Any]]) -> str:
    """Produce a compact operator-readable projection; native Evals owns its full render."""
    lines = [
        "# Evaluation summary",
        "",
        (f"- **All-attempt accuracy:** {_markdown_ratio(summary.get('correct_all'))} "
         f"({summary.get('correct', 0)}/{summary.get('all_attempts', 0)} correct usable outcomes)"),
        (f"- **Decisive coverage:** {_markdown_ratio(summary.get('coverage'))} "
         f"({summary.get('scored', 0)}/{summary.get('all_attempts', 0)} attempts)"),
        f"- **Task errors / evaluator errors:** {summary.get('task_errors', 0)} / {summary.get('evaluator_errors', 0)}",
        f"- **Unscored:** {summary.get('abstained', 0)} abstentions; {summary.get('blocked', 0)} blocked",
        "",
        "Source-only classifications are not executed security verdicts. Accuracy and coverage are evaluation measurements, not model approval, host qualification, or a production-security claim.",
        "",
        "| Language | Attempts | Usable accuracy | Decisive coverage | Precision | Recall | FP | FN | Reported input tokens | Reported output tokens | Task median (s) | Task P95 (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in language_rows:
        usable_confusion = _confusion_metrics_usable(row)
        lines.append("| " + " | ".join((
            _markdown_cell(row.get("language")),
            _markdown_number(row.get("all_attempts")),
            _markdown_ratio(row.get("correct_scored")),
            _markdown_ratio(row.get("coverage")),
            _markdown_ratio(row.get("precision")) if usable_confusion else "not applicable",
            _markdown_ratio(row.get("recall")) if usable_confusion else "not applicable",
            _markdown_number(row.get("false_positive")) if usable_confusion else "not applicable",
            _markdown_number(row.get("false_negative")) if usable_confusion else "not applicable",
            _markdown_usage(row, "input_tokens"),
            _markdown_usage(row, "output_tokens"),
            _markdown_number(row.get("task_duration_median")),
            _markdown_number(row.get("task_duration_p95")),
        )) + " |")
    lines.extend((
        "",
        "Confusion metrics are shown only for usable, grounded two-class source predictions. Token totals are reported only when every attempt reported that field; otherwise the known sum and known-attempt coverage are shown. Unknown provider usage is not zero, and a failed request may have billing that was not reported.",
        "",
    ))
    return "\n".join(lines)


def export_report(report: EvaluationReport, output_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Export a local native-report projection with all returned and failed attempts."""
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")  # noqa: TRY004 - invalid admission is consistently ValueError
    native_metadata = dict(report.experiment_metadata or {})
    # Runtime identities come from the evaluation boundary, not caller-provided
    # labels.  They are experiment provenance and intentionally stay outside the
    # immutable dataset identity so comparable runs may differ in model/code.
    for key in ("config_digest", "config_identity", "build_identity", "native_profile_hashes", "evaluator_policy"):
        if key in metadata and key in native_metadata and metadata[key] != native_metadata[key]:
            raise ValueError(f"Caller metadata conflicts with native {key}")
    effective_metadata = {**metadata, **native_metadata}
    output_dir = _private_directory(output_dir)
    records = _records(report)
    summary, strata = report_summary(report)
    by_dimension = {}
    for dimension in ("language", "framework", "cwe", "agent", "model"):
        dimension_summary, dimension_strata = report_summary(report, group_by=(dimension,))
        by_dimension[dimension] = {"summary": dimension_summary, "strata": dimension_strata}
    task_durations = [row["metrics"]["task_duration_seconds"] for row in records if row["row_kind"] == "case"]
    total_durations = [row["metrics"]["total_duration_seconds"] for row in records if row["row_kind"] == "case"]
    status_by_source: dict[str, set[str | None]] = {}
    for row in records:
        status_by_source.setdefault(row["case"]["source_case_name"], set()).add(row["outcome"].get("terminal_status"))
    summary["task_duration_seconds"] = _duration_stats(task_durations)
    summary["total_duration_seconds"] = _duration_stats(total_durations)
    summary["trial_instability_cases"] = sum(1 for statuses in status_by_source.values() if len(statuses) > 1)
    identity = _immutable_identity(records, effective_metadata)
    native = {
        "name": report.name, "trace_id": report.trace_id, "span_id": report.span_id,
        "experiment_metadata": report.experiment_metadata,
        "cases": [_json_value(case) for case in report.cases],
        "failures": [_json_value(failure) for failure in report.failures],
        "analyses": [_json_value(item) for item in report.analyses],
        "report_evaluator_failures": [_json_value(item) for item in report.report_evaluator_failures],
    }
    document = {"schema": _SCHEMA, "metadata": effective_metadata, "immutable_identity": identity,
                "native_report": native, "records": records, "summary": summary, "strata": strata,
                "by_dimension": by_dimension}
    report_path = output_dir / "evaluation-report.json"
    records_path = output_dir / "evaluation-records.csv"
    strata_path = output_dir / "evaluation-strata.csv"
    human_path = output_dir / "evaluation-report.txt"
    summary_markdown_path = output_dir / "evaluation-summary.md"
    _json_dump(report_path, document)
    _csv_dump(records_path, records)
    _csv_dump(strata_path, strata)
    _write_private(human_path, report.render(include_metadata=True, include_durations=True, include_total_duration=True,
                                           include_errors=True, include_evaluator_failures=True, include_reasons=True).encode())
    _, language_rows = report_summary(report, group_by=("language",))
    _write_private(summary_markdown_path, _summary_markdown(summary, language_rows).encode())
    return {"report": str(report_path), "records": str(records_path), "strata": str(strata_path),
            "human": str(human_path), "summary_markdown": str(summary_markdown_path), "summary": summary,
            "immutable_identity": identity}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read exported evaluation report {path}") from error
    if value.get("schema") != _SCHEMA or not isinstance(value.get("records"), list):
        raise ValueError(f"{path} is not a { _SCHEMA } export")
    return value


def _check_comparable(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    left, right = baseline.get("immutable_identity", {}), candidate.get("immutable_identity", {})
    kinds = set(left.get("suite_kinds", [])) | set(right.get("suite_kinds", []))
    if "smoke" in kinds and len(kinds) > 1:
        raise ValueError("Incompatible reports: smoke and upstream suites cannot be compared")
    for key in ("dataset_digest", "cases", "split", "task_mode", "evaluator_policy", "execution_profile"):
        if left.get(key) != right.get(key):
            raise ValueError(f"Incompatible reports: immutable {key} differs")


def _pair_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["case"]["source_case_name"]), int(row.get("trial", 1))


def compare_reports(baseline: Path, candidate: Path, output_dir: Path) -> dict[str, Any]:
    """Create an explicit paired comparison; missing/failure rows remain visible."""
    left, right = _load(baseline), _load(candidate)
    _check_comparable(left, right)
    output_dir = _private_directory(output_dir)
    old = {_pair_key(row): row for row in left["records"]}
    new = {_pair_key(row): row for row in right["records"]}
    pairs: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        pairs.append({
            "schema": "corsair.eval-paired.v1", "source_case_name": key[0], "trial": key[1],
            "baseline_row_kind": before.get("row_kind") if before else "missing",
            "candidate_row_kind": after.get("row_kind") if after else "missing",
            "baseline_status": before.get("outcome", {}).get("terminal_status") if before else None,
            "candidate_status": after.get("outcome", {}).get("terminal_status") if after else None,
            "baseline_correct": before.get("outcome", {}).get("correct") if before else None,
            "candidate_correct": after.get("outcome", {}).get("correct") if after else None,
            "baseline_task_seconds": before.get("metrics", {}).get("task_duration_seconds") if before else None,
            "candidate_task_seconds": after.get("metrics", {}).get("task_duration_seconds") if after else None,
            "baseline_requests": before.get("metrics", {}).get("model_requests") if before else None,
            "candidate_requests": after.get("metrics", {}).get("model_requests") if after else None,
            "baseline_tools": before.get("metrics", {}).get("tool_attempts") if before else None,
            "candidate_tools": after.get("metrics", {}).get("tool_attempts") if after else None,
            "missing_side": "none" if before and after else ("baseline" if before is None else "candidate"),
        })
    delta_keys = ("agent", "model", "prompt", "provider", "config_digest", "config_identity", "build_identity",
                  "native_profile_hashes")
    left_meta, right_meta = left.get("metadata", {}), right.get("metadata", {})
    deltas = {key: {"baseline": left_meta.get(key), "candidate": right_meta.get(key)} for key in delta_keys
              if left_meta.get(key) != right_meta.get(key)}
    payload = {"schema": "corsair.eval-comparison.v1", "baseline": str(baseline), "candidate": str(candidate),
               "immutable_identity": left["immutable_identity"], "experiment_deltas": deltas, "paired": pairs,
               "missing_rows": sum(pair["missing_side"] != "none" for pair in pairs)}
    json_path = output_dir / "evaluation-comparison.json"
    csv_path = output_dir / "evaluation-paired.csv"
    _json_dump(json_path, payload)
    _csv_dump(csv_path, pairs)
    return {"comparison": str(json_path), "paired": str(csv_path), "experiment_deltas": deltas,
            "paired_rows": len(pairs), "missing_rows": payload["missing_rows"]}


def _private_root(root: Path) -> Path:
    return _private_directory(root)


def promote_baseline(path: Path, root: Path) -> dict[str, Any]:
    """Create a digest-addressed immutable evaluation baseline reference, never a smoke promotion.

    A reference freezes comparable evaluation input/provenance only. It does not
    approve a model, claim quality, or qualify a host/runtime.
    """
    document = _load(path)
    identity = document.get("immutable_identity", {})
    kinds = set(identity.get("suite_kinds", []))
    if "smoke" in kinds:
        raise ValueError("Generated smoke reports cannot be promoted as evaluation baselines")
    if any(row.get("promotion_eligible") is False or row.get("generated") is True for row in document["records"]):
        raise ValueError("This development/generated report is explicitly ineligible for baseline promotion")
    if not identity.get("dataset_digest") or not identity.get("cases"):
        raise ValueError("Baseline promotion requires an explicit immutable dataset/case identity")
    raw = path.read_bytes()
    report_sha256 = hashlib.sha256(raw).hexdigest()
    destination = _private_directory(_private_root(root) / "baselines")
    reference = destination / f"{report_sha256}.json"
    value = {"schema": "corsair.baseline-reference.v1", "report_sha256": report_sha256,
             "report_path": str(path.absolute()), "immutable_identity": identity}
    encoded = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    if reference.exists():
        if reference.read_bytes() != encoded:
            raise ValueError("Existing baseline reference digest has incompatible content")
    else:
        _write_private(reference, encoded)
    return {"reference": str(reference), "report_sha256": report_sha256, "immutable_identity": identity}
