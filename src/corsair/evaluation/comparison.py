"""Compare two saved evaluation reports case by case; a pure reader that never re-scores.

Rows join on ``(case_id, repeat)``. ``repeat`` is the row's own field when present
(isolated reports) and otherwise the row's ordinal among that case's rows, which
matches the deterministic case-major, repeat-minor order of a composed batch.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from corsair.evaluation.ledger import row_ledger
from corsair.evaluation.scoring import summarize

USAGE_FIELDS = ("llm_calls", "tool_calls", "input_tokens", "output_tokens", "agent_seconds")
SUMMARY_FIELDS = (
    "attempts",
    "passed",
    "failed",
    "pass_rate",
    "correctly_resolved",
    "invalid_positive_evidence",
    "forbidden_labels",
    "inconclusive",
    "operational_failures",
    "unavailable_results",
    *USAGE_FIELDS,
)
# Per-gate summary counts compared side by side: every stop, and failed rows' final stop.
LEDGER_FIELDS = ("gate_ledger", "failure_stops")


def read_report(path: Path) -> dict[str, Any]:
    """Read one saved report; its rows, when present, must be a list of objects."""
    report = json.loads(path.read_bytes())
    if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
        raise ValueError("report must contain a summary object")
    rows = report.get("rows", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("report rows must be a list of objects")
    return report


def row_label(row: dict[str, Any]) -> str | None:
    """The canonical verdict, else the disposition, an isolated match kind or intake outcome."""
    for field in ("verdict", "disposition", "match_kind", "intake"):
        value = row.get(field)
        if isinstance(value, str):
            return value
    return None


def row_stop(row: dict[str, Any]) -> str | None:
    """The gate of a row's final ledger entry: what stopped it, in one name."""
    ledger = row_ledger(row)
    gate = ledger[-1].get("gate") if ledger and isinstance(ledger[-1], dict) else None
    return gate if isinstance(gate, str) else None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _delta(baseline: object, candidate: object) -> int | float | None:
    """Candidate minus baseline; an unknown side keeps the delta unknown, never zero."""
    before, after = _number(baseline), _number(candidate)
    if before is None or after is None:
        return None
    return after - before


def _known_total(values: Iterable[object]) -> int | float | None:
    total: int | float | None = None
    for value in values:
        number = _number(value)
        if number is None:
            return None
        total = number if total is None else total + number
    return total


def _keyed_rows(report: dict[str, Any]) -> tuple[dict[tuple[str, int], dict[str, Any]], int]:
    """Index rows by (case_id, repeat); count rows that carry no case identity."""
    if not isinstance(report.get("rows"), list):
        raise ValueError("compare requires reports with per-case rows")
    keyed: dict[tuple[str, int], dict[str, Any]] = {}
    seen: dict[str, int] = {}
    unidentified = 0
    for row in report["rows"]:
        case_id = row.get("case_id")
        if not isinstance(case_id, str):
            unidentified += 1
            continue
        explicit = row.get("repeat")
        repeat = explicit if isinstance(explicit, int) and explicit >= 0 else seen.get(case_id, 0)
        seen[case_id] = seen.get(case_id, 0) + 1
        if (case_id, repeat) in keyed:
            raise ValueError(f"report repeats case {case_id} attempt {repeat}")
        keyed[(case_id, repeat)] = row
    return keyed, unidentified


def _side_summary(report: dict[str, Any]) -> dict[str, Any]:
    rows = report["rows"]
    summary = summarize(rows)
    summary["agent_seconds"] = _known_total(row.get("agent_seconds") for row in rows)
    return summary


def _identities(rows: Iterable[dict[str, Any]], field: str) -> list[str]:
    return sorted({value for row in rows if isinstance(value := row.get(field), str)})


def _family(row: dict[str, Any] | None) -> str | None:
    """The row's declared dataset family, when its report carries one."""
    value = None if row is None else row.get("family")
    return value if isinstance(value, str) else None


def _case(
    key: tuple[str, int], before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, Any]:
    """One joined case: presence, status flip, label change, forbidden labels and usage."""
    case_id, repeat = key
    baseline_pass = before is not None and before.get("status") == "pass"
    candidate_pass = after is not None and after.get("status") == "pass"
    flip = None
    if before is not None and after is not None and baseline_pass != candidate_pass:
        flip = "fail_to_pass" if candidate_pass else "pass_to_fail"
    labels = (
        row_label(before) if before is not None else None,
        row_label(after) if after is not None else None,
    )
    new_forbidden = (
        after is not None
        and after.get("forbidden_label") is True
        and (before is None or before.get("forbidden_label") is not True)
    )
    presence = "candidate_only" if before is None else "baseline_only" if after is None else "both"
    stops = (
        row_stop(before) if before is not None else None,
        row_stop(after) if after is not None else None,
    )
    return {
        "case_id": case_id,
        "repeat": repeat,
        "family": _family(after) or _family(before),
        "presence": presence,
        "baseline_status": before.get("status") if before else None,
        "candidate_status": after.get("status") if after else None,
        "baseline_label": labels[0],
        "candidate_label": labels[1],
        "label_changed": before is not None and after is not None and labels[0] != labels[1],
        "baseline_stop": stops[0],
        "candidate_stop": stops[1],
        "flip": flip,
        "new_forbidden_label": new_forbidden,
        "usage_delta": {
            field: _delta((before or {}).get(field), (after or {}).get(field))
            for field in USAGE_FIELDS
        },
    }


