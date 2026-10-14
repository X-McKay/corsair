"""Native Pydantic Evals execution for Corsair v2 datasets.

The runner intentionally contains no scheduling loop.  ``Dataset.evaluate`` owns
case concurrency/repeats/failures; this module only adapts the normal Corsair
runtime result to a narrow string prediction and records non-sensitive receipts.
"""
from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import logfire
from pydantic_evals import Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import (
    EqualsExpected,
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    MaxModelRequests,
    MaxToolCalls,
    ReportEvaluator,
    ReportEvaluatorContext,
    TrajectoryMatch,
)
from pydantic_evals.reporting import EvaluationReport
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

from .config import build_identity, config_identity
from .contracts import (
    AnalysisInput,
    AnalysisResult,
    OperatorConfig,
    RunResult,
    RunSpec,
    StageMetrics,
    digest,
)
from .storage import Store

_SOURCE_OUTPUTS = frozenset({"vulnerable", "safe_in_scope", "unknown"})
_RUN_OUTPUTS = frozenset({"confirmed_finding", "verified_repair", "unknown_absence", "inconclusive", "unsupported", "unqualified", "cancelled", "failed_platform"})
_USAGE_FIELDS = ("requests", "tool_calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")


def _configure_local_telemetry() -> None:
    """Configure only the in-process Logfire provider before Evals creates spans."""
    try:
        logfire.configure(service_name="corsair-v2-evals", environment="local", send_to_logfire=False,
                          inspect_arguments=False)
    except RuntimeError as error:
        # Logfire is process-global.  A prior *local-only* configuration is safe;
        # do not replace providers or enable an exporter from an eval helper.
        if "already configured" not in str(error).lower():
            raise


def _metric_presence(stage: StageMetrics, field: str) -> tuple[int | None, str]:
    """Return a conservative value/presence pair from the typed receipt.

    ``field_availability`` is the provider-boundary fact.  The older untyped
    envelope is only a compatibility fallback.  In particular, a typed reported
    zero remains zero and a typed unknown remains null even if an SDK normalized
    the raw field to a default numeric value.
    """
    value = getattr(stage, field)
    declared = stage.field_availability.get(field)
    if declared is None:
        availability = stage.usage_details.get("field_availability", {})
        declared = availability.get(field) if isinstance(availability, dict) else None
    if declared in {"reported", "reported_zero", "not_reported", "not_applicable", "unknown"}:
        if declared in {"not_reported", "not_applicable", "unknown"}:
            return None, declared
        if value is None:
            return None, "unknown"
        return int(value), declared
    if value is None:
        return None, "unknown"
    if value == 0:
        return None, "unknown"
    return int(value), "reported"


def _usage_envelope(stages: tuple[StageMetrics, ...]) -> dict[str, Any]:
    encoded: list[dict[str, Any]] = []
    aggregate_values: dict[str, int | None] = {}
    aggregate_availability: dict[str, str] = {}
    per_field: dict[str, list[int | None]] = {field: [] for field in _USAGE_FIELDS}
    for stage in stages:
        values: dict[str, int | None] = {}
        availability: dict[str, str] = {}
        for field in _USAGE_FIELDS:
            values[field], availability[field] = _metric_presence(stage, field)
            per_field[field].append(values[field])
        encoded.append({
            "role": stage.role, "model": stage.model, "status": stage.status,
            "duration_seconds": stage.latency_seconds, "usage": values,
            "field_availability": availability,
            "trajectory": {"observed": bool(stage.trajectory), "events": len(stage.trajectory)},
        })
    for field, values in per_field.items():
        if stages and all(value is not None for value in values):
            aggregate_values[field] = sum(value for value in values if value is not None)
            aggregate_availability[field] = "reported_zero" if aggregate_values[field] == 0 else "reported"
        else:
            aggregate_values[field] = None
            aggregate_availability[field] = "unknown"
    return {
        "schema": "corsair.model-usage.v1", "source": "corsair-stage-metrics",
        "stages": encoded, "aggregate": aggregate_values, "field_availability": aggregate_availability,
    }


