"""GitHub-flavoured Markdown for saved evaluation reports and comparisons; presentation only.

Every function takes the JSON-mode dictionary that ``corsair report``, ``corsair compare``,
``eval`` or ``rescore`` emits and returns text; none reads a file, re-scores or decides
anything. The stable entry points are :func:`report_markdown`, :func:`comparison_markdown` and
the dispatcher :func:`to_markdown`.

A report or comparison record is meant to be committed or pasted, so it carries identity and
the baseline-policy caveats, and it never carries free text a model may have written: a row's
``reason`` can be an auditor's review or a producer's abstention, so rows show only their
code-chosen stopping gate.
Unknown values stay ``unknown``, never zero. Every cell is sanitized and escaped, so a pipe or a
newline in a report cannot break a table.
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from corsair.evaluation.comparison import row_label
from corsair.observability.logging import safe_text

# Row fields that identify what produced a row; the model fields appear only when a report
# records them.
_MODEL_FIELDS = ("model", "producer_model", "auditor_model")
_USAGE_COLUMNS = (
    ("llm_calls", "LLM calls"),
    ("tool_calls", "Tool calls"),
    ("input_tokens", "Input tokens"),
    ("output_tokens", "Output tokens"),
    ("agent_seconds", "Agent s"),
)
_SIDES = ("baseline", "candidate")
_ESCAPED = "\\`*_[]<>|~"
_POLICY_CAVEAT = (
    "> Candidate diagnostic, not a promoted baseline: it makes no population accuracy, "
    "false-positive, clearance or production-readiness claim (see the baseline policy, "
    "`evals/baselines/README.md`)."
)
_UNRUN_CAVEAT = (
    "> Unknown usage is `unknown`, never zero. A gate this record does not show as run "
    "(Docker, Temporal, live model or full chain) is unrun, not passed."
)
_ISOLATED_CAVEAT = (
    "> Isolated agent diagnostic (`live-model-fixture`): one role ran on frozen inputs; "
    "no target code, Docker sandbox, Temporal workflow or full chain ran."
)
_COMPARISON_CAVEAT = (
    "> A candidate with no regression on one frozen cohort is not a promoted baseline."
)
_MISMATCH_CAVEAT = (
    "> **Dataset mismatch:** the dataset digests differ or are undeclared; this is not a "
    "comparison on one frozen dataset."
)


def _text(value: object) -> str:
    """Sanitized text with Markdown and table syntax escaped; ``None`` is ``unknown``."""
    if value is None:
        return "unknown"
    text = safe_text(value)
    return "".join(f"\\{char}" if char in _ESCAPED else char for char in text)


def _code(value: object) -> str:
    """An identifier as a code span; pipes stay escaped so a table cell cannot split."""
    if value is None:
        return "unknown"
    text = safe_text(value).replace("`", "'").replace("|", "\\|")
    return f"`{text}`" if text.strip() else "unknown"


def _number(value: object) -> str:
    if isinstance(value, float):
        return str(round(value, 4))
    return _text(value)


def _signed(value: object) -> str:
    """A delta with its sign; an unknown delta is never shown as zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "unknown"
    return f"{round(value, 4):+}"


def _codes(values: Iterable[object]) -> str:
    shown = [_code(value) for value in values]
    return ", ".join(shown) if shown else "unknown"


def _table(header: Iterable[str], rows: Iterable[Iterable[str]], numeric: int = 0) -> list[str]:
    """A GFM table; the last ``numeric`` columns are right-aligned."""
    names = list(header)
    align = ["---"] * (len(names) - numeric) + ["---:"] * numeric
    lines = [f"| {' | '.join(names)} |", f"| {' | '.join(align)} |"]
    lines += [f"| {' | '.join(row)} |" for row in rows]
    return lines


def _distinct(rows: Iterable[Mapping[str, Any]], fields: Iterable[str]) -> list[str]:
    names = tuple(fields)
    return sorted(
        {value for row in rows for name in names if isinstance(value := row.get(name), str)}
    )


def _rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _stop(row: Mapping[str, Any]) -> str:
    """The row's final gate-ledger gate, else its isolated feedback gate; never a reason."""
    ledger = row.get("gate_ledger")
    if isinstance(ledger, list) and ledger and isinstance(ledger[-1], Mapping):
        return _code(ledger[-1].get("gate"))
    feedback = row.get("feedback")
    if isinstance(feedback, Mapping):
        return _code(feedback.get("gate"))
    return "none"


def _status(row: Mapping[str, Any]) -> str:
    detail = _text(row.get("status"))
    execution = row.get("execution_status")
    if execution not in {None, "COMPLETED"}:
        detail += f" · {_text(execution)}"
    return detail