def _gate_delta(baseline: object, candidate: object) -> list[dict[str, Any]]:
    """Per-gate counts on both sides; moved gates first by size, then by name."""
    before = baseline if isinstance(baseline, Mapping) else {}
    after = candidate if isinstance(candidate, Mapping) else {}
    entries = [
        {
            "gate": gate,
            "baseline": before.get(gate, 0),
            "candidate": after.get(gate, 0),
            "delta": after.get(gate, 0) - before.get(gate, 0),
        }
        for gate in before.keys() | after.keys()
    ]
    return sorted(entries, key=lambda entry: (-abs(entry["delta"]), entry["gate"]))


def _regressions(cases: list[dict[str, Any]], unidentified: dict[str, int]) -> list[dict]:
    """A pass that stops passing, a new forbidden label, or a lost case regresses."""
    found: list[dict[str, Any]] = []
    for case in cases:
        identity = {"case_id": case["case_id"], "repeat": case["repeat"], "family": case["family"]}
        if case["flip"] == "pass_to_fail":
            found.append({**identity, "reason": "pass_to_fail"})
        if case["new_forbidden_label"]:
            found.append({**identity, "reason": "new_forbidden_label"})
        if case["presence"] == "baseline_only":
            found.append({**identity, "reason": "missing_in_candidate"})
    if unidentified["candidate"] > unidentified["baseline"]:
        found.append(
            {"case_id": None, "repeat": None, "family": None, "reason": "unidentified_rows"}
        )
    return found


def compare_reports(
    baseline: dict[str, Any], candidate: dict[str, Any], *, allow_dataset_mismatch: bool = False
) -> dict[str, Any]:
    """Join two reports by case and repeat and decide whether the candidate regressed.

    Reports over different (or undeclared) frozen dataset digests are refused unless
    the caller explicitly allows the mismatch. Such a result is ``comparable: false`` with
    ``regression: None``: its per-case changes and deltas are descriptive only, never a
    regression verdict either way."""
    digests = {
        "baseline": baseline.get("dataset_digest"),
        "candidate": candidate.get("dataset_digest"),
    }
    dataset_match = digests["baseline"] is not None and digests["baseline"] == digests["candidate"]
    if not dataset_match and not allow_dataset_mismatch:
        raise ValueError(
            "reports cover different or undeclared dataset digests "
            f"(baseline={digests['baseline']}, candidate={digests['candidate']}); "
            "pass --allow-dataset-mismatch to compare them anyway"
        )
    before, before_unidentified = _keyed_rows(baseline)
    after, after_unidentified = _keyed_rows(candidate)
    unidentified = {"baseline": before_unidentified, "candidate": after_unidentified}
    keys = sorted(before.keys() | after.keys())
    cases = [_case(key, before.get(key), after.get(key)) for key in keys]
    regressions = _regressions(cases, unidentified)
    summaries = {"baseline": _side_summary(baseline), "candidate": _side_summary(candidate)}
    return {
        "comparable": dataset_match,
        "regression": bool(regressions) if dataset_match else None,
        "dataset_match": dataset_match,
        "dataset_digest": digests,
        "config_digests": {
            side: _identities(report["rows"], "config_digest")
            for side, report in (("baseline", baseline), ("candidate", candidate))
        },
        "cohorts": {
            side: _identities(report["rows"], "cohort")
            for side, report in (("baseline", baseline), ("candidate", candidate))
        },
        "summary_delta": {
            field: {
                "baseline": summaries["baseline"].get(field),
                "candidate": summaries["candidate"].get(field),
                "delta": _delta(
                    summaries["baseline"].get(field), summaries["candidate"].get(field)
                ),
            }
            for field in SUMMARY_FIELDS
        },
        # Gate movement attributes a change; it never decides a regression.
        "gate_delta": {
            field: _gate_delta(summaries["baseline"].get(field), summaries["candidate"].get(field))
            for field in LEDGER_FIELDS
        },
        "counts": {
            "joined": sum(case["presence"] == "both" for case in cases),
            "pass_to_fail": sum(case["flip"] == "pass_to_fail" for case in cases),
            "fail_to_pass": sum(case["flip"] == "fail_to_pass" for case in cases),
            "label_changed": sum(case["label_changed"] for case in cases),
            "new_forbidden_labels": sum(case["new_forbidden_label"] for case in cases),
            "missing_in_candidate": sum(case["presence"] == "baseline_only" for case in cases),
            "new_in_candidate": sum(case["presence"] == "candidate_only" for case in cases),
        },
        "unidentified_rows": unidentified,
        "regressions": regressions,
        "cases": cases,
    }