def _record_usage(stages: tuple[StageMetrics, ...], *, terminal_status: str, evidence_status: str,
                  citation_status: str) -> None:
    envelope = _usage_envelope(stages)
    set_eval_attribute("usage_snapshot", envelope)
    set_eval_attribute("terminal_status", terminal_status)
    set_eval_attribute("evidence_status", evidence_status)
    set_eval_attribute("citation_status", citation_status)
    set_eval_attribute("trajectory_observed", any(bool(stage.trajectory) for stage in stages))
    for field, value in envelope["aggregate"].items():
        if value is not None:
            increment_eval_metric({"requests": "model_requests", "tool_calls": "successful_tool_calls"}.get(field, field), value)


def _valid_citations(inputs: AnalysisInput, result: AnalysisResult) -> str:
    assessment = result.assessment
    if assessment is None:
        return "absent"
    if not assessment.citations:
        return "absent"
    source_lines = {path: len(content.splitlines()) for path, content in inputs.files.items()}
    if all(citation.path in source_lines and citation.end_line <= source_lines[citation.path] for citation in assessment.citations):
        return "valid"
    return "invalid"


def _analysis_projection(inputs: AnalysisInput, result: AnalysisResult) -> str:
    if result.assessment is None or result.metrics.status != "completed":
        output = "unknown"
        citations = "absent"
    else:
        output = result.assessment.prediction
        citations = _valid_citations(inputs, result)
    _record_usage((result.metrics,), terminal_status=output, evidence_status="source_only", citation_status=citations)
    return output


def _verified_run_evidence(result: RunResult, config: OperatorConfig) -> str:
    """Verify the engine's immutable, acyclic evidence receipt before scoring.

    A reference-shaped object is not evidence.  The engine stores a canonical
    provisional result in the evidence artifact before attaching ``evidence_ref``
    and ``report_ref`` to the returned result.  Reconstructing and comparing that
    exact provisional result binds verdict, policy/image/revision effects, command
    receipts, and all artifact references to bytes retrieved from the configured
    Store.  This is deliberately deterministic and never consults benchmark truth.
    """
    if result.evidence_ref is None:
        return "missing"
    if result.qualification != "qualified" or result.cleanup != "confirmed" or not result.revisions:
        return "unqualified"
    try:
        with Store(config.storage_root) as store:
            evidence = store.get_json(result.evidence_ref)
    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return "invalid"
    if not isinstance(evidence, dict) or not isinstance(evidence.get("result"), dict):
        return "invalid"
    try:
        provisional = RunResult.model_validate(evidence["result"])
    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return "invalid"
    expected = result.model_copy(update={"evidence_ref": None, "report_ref": None})
    if provisional != expected:
        return "mismatched"
    build = evidence.get("build_sha256")
    if not isinstance(build, str) or len(build) != 64 or any(char not in "0123456789abcdef" for char in build):
        return "invalid"
    # Commands are only genuine effects when their engine-native deterministic
    # receipt IDs are present.  Their full values are already compared above.
    if any(not command.operation_id.startswith("native.") for revision in provisional.revisions for command in revision.commands):
        return "invalid"
    try:
        from .contracts import ArtifactRef, InvestigationPlan, ValidityReview
        from .engine import execution_identity
        from .verdict import decide
        if result.config_sha256 != execution_identity(config):
            return "mismatched_config"
        with Store(config.storage_root) as store:
            if store.result(result.run_id) != result:
                return "not_committed"
            plan = InvestigationPlan.model_validate(store.get_json(result.plan_ref))
            pair = store.get_json(result.pair_ref)
            reviewed = store.get_json(result.validity_ref)
            if reviewed["plan_ref"] != result.plan_ref.model_dump(mode="json") or reviewed["pair_ref"] != result.pair_ref.model_dump(mode="json"):
                return "mismatched_review"
            if store.get_json(ArtifactRef.model_validate(reviewed["source_ref"])) != result.source.model_dump(mode="json"):
                return "mismatched_source"
            review = ValidityReview.model_validate(reviewed["review"])
            for revision in result.revisions:
                if not revision.commands or revision.report_ref is None:
                    return "missing_native_evidence"
                store.get(revision.report_ref)
                for command in revision.commands:
                    if (store.operation(command.operation_id) or {}).get("result") != command.model_dump(mode="json"):
                        return "invalid_native_receipt"
                    for ref in (command.stdout_ref, command.stderr_ref):
                        if ref is not None:
                            store.get(ref)
            expected = decide(plan, review, next((r for r in result.revisions if r.revision == "baseline"), None),
                              next((r for r in result.revisions if r.revision == "candidate"), None),
                              pair_sha256=digest(pair), qualified=True)
            if expected != result.verdict:
                return "invalid_disposition"
    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return "invalid"
    return "valid"


