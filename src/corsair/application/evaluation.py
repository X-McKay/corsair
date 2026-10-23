"""Evaluator-only case-set integrity, scoring and metrics; no model or sandbox effects."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

LABELS = ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE")


TELEMETRY = ("requests", "input_tokens", "output_tokens", "tool_calls", "bash_calls", "duration_s")


LITE_CONTRACT: dict[str, tuple[frozenset[str] | None, str]] = {
    "ineffective-fix": (
        frozenset({"LIKELY_EXPLOITABLE"}),
        "a non-working fix keeps LIKELY_EXPLOITABLE with fix=not_verified; v2 expected INCONCLUSIVE",
    ),
    "bare-tree-no-manifest": (None, "Python trees with no manifest are accepted; v2 expected UNABLE_TO_RUN"),
}


def _load_set(path: Path) -> tuple[list[Path], bool]:
    """Case directories of a frozen set file, and its held-out flag. Keys are relative to ``evals/e2e``; a case whose
    oracle no longer matches the digest recorded at freeze time is refused, so a relabelled case cannot slip in."""
    data = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent.parent
    dirs = []
    for key, digest in data["cases"].items():
        oracle = root / key / "oracle.json"
        if hashlib.sha256(oracle.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"{path}: the oracle for {key} changed since the set was frozen")
        dirs.append(root / key)
    return dirs, bool(data.get("held_out"))


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _telemetry(rows: list[dict], key: str) -> dict:
    """Totals over the runs that reported the field. A field no run reported is unknown (total None), never zero."""
    values = [row[key] for row in rows if row.get(key) is not None]
    total = sum(values) if values else None
    return {
        "reported_runs": len(values),
        "runs": len(rows),
        "total": total,
        "mean": _rate(total, len(values)) if values else None,
    }


def summarise(rows: list[dict]) -> dict:
    """Accuracy, per-label precision and recall, the INCONCLUSIVE rate and usage over per-run rows. Accuracy uses the
    oracle's accepted labels (``correct``); precision and recall use its ``expected_label`` as the truth, and rows
    without one are left out of them."""
    scored = [row for row in rows if row["correct"] is not None]
    truthed = [row for row in rows if row["expected_label"]]
    per_label = {}
    for label in LABELS:
        tp = sum(1 for r in truthed if r["expected_label"] == label and r["label"] == label)
        fp = sum(1 for r in truthed if r["expected_label"] != label and r["label"] == label)
        fn = sum(1 for r in truthed if r["expected_label"] == label and r["label"] != label)
        per_label[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _rate(tp, tp + fp),
            "recall": _rate(tp, tp + fn),
        }
    counts = Counter(row["label"] for row in rows)
    correct = sum(1 for r in scored if r["correct"])
    return {
        "runs": len(rows),
        "scored_runs": len(scored),
        "correct_runs": correct,
        "accuracy": _rate(correct, len(scored)),
        "forbidden_hits": sum(1 for r in rows if r["forbidden_hit"]),
        "per_label": per_label,
        "label_counts": dict(sorted(counts.items())),
        "inconclusive_rate": _rate(counts.get("INCONCLUSIVE", 0), len(rows)),
        "telemetry": {key: _telemetry(rows, key) for key in TELEMETRY},
    }


def per_case(rows: list[dict]) -> list[dict]:
    """Per case over its repeats: label counts, the modal label and agreement (share of runs on the modal label)."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["case"], []).append(row)
    out = []
    for case, group in groups.items():
        counts = Counter(row["label"] for row in group)
        modal, modal_count = counts.most_common(1)[0]
        scored = [row for row in group if row["correct"] is not None]
        out.append(
            {
                "case": case,
                "case_id": group[0]["case_id"],
                "expected_label": group[0]["expected_label"],
                "runs": len(group),
                "label_counts": dict(sorted(counts.items())),
                "modal_label": modal,
                "agreement": modal_count / len(group),
                "scored_runs": len(scored),
                "accuracy": _rate(sum(1 for r in scored if r["correct"]), len(scored)),
            }
        )
    return out


def score(name: str, oracle: dict, label: str) -> tuple[bool | None, bool, str | None]:
    """(correct, forbidden hit, policy note) for one case. ``correct`` is None when the oracle accepts no label or the
    case is not scored. An oracle's ``acceptable_labels`` (default: ``expected_label``) decide correctness, so a safe
    case is correct with LIKELY_NOT_EXPLOITABLE; ``forbidden_labels`` are the labels that would be a false positive."""
    expected = oracle.get("expected_label")
    accepted = set(oracle.get("acceptable_labels") or ([expected] if expected else []))
    forbidden = set(oracle.get("forbidden_labels") or [])
    note = None
    if name in LITE_CONTRACT:
        lite_accepted, note = LITE_CONTRACT[name]
        accepted, forbidden = set(lite_accepted or ()), set()
    return (label in accepted) if accepted else None, label in forbidden, note


def _ledger(rows: list[dict]) -> dict[str, int]:
    ledger: dict[str, int] = {}
    for row in rows:
        for gate in row["gates"]:
            ledger[gate] = ledger.get(gate, 0) + 1
    return dict(sorted(ledger.items()))