def _identity_lines(report: Mapping[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    items = [
        ("Dataset digest", _code(report.get("dataset_digest"))),
        ("Config digests", _codes(_distinct(rows, ("config_digest",)))),
        ("Models", _codes(_distinct(rows, _MODEL_FIELDS))),
    ]
    optional = (
        ("Agent resources digests", ("agent_resources_digest",)),
        ("Agents", ("agent",)),
        ("Cohorts", ("cohort",)),
    )
    for name, fields in optional:
        if found := _distinct(rows, fields):
            items.append((name, _codes(found)))
    if isinstance(report.get("report"), str):
        items.append(("Report", _code(report["report"])))
    return ["### Identity", "", *_table(("Item", "Value"), items)]


def _summary_lines(summary: Mapping[str, Any]) -> list[str]:
    scalars = [
        (_text(key.replace("_", " ")), _number(value))
        for key, value in summary.items()
        if not isinstance(value, Mapping)
    ]
    return ["### Summary", "", *_table(("Metric", "Value"), scalars, numeric=1)]


def _counts_lines(title: str, counts: object) -> list[str]:
    if not isinstance(counts, Mapping):
        return []
    if not counts:
        return [f"### {title}", "", "None recorded."]
    rows = [(_code(gate), _number(count)) for gate, count in counts.items()]
    return [f"### {title}", "", *_table(("Gate", "Count"), rows, numeric=1)]


def _case_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    seen: dict[object, int] = {}
    body = []
    for row in rows:
        case_id = row.get("case_id")
        explicit = row.get("repeat")
        ordinal = seen.get(case_id, 0)
        seen[case_id] = ordinal + 1
        repeat = explicit if isinstance(explicit, int) else ordinal
        repeat = ordinal if isinstance(repeat, bool) else repeat
        body.append(
            (
                _code(case_id),
                _number(repeat),
                _code(row.get("run_id")),
                _status(row),
                _code(row_label(row)),
                _stop(row),
                *(_number(row.get(field)) for field, _ in _USAGE_COLUMNS),
            )
        )
    header = ("Case", "#", "Run", "Status", "Label", "Stop", *(name for _, name in _USAGE_COLUMNS))
    return ["### Cases", "", *_table(header, body, numeric=len(_USAGE_COLUMNS))]


def _sections(*sections: list[str]) -> str:
    return "\n\n".join("\n".join(lines) for lines in sections if lines) + "\n"


def report_markdown(report: Mapping[str, Any]) -> str:
    """Render a saved report (or an eval/rescore summary receipt) as a Markdown record.

    Sections: title, caveats, identity, summary, per-case table, gate ledger and failure
    stops. A bare summary mapping (``{"attempts": ...}``) is accepted as its own summary.
    """
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        summary = report
    rows = _rows(report)
    caveats = [_POLICY_CAVEAT, _UNRUN_CAVEAT]
    cohorts = _distinct(rows, ("cohort",))
    if cohorts == ["live-model-fixture"]:
        caveats.append(_ISOLATED_CAVEAT)
    return _sections(
        ["## Corsair evaluation report"],
        [line for caveat in caveats for line in (caveat, ">")][:-1],
        _identity_lines(report, rows),
        _summary_lines(summary),
        _case_lines(rows),
        _counts_lines("Gate ledger", summary.get("gate_ledger")),
        _counts_lines("Failure stops", summary.get("failure_stops")),
    )


def _side_identity(found: object) -> tuple[str, str]:
    """Baseline and candidate cells of one identity item; a digest list joins its values."""
    sides = found if isinstance(found, Mapping) else {}
    shown = [sides.get(key) for key in _SIDES]
    return (
        _codes(shown[0]) if isinstance(shown[0], list) else _code(shown[0]),
        _codes(shown[1]) if isinstance(shown[1], list) else _code(shown[1]),
    )


def _comparison_identity(value: Mapping[str, Any]) -> list[str]:
    items = []
    if "baseline_report" in value or "candidate_report" in value:
        items.append(
            ("Report", _code(value.get("baseline_report")), _code(value.get("candidate_report")))
        )
    for field, name in (
        ("dataset_digest", "Dataset digest"),
        ("config_digests", "Config digests"),
        ("cohorts", "Cohorts"),
    ):
        if field in value:
            items.append((name, *_side_identity(value[field])))
    return ["### Identity", "", *_table(("Item", "Baseline", "Candidate"), items)]


def _delta_lines(value: Mapping[str, Any]) -> list[str]:
    deltas = value.get("summary_delta")
    if not isinstance(deltas, Mapping):
        return []
    rows = [
        (
            _text(key.replace("_", " ")),
            _number(delta.get("baseline")),
            _number(delta.get("candidate")),
            _signed(delta.get("delta")),
        )
        for key, delta in deltas.items()
        if isinstance(delta, Mapping)
    ]
    header = ("Metric", "Baseline", "Candidate", "Delta")
    return ["### Summary deltas", "", *_table(header, rows, numeric=3)]


def _regression_lines(value: Mapping[str, Any]) -> list[str]:
    found = [item for item in value.get("regressions") or [] if isinstance(item, Mapping)]
    if not found:
        return ["### Regressions", "", "None."]
    lines = []
    for item in found:
        if item.get("case_id") is None:
            lines.append(f"- rows without a case identity: {_code(item.get('reason'))}")
        else:
            subject = f"{_code(item['case_id'])} #{_number(item.get('repeat'))}"
            lines.append(f"- {subject}: {_code(item.get('reason'))}")
    return ["### Regressions", "", *lines]


def _changed(case: Mapping[str, Any]) -> bool:
    return bool(
        case.get("flip")
        or case.get("label_changed")
        or case.get("new_forbidden_label")
        or case.get("presence") != "both"
    )


def _side(case: Mapping[str, Any], side: str, field: str, show: Callable[[object], str]) -> str:
    """One side's value; a side the attempt is missing from is ``absent``, not ``unknown``."""
    if case.get("presence") == ("candidate_only" if side == "baseline" else "baseline_only"):
        return "absent"
    return show(case.get(field))


def _changed_lines(value: Mapping[str, Any]) -> list[str]:
    cases = [case for case in value.get("cases") or [] if isinstance(case, Mapping)]
    changed = [case for case in cases if _changed(case)]
    if not changed:
        return ["### Changed cases", "", f"No per-case status or label changes in {len(cases)}."]
    body = []
    for case in changed:
        change = str(case.get("flip") or case.get("presence"))
        if case.get("new_forbidden_label"):
            change += " · new forbidden label"
        usage = case.get("usage_delta")
        usage = usage if isinstance(usage, Mapping) and case.get("presence") == "both" else None
        status = [_side(case, side, f"{side}_status", _text) for side in _SIDES]
        label = [_side(case, side, f"{side}_label", _code) for side in _SIDES]
        body.append(
            (
                _code(case.get("case_id")),
                _number(case.get("repeat")),
                " → ".join(status),
                " → ".join(label),
                _text(change.replace("_", " ")),
                *(
                    "-" if usage is None else _signed(usage.get(field))
                    for field, _ in _USAGE_COLUMNS
                ),
            )
        )
    header = (
        "Case",
        "#",
        "Status",
        "Label",
        "Change",
        *(f"{name} Δ" for _, name in _USAGE_COLUMNS),
    )
    return ["### Changed cases", "", *_table(header, body, numeric=len(_USAGE_COLUMNS))]


def comparison_markdown(comparison: Mapping[str, Any]) -> str:
    """Render a ``compare_reports`` result as a Markdown record.

    Sections: title and result, caveats (a dataset mismatch first), identity per side,
    counts, summary deltas, regressions and the attempts whose status, label, forbidden
    flag or presence changed.
    """
    regression = comparison.get("regression")
    result = "**REGRESSION**" if regression else "**NO REGRESSION**"
    caveats = [] if comparison.get("dataset_match") else [_MISMATCH_CAVEAT]
    caveats += [_POLICY_CAVEAT, _COMPARISON_CAVEAT, _UNRUN_CAVEAT]
    counts = comparison.get("counts")
    count_rows = (
        [(_text(key.replace("_", " ")), _number(count)) for key, count in counts.items()]
        if isinstance(counts, Mapping)
        else []
    )
    return _sections(
        ["## Corsair report comparison"],
        [f"Result: {result}"],
        [line for caveat in caveats for line in (caveat, ">")][:-1],
        _comparison_identity(comparison),
        ["### Counts", "", *_table(("Count", "Value"), count_rows, numeric=1)]
        if count_rows
        else [],
        _delta_lines(comparison),
        _regression_lines(comparison),
        _changed_lines(comparison),
    )


def to_markdown(value: object) -> str:
    """Dispatch a JSON-mode command result: comparison, report or summary, else fenced JSON.

    Commands without a Markdown record keep their complete JSON receipt inside a fenced block,
    so ``--format markdown`` never drops or invents fields.
    """
    if isinstance(value, Mapping) and "disposition" not in value:
        if {"cases", "regression"} <= value.keys():
            return comparison_markdown(value)
        if isinstance(value.get("summary"), Mapping) or "attempts" in value:
            return report_markdown(value)
    rendered = json.dumps(value, indent=2, ensure_ascii=False)
    # A fence longer than any backtick run in the receipt, so no value can close it.
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall("`+", rendered)), default=0))
    return f"{fence}json\n{rendered}\n{fence}\n"