def _run_projection(result: RunResult, config: OperatorConfig) -> str:
    output = result.verdict.status
    decisive = output in {"confirmed_finding", "verified_repair", "unknown_absence"}
    verified = _verified_run_evidence(result, config)
    evidence = "valid" if not decisive else verified
    _record_usage(tuple(item.metrics for item in result.stages), terminal_status=output, evidence_status=evidence,
                  citation_status="not_applicable")
    return output


@dataclass(repr=False)
class OutputDomain(Evaluator[object, str, dict[str, Any]]):
    """Verify that the adaptation produced a terminal, scoreable string."""
    def evaluate(self, ctx: EvaluatorContext[object, str, dict[str, Any]]) -> EvaluationReason:
        mode = (ctx.metadata or {}).get("input_kind", "source")
        allowed = _SOURCE_OUTPUTS if mode == "source" else _RUN_OUTPUTS
        return EvaluationReason(ctx.output in allowed, f"mode={mode}; output={ctx.output!r}")


@dataclass(repr=False)
class GroundedCitations(Evaluator[object, str, dict[str, Any]]):
    """Require in-slice citations for a non-abstaining source prediction."""
    def evaluate(self, ctx: EvaluatorContext[object, str, dict[str, Any]]) -> EvaluationReason:
        if (ctx.metadata or {}).get("input_kind", "source") != "source":
            return EvaluationReason(True, "not applicable to full-system output")
        status = ctx.attributes.get("citation_status", "unknown")
        if ctx.output == "unknown":
            return EvaluationReason(True, "abstention has no source claim")
        return EvaluationReason(status == "valid", f"citation_status={status}")


@dataclass(repr=False)
class EvidenceBackedDisposition(Evaluator[object, str, dict[str, Any]]):
    """Require retained evidence for a qualified full-system decision, never source labels."""
    def evaluate(self, ctx: EvaluatorContext[object, str, dict[str, Any]]) -> EvaluationReason:
        if (ctx.metadata or {}).get("input_kind", "source") == "source":
            return EvaluationReason(True, "source-only classification is not an execution disposition")
        decisive = ctx.output in {"confirmed_finding", "verified_repair", "unknown_absence"}
        status = ctx.attributes.get("evidence_status", "unknown")
        return EvaluationReason(not decisive or status == "valid", f"evidence_status={status}")


@dataclass(repr=False)
class DeclaredTrajectory(Evaluator[object, str, dict[str, Any]]):
    """Use native ``TrajectoryMatch`` only for cases declaring a trajectory.

    No captured span tree is reported as the label ``unknown``.  It is not
    reinterpreted as a zero-tool success, while the native Max* evaluators still
    retain their failing assertion/reason for the absent instrumentation.
    """
    def evaluate(self, ctx: EvaluatorContext[object, str, dict[str, Any]]) -> EvaluationReason:
        expected = (ctx.metadata or {}).get("expected_trajectory")
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            return EvaluationReason("unknown", "no expected local-tool trajectory was declared")
        try:
            _ = ctx.span_tree
        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome; pinned Evals raises SpanTreeRecordingError here
            return EvaluationReason("unknown", f"local trajectory unavailable: {type(error).__name__}")
        result = TrajectoryMatch(expected_trajectory=expected, order="exact", include_failed=True,
                                 evaluation_name="declared_trajectory_match").evaluate(ctx)
        if isinstance(result, EvaluationReason):
            return result
        return EvaluationReason(result, None)


@dataclass(repr=False)
class CorsairStrata(ReportEvaluator[object, str, dict[str, Any]]):
    """Native report evaluator preserving all attempts and task failures."""
    def evaluate(self, ctx: ReportEvaluatorContext[object, str, dict[str, Any]]) -> list[ScalarResult | TableResult]:
        summary, rows = report_summary(ctx.report)
        columns = ["language", "framework", "cwe", "agent", "model", "all_attempts", "scored", "correct",
                   "correct_all", "correct_scored", "coverage", "abstained", "blocked", "task_errors",
                   "evaluator_errors", "true_positive", "true_negative", "false_positive", "false_negative",
                   "requests", "tools", "input_tokens", "output_tokens", "cache_read_tokens",
                   "cache_write_tokens", "reasoning_tokens", "task_duration_median", "task_duration_p95",
                   "total_duration_median", "total_duration_p95", "trajectory_observed", "trajectory_unknown",
                   "trial_instability_cases"]
        return [
            ScalarResult(title="all_attempts", value=summary["all_attempts"]),
            ScalarResult(title="scored", value=summary["scored"]),
            ScalarResult(title="correct", value=summary["correct"]),
            TableResult(title="Corsair strata", description="All attempts include task failures; smoke scores are wiring only.",
                        columns=columns, rows=[[row.get(column) for column in columns] for row in rows]),
        ]


