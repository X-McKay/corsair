"""summary.json and policy.json for a v2 agent eval run (schema ``corsair-eval-summary/v1``).

``summarize`` reads the runner's ``attempts.jsonl`` and ``configuration.json`` and rolls attempts up overall, by
language and by case kind: per dimension passed/total, clean attempts, and efficiency (mean, p50, p90, total) over
observed samples only. A metric no attempt reported has ``observed: 0`` and null statistics, never zero; ``total``
is null when any attempt left it unreported (a sum with an unknown in it is unknown). Metric and parameter names
follow the run record (``corsair-v2-run/1``, ``src/corsair/v2/RUN_RECORD.md``).

``apply_policy`` reads the agent's ``evals/release-policy.yaml`` and reports pass, fail or unknown per entry. While
gates are deferred it never changes the run's exit code. An entry whose threshold is null is ``not_set``; an entry
whose metric was not observed, or a run missing required provenance, is ``unknown``, never ``pass``.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any

import yaml

SCHEMA = "corsair-eval-summary/v1"
METRICS = ("wall_s", "requests", "tool_calls", "input_tokens", "output_tokens", "tokens", "retries")
# Chain dispositions (contracts.Label). Decisive = one of the two exploitability labels; abstentions are reported as
# their own rates by terminal reason so they are never hidden inside accuracy.
DECISIVE = ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE")
ABSTAIN = ("INCONCLUSIVE", "UNABLE_TO_RUN", "ERROR")


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(0.9 * len(ordered) + 0.5) - 1))]


def _stats(values: list[float | None]) -> dict:
    seen = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not seen:
        return {"observed": 0, "mean": None, "p50": None, "p90": None, "total": None}
    return {"observed": len(seen), "mean": round(mean(seen), 3), "p50": round(median(seen), 3),
            "p90": round(_p90(seen), 3), "total": round(sum(seen), 3) if len(seen) == len(values) else None}


def _parameters(rows: list[dict]) -> dict:
    """Per parameter, the distinct values the attempts ran with (null kept: unknown), so runs compare by setting."""
    names = sorted({name for row in rows for name in row.get("parameters") or {}})
    return {name: sorted({json.dumps((row.get("parameters") or {}).get(name)) for row in rows}) for name in names}


def _statuses(rows: list[dict]) -> dict:
    """Run-record statuses only; an attempt that never reported one (the task raised) is counted apart."""
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("status") is not None:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
    return dict(sorted(counts.items()))


def dispositions(rows: list[dict]) -> dict | None:
    """Rows carrying ``label`` (chain runs): decisive rate, accuracy per expected label, abstention rates by
    terminal reason. None when no row has a label (agent runs)."""
    labelled = [row for row in rows if row.get("label") is not None]
    if not labelled:
        return None
    total = len(labelled)
    decisive = [row for row in labelled if row["label"] in DECISIVE]
    per_label = {}
    for label in sorted({row.get("expected_label") for row in labelled} - {None}):
        expected = [row for row in labelled if row.get("expected_label") == label]
        per_label[label] = {"passed": sum(row["label"] == label for row in expected), "total": len(expected)}
    abstentions = {}
    for label in ABSTAIN:
        hits = [row for row in labelled if row["label"] == label]
        reasons: dict[str, int] = {}
        for row in hits:
            reasons[str(row.get("terminal_reason"))] = reasons.get(str(row.get("terminal_reason")), 0) + 1
        abstentions[label] = {"count": len(hits), "rate": round(len(hits) / total, 4),
                              "by_terminal_reason": dict(sorted(reasons.items()))}
    return {"runs": total, "decisive": len(decisive), "decisive_rate": round(len(decisive) / total, 4),
            "decisive_correct": sum(row["label"] == row.get("expected_label") for row in decisive),
            "accuracy_by_expected_label": per_label, "abstentions": abstentions}


def rollup(rows: list[dict]) -> dict:
    dimensions: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, value in row["dimensions"].items():
            entry = dimensions.setdefault(name, {"passed": 0, "total": 0})
            entry["passed"] += int(value)
            entry["total"] += 1
    # New receipts distinguish task failure from evaluator failure. Older rows cannot prove which failed:
    # retain their legacy task_failures count below, but do not manufacture completion coverage for them.
    task_failures = sum(row.get("failure_kind") == "task" for row in rows)
    evaluator_failures = sum(row.get("failure_kind") == "evaluator" for row in rows)
    unknown_failures = sum(row.get("failure") is not None and row.get("failure_kind") is None for row in rows)
    # Old receipts only: retain the legacy task count; those same failures remain unattributed in completion.
    legacy_task_failures = sum(row["failure"] is not None and not row["assertions"]
                              and row.get("failure_kind") is None for row in rows)
    completed = len(rows) - task_failures if not unknown_failures else None
    return {"cases": len({row["case"] for row in rows}), "attempts": len(rows),
            "clean_attempts": sum(row["passed"] for row in rows),
            "task_failures": task_failures + legacy_task_failures,
            "completion": {"attempted": len(rows), "completed": completed, "task_failures": task_failures,
                           "evaluator_failures": evaluator_failures, "unknown_failures": unknown_failures,
                           "rate": completed / len(rows) if completed is not None and rows else None},
            "dimensions": dict(sorted(dimensions.items())),
            **({"dispositions": found} if (found := dispositions(rows)) is not None else {}),
            **({"revisions": _stats([row.get("revisions") for row in rows]),
                "accepted_within_limit": {"passed": sum(row["accepted_within_limit"] is True for row in rows),
                                          "total": sum(row.get("accepted_within_limit") is not None for row in rows)}}
               if any(row.get("revisions") is not None for row in rows) else {}),
            "statuses": _statuses(rows), "status_unreported": sum(row.get("status") is None for row in rows),
            "parameters": {k: [json.loads(v) for v in vs]
                                                        for k, vs in _parameters(rows).items()},
            **{metric: _stats([row.get(metric) for row in rows]) for metric in METRICS}}


def summarize(evidence: Path, *, agent: str, set_name: str, language: str | None, mode: str, run: str,
              command: dict) -> dict:
    configuration = json.loads((evidence / "configuration.json").read_text()) \
        if (evidence / "configuration.json").exists() else {}
    path = evidence / "attempts.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()[1:]] if path.exists() else None
    record = {"schema": SCHEMA, "agent": agent, "set": set_name, "language": language, "mode": mode, "run": run,
              "identity": {"git_commit": command.get("git_commit"), "git_dirty": command.get("git_dirty"),
                           **{k: v for k, v in configuration.items() if k not in ("dimensions",)}}}
    if rows is None:
        return record | {"attempts": None, "rollups": None, "report": "missing"}
    groups: dict[str, dict[str, list[dict]]] = {"by_language": {}, "by_kind": {}}
    for row in rows:
        groups["by_language"].setdefault(row["language"], []).append(row)
        groups["by_kind"].setdefault(str(row.get("kind")), []).append(row)
    return record | {"attempts": rows, "rollups": {
        "all": rollup(rows),
        **{name: {key: rollup(items) for key, items in sorted(group.items())} for name, group in groups.items()}}}


def _rate(entry: dict | None) -> float | None:
    return None if not entry or not entry["total"] else entry["passed"] / entry["total"]


def _judge(value: float | None, limit: float | None, kind: str) -> dict:
    if limit is None:
        return {"status": "not_set", "value": value, "limit": None}
    if value is None:
        return {"status": "unknown", "value": None, "limit": limit}
    ok = value >= limit if kind == "min" else value <= limit
    return {"status": "pass" if ok else "fail", "value": round(value, 4), "limit": limit}


def apply_policy(summary: dict, policy_path: Path) -> dict:
    """Pass, fail, unknown or not_set per policy entry; ``deferred`` while gates do not decide the exit code."""
    if not policy_path.exists():
        return {"policy": None, "status": "missing"}
    policy = yaml.safe_load(policy_path.read_text())
    rollups = summary.get("rollups") or {}
    overall = rollups.get("all") or {}
    rows = summary.get("attempts") or []
    entries: dict[str, dict] = {}
    applies = policy.get("applies_to") or {}
    sets = applies.get("sets") or []
    in_scope = (not sets or summary["set"] in sets) and applies.get("mode", summary["mode"]) == summary["mode"]
    if not in_scope:
        return {"policy": str(policy_path), "schema_version": policy.get("schema_version"), "in_scope": False,
                "deferred": True, "status": "not_applicable", "missing_provenance": [], "entries": {}}
    hard = policy.get("hard_gates") or {}
    if "completion_rate" in hard:
        entries["hard_gates.completion_rate"] = _judge((overall.get("completion") or {}).get("rate"),
                                                      hard["completion_rate"], "min")
    if "evaluator_failures" in hard:
        completion = overall.get("completion") or {}
        entries["hard_gates.evaluator_failures"] = _judge(
            completion.get("evaluator_failures") if completion.get("unknown_failures") == 0 else None,
            hard["evaluator_failures"], "max")
    if "contract_rate" in hard:
        entries["hard_gates.contract_rate"] = _judge(_rate((overall.get("dimensions") or {}).get("contract")),
                                                     hard["contract_rate"], "min")
    if "safety_failures" in hard:
        safety = (overall.get("dimensions") or {}).get("safety")
        entries["hard_gates.safety_failures"] = _judge(
            None if safety is None else safety["total"] - safety["passed"], hard["safety_failures"], "max")
    if "budget_exhausted_count" in hard:
        statuses = [row.get("status") for row in rows]
        entries["hard_gates.budget_exhausted_count"] = _judge(
            None if not rows or any(s is None for s in statuses) else statuses.count("budget_exhausted"),
            hard["budget_exhausted_count"], "max")
    thresholds = policy.get("thresholds") or {}
    for dimension, rule in (thresholds.get("accuracy") or {}).items():
        entries[f"accuracy.{dimension}"] = _judge(_rate((overall.get("dimensions") or {}).get(dimension)),
                                                  rule.get("min"), "min")
        for language, limit in (rule.get("by_language") or {}).items():
            group = ((rollups.get("by_language") or {}).get(language) or {}).get("dimensions") or {}
            entries[f"accuracy.{dimension}.{language}"] = _judge(_rate(group.get(dimension)), limit, "min")
    labels = overall.get("dispositions")
    for name in ("decisive_rate", "inconclusive_rate", "unable_to_run_rate"):
        rule = thresholds.get(name)
        if rule is None:
            continue
        kind = "min" if name == "decisive_rate" else "max"
        pick = lambda d: None if d is None else (d["decisive_rate"] if name == "decisive_rate" else
                                                 d["abstentions"][name.removesuffix("_rate").upper()]["rate"])
        entries[name] = _judge(pick(labels), rule.get(kind), kind)
        for language, limit in (rule.get("by_language") or {}).items():
            group = ((rollups.get("by_language") or {}).get(language) or {}).get("dispositions")
            entries[f"{name}.{language}"] = _judge(pick(group), limit, kind)
    for label, rule in (thresholds.get("accuracy_by_label") or {}).items():
        entry = ((labels or {}).get("accuracy_by_expected_label") or {}).get(label)
        entries[f"accuracy_by_label.{label}"] = _judge(_rate(entry), rule.get("min"), "min")
    if "clean_attempt_rate" in thresholds:
        attempts = overall.get("attempts")
        entries["clean_attempt_rate"] = _judge(overall["clean_attempts"] / attempts if attempts else None,
                                               thresholds["clean_attempt_rate"].get("min"), "min")
    for metric in METRICS:
        for bound, limit in (thresholds.get(metric) or {}).items():
            statistic, kind = bound.rsplit("_", 1)  # p90_max -> (p90, max), mean_max -> (mean, max)
            entries[f"{metric}.{bound}"] = _judge((overall.get(metric) or {}).get(statistic), limit, kind)
    identity = summary.get("identity") or {}
    missing = [name for name in policy.get("required_provenance") or () if identity.get(name) in (None, "")]
    statuses = {entry["status"] for entry in entries.values()}
    status = ("fail" if "fail" in statuses else "unknown" if "unknown" in statuses or missing
              else "pass" if statuses == {"pass"} else "not_set")
    return {"policy": str(policy_path), "schema_version": policy.get("schema_version"), "in_scope": in_scope,
            "deferred": True, "status": status, "missing_provenance": missing, "entries": entries}


def compare(current: dict, reference: dict | None, reference_id: str | None) -> str:
    """Markdown: identity changes first (they decide comparability), then dimensions and efficiency per scope."""
    lines = [f"# {current['agent']} {current['run']}", ""]
    if current.get("rollups") is None:
        return "\n".join(lines + ["Attempts missing: results and telemetry are unknown.", ""])
    now = current["rollups"]["all"]
    lines += [f"Clean attempts: {now['clean_attempts']}/{now['attempts']} (task failures {now['task_failures']})", ""]
    completion = now.get("completion")
    if completion is not None:
        lines += [f"Task completion: {completion['completed']}/{completion['attempted']}; "
                  f"evaluator failures: {completion['evaluator_failures']}; "
                  f"unattributed failures: {completion['unknown_failures']}. "
                  "Dimension rates are conditional on evaluated attempts.", ""]
    if reference is None or reference.get("rollups") is None:
        return "\n".join(lines + ["No earlier run with this set and mode; nothing to compare.", ""])
    language = current.get("language")
    before_scope = reference["rollups"]["all"] if not language or reference.get("language") == language else \
        (reference["rollups"]["by_language"].get(language) or {})
    lines += [f"Compared with {reference_id} ({reference.get('reference_kind')})"
              + (f", its {language} rollup" if language and reference.get("language") != language else "") + ".", ""]
    reference_completion = before_scope.get("completion") or {}
    if reference_completion.get("completed") is None:
        lines += ["Reference task completion: unknown (missing or unattributed completion telemetry).", ""]
    else:
        lines += [f"Reference task completion: {reference_completion['completed']}/"
                  f"{reference_completion['attempted']}.", ""]
    changed = {k: (reference["identity"].get(k), v) for k, v in current["identity"].items()
               if k not in ("git_commit", "git_dirty", "language", "repeat") and reference["identity"].get(k) != v}
    if changed:
        lines += ["## Changed identity", ""] + [f"- `{k}`: {json.dumps(a)} -> {json.dumps(b)}"
                                                for k, (a, b) in changed.items()] + [""]
    names = sorted(set(now["dimensions"]) | set(before_scope.get("dimensions") or {}))
    fmt = lambda e: "-" if not e else f"{e['passed']}/{e['total']}"
    lines += ["## Dimensions", "", "| Dimension | Before | Now |", "| --- | --- | --- |"]
    lines += [f"| {n} | {fmt((before_scope.get('dimensions') or {}).get(n))} | {fmt(now['dimensions'].get(n))} |"
              for n in names]
    lines += ["", "## Efficiency (observed samples only)", "", "| Metric | Before mean / p90 | Now mean / p90 |",
              "| --- | --- | --- |"]
    for metric in METRICS:
        b, n = before_scope.get(metric) or {}, now[metric]
        lines.append(f"| {metric} | {b.get('mean')} / {b.get('p90')} ({b.get('observed', 0)}) | "
                     f"{n['mean']} / {n['p90']} ({n['observed']}) |")
    return "\n".join(lines + ["", "Unobserved telemetry is unknown, not zero.", ""])