def _truth(case: Any) -> str | None:
    expected = case.expected_output
    if expected == "vulnerable":
        return "positive"
    if expected == "safe_in_scope":
        return "negative"
    return None


def _status_bucket(output: str) -> str:
    if output in {"unknown", "unknown_absence", "inconclusive"}:
        return "abstained"
    if output in {"unsupported", "unqualified", "cancelled", "failed_platform"}:
        return "blocked"
    return "scored"


def _correct(case: Any) -> bool | None:
    assertion = case.assertions.get("EqualsExpected")
    return assertion.value if assertion is not None and isinstance(assertion.value, bool) else None


def _case_bucket(case: Any) -> str:
    category = _status_bucket(case.output)
    required = ("OutputDomain", "GroundedCitations", "EvidenceBackedDisposition")
    if category == "scored" and any(name not in case.assertions or case.assertions[name].value is not True for name in required):
        return "blocked"
    return category


def evaluator_policy_identity() -> str:
    """Freeze the actual evaluation implementation, not only a hand-written label."""
    return "corsair.v2.evaluation.v1:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def report_summary(report: EvaluationReport, group_by: tuple[str, ...] = ("language", "framework", "cwe", "agent", "model")) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Calculate complete-denominator report data without dropping failures."""
    group: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    usage_fields = ("requests", "tools", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")
    def bucket(metadata: dict[str, Any] | None) -> dict[str, Any]:
        values = metadata or {}
        cwes = values.get("cwe", [])
        cwe = (",".join(cwes) if isinstance(cwes, list) and cwes else "not_applicable") if "cwe" in group_by else "all"
        key = (str(values.get("language", "unknown")) if "language" in group_by else "all",
               str(values.get("framework", "unknown")) if "framework" in group_by else "all", cwe,
               str(values.get("agent", "unknown")) if "agent" in group_by else "all",
               str(values.get("model", "unknown")) if "model" in group_by else "all")
        return group.setdefault(key, {"language": key[0], "framework": key[1], "cwe": key[2], "agent": key[3],
                                      "model": key[4], "all_attempts": 0, "scored": 0, "correct": 0,
                                      "abstained": 0, "blocked": 0, "task_errors": 0, "evaluator_errors": 0,
                                      "true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0,
                                      "trajectory_observed": 0, "trajectory_unknown": 0,
                                      "_usage": {field: [] for field in usage_fields}, "_task_durations": [],
                                      "_total_durations": [], "_statuses": {}})
    for case in report.cases:
        row = bucket(case.metadata)
        row["all_attempts"] += 1
        category = _case_bucket(case)
        row[category] += 1 if category in {"abstained", "blocked"} else 0
        if category == "scored":
            row["scored"] += 1
        correct = _correct(case)
        if correct and category == "scored":
            row["correct"] += 1
        row["evaluator_errors"] += len(case.evaluator_failures)
        envelope = case.attributes.get("usage_snapshot", {})
        aggregate = envelope.get("aggregate", {}) if isinstance(envelope, dict) else {}
        for field, envelope_field in (("requests", "requests"), ("tools", "tool_calls"),
                                      ("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                                      ("cache_read_tokens", "cache_read_tokens"), ("cache_write_tokens", "cache_write_tokens"),
                                      ("reasoning_tokens", "reasoning_tokens")):
            row["_usage"][field].append(aggregate.get(envelope_field))
        row["_task_durations"].append(case.task_duration)
        row["_total_durations"].append(case.total_duration)
        if case.attributes.get("trajectory_observed") is True:
            row["trajectory_observed"] += 1
        else:
            row["trajectory_unknown"] += 1
        source_name = case.source_case_name or case.name
        row["_statuses"].setdefault(source_name, set()).add(case.output)
        truth = _truth(case)
        if category != "scored":
            continue
        if truth == "positive":
            if case.output == "vulnerable": row["true_positive"] += 1
            elif category == "scored": row["false_negative"] += 1
        elif truth == "negative":
            if case.output == "vulnerable": row["false_positive"] += 1
            elif category == "scored": row["true_negative"] += 1
    for failure in report.failures:
        row = bucket(failure.metadata)
        row["all_attempts"] += 1
        row["task_errors"] += 1
        for field in usage_fields:
            row["_usage"][field].append(None)
        source_name = failure.source_case_name or failure.name
        row["_statuses"].setdefault(source_name, set()).add("task_error")
    rows = []
    for row in group.values():
        row["correct_all"] = row["correct"] / row["all_attempts"] if row["all_attempts"] else None
        row["correct_scored"] = row["correct"] / row["scored"] if row["scored"] else None
        row["coverage"] = row["scored"] / row["all_attempts"] if row["all_attempts"] else None
        for field, values in row.pop("_usage").items():
            row[field] = sum(values) if values and all(value is not None for value in values) else None
            known = [value for value in values if value is not None]
            row[field + "_known_sum"] = sum(known) if known else None
            row[field + "_known_attempts"] = len(known)
            row[field + "_unknown_attempts"] = row["all_attempts"] - len(known)
        task_durations = sorted(row.pop("_task_durations"))
        total_durations = sorted(row.pop("_total_durations"))
        def quantile(values: list[float], percentile: float) -> float | None:
            return values[max(0, int(__import__("math").ceil(len(values) * percentile) - 1))] if values else None
        from statistics import median
        row["task_duration_median"] = median(task_durations) if task_durations else None
        row["task_duration_p95"] = quantile(task_durations, 0.95)
        row["total_duration_median"] = median(total_durations) if total_durations else None
        row["total_duration_p95"] = quantile(total_durations, 0.95)
        row["trial_instability_cases"] = sum(1 for statuses in row.pop("_statuses").values() if len(statuses) > 1)
        rows.append(row)
    rows.sort(key=lambda row: (row["language"], row["framework"], row["cwe"], row["agent"], row["model"]))
    totals = {field: sum(row[field] for row in rows) for field in ("all_attempts", "scored", "correct", "abstained", "blocked", "task_errors", "evaluator_errors", "true_positive", "true_negative", "false_positive", "false_negative")}
    totals["correct_all"] = totals["correct"] / totals["all_attempts"] if totals["all_attempts"] else None
    totals["correct_scored"] = totals["correct"] / totals["scored"] if totals["scored"] else None
    totals["coverage"] = totals["scored"] / totals["all_attempts"] if totals["all_attempts"] else None
    for field in usage_fields:
        totals[field] = sum(row[field] for row in rows) if rows and all(row[field] is not None for row in rows) else None
        known = [row[field + "_known_sum"] for row in rows if row[field + "_known_sum"] is not None]
        totals[field + "_known_sum"] = sum(known) if known else None
        totals[field + "_known_attempts"] = sum(row[field + "_known_attempts"] for row in rows)
        totals[field + "_unknown_attempts"] = sum(row[field + "_unknown_attempts"] for row in rows)
    for row in [totals, *rows]:
        tp, tn, fp, fn = (row[key] for key in ("true_positive", "true_negative", "false_positive", "false_negative"))
        row["precision"] = tp / (tp + fp) if tp + fp else None
        row["recall"] = tp / (tp + fn) if tp + fn else None
        row["specificity"] = tn / (tn + fp) if tn + fp else None
        row["false_positive_rate"] = fp / (fp + tn) if fp + tn else None
        row["false_negative_rate"] = fn / (fn + tp) if fn + tp else None
        row["f1"] = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
        row["balanced_accuracy"] = (row["recall"] + row["specificity"]) / 2 if row["recall"] is not None and row["specificity"] is not None else None
    return totals, rows


async def evaluate_dataset(dataset: Dataset, config: OperatorConfig, output_dir: Any, mode: Literal["source", "run"] = "source",
                           repeat: int = 1, max_concurrency: int = 1,
                           task: Callable[[AnalysisInput | RunSpec], str | AnalysisResult | RunResult | Awaitable[str | AnalysisResult | RunResult]] | None = None) -> EvaluationReport:
    """Evaluate a typed native Dataset through the production runtime or test injection.

    The production call contract for parent integration is exactly:
    ``corsair.v2.runtime.analyze_case(inputs, config)`` for ``source`` and
    ``corsair.v2.engine.run(spec, config)`` for ``run``.  ``task`` exists only
    for deterministic unit tests; it is never selected as a production fallback.
    ``output_dir`` is accepted for the CLI contract; report export is explicit
    through ``corsair.v2.reports.export_report`` so callers choose persistence.
    """
    del output_dir  # Native Evals is the runner; report export is a distinct explicit side effect.
    if mode not in ("source", "run") or repeat < 1 or max_concurrency < 1:
        raise ValueError("mode must be source/run and repeat/max_concurrency must be positive")
    _configure_local_telemetry()
    actual_config_identity = config_identity(config)
    actual_build_identity = build_identity()
    profile_hashes = {
        role: digest(config.model_for(role))
        for role in ("analysis", "investigator", "control_author", "exploit_author", "validity", "repair")
    }
    profile_hashes["sandbox"] = digest(config.sandbox)

    async def runner(inputs: AnalysisInput | RunSpec) -> str:
        actual_inputs: AnalysisInput | RunSpec = inputs
        trial_id = uuid4().hex
        attempt_request_id = f"eval-{uuid4().hex}"
        set_eval_attribute("trial_id", trial_id)
        set_eval_attribute("attempt_request_id", attempt_request_id)
        if mode == "run":
            if not isinstance(inputs, RunSpec):
                raise TypeError("run evaluation requires RunSpec inputs")
            # Evals repeats call this same native task again.  Request IDs are
            # engine idempotency keys, so a fresh opaque ID is mandatory for an
            # independent inference/effect attempt rather than a cached result.
            logical_case_id = inputs.request_id
            actual_inputs = inputs.model_copy(update={"request_id": attempt_request_id})
            set_eval_attribute("logical_case_id", logical_case_id)
        else:
            set_eval_attribute("logical_case_id", digest(inputs))
        if task is None:
            if mode == "source":
                from .runtime import analyze_case  # parent-owned production seam
                raw = analyze_case(actual_inputs, config, attempt_id=attempt_request_id)  # type: ignore[arg-type]
            else:
                from .engine import run  # parent-owned production seam
                raw = run(actual_inputs, config)  # type: ignore[arg-type]
        else:
            raw = task(actual_inputs)
        result = await raw if inspect.isawaitable(raw) else raw
        if isinstance(result, AnalysisResult):
            if mode != "source":
                raise TypeError("run evaluation task returned AnalysisResult")
            return _analysis_projection(inputs, result)  # type: ignore[arg-type]
        if isinstance(result, RunResult):
            if mode != "run":
                raise TypeError("source evaluation task returned RunResult")
            return _run_projection(result, config)
        if isinstance(result, str):
            # Deterministic injection has no provider receipt; explicitly preserve
            # missing usage rather than turning it into zero in native metrics.
            _record_usage((), terminal_status=result, evidence_status="unknown", citation_status="unknown")
            return result
        raise TypeError("Evaluation task must return str, AnalysisResult, or RunResult")

    evaluators = [EqualsExpected(), OutputDomain(), GroundedCitations(), EvidenceBackedDisposition(), DeclaredTrajectory(),
                  MaxToolCalls(config.budget.tool_calls_limit), MaxModelRequests(config.budget.request_limit)]
    metadata = {
        "mode": mode,
        "config_digest": actual_config_identity["config_sha256"],
        "config_identity": actual_config_identity,
        "build_identity": actual_build_identity,
        "native_profile_hashes": profile_hashes,
        "evaluator_policy": evaluator_policy_identity(),
        "telemetry": "local-only-logfire",
        "retry_task": "disabled; engine owns durable effects",
    }
    # Dataset owns evaluator scheduling. Copy rather than mutate a caller-owned
    # native Dataset so a reused benchmark cannot silently accumulate policies.
    evaluated = dataset.model_copy(update={
        "evaluators": [*dataset.evaluators, *evaluators],
        "report_evaluators": [*dataset.report_evaluators, CorsairStrata()],
    })
    return await evaluated.evaluate(runner, name=f"{dataset.name}-{mode}", task_name="corsair_v2_runtime",
                                    max_concurrency=max_concurrency, progress=False, repeat=repeat, metadata=metadata)
