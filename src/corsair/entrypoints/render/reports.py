"""Evaluation report views: `eval`, `rescore`, `report`, `dataset replay-candidates` and
`compare`.

An evaluation shows its summary, one row per scored attempt (with the native replay result
when present), per-family and per-split tables and per-gate counts. A comparison leads with
dataset identity, then gate, family and summary deltas and only the cases that changed.
Unknown usage and deltas stay unknown, never zero.
"""

from collections.abc import Callable, Mapping
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.entrypoints.render.common import PASS_FAIL_STYLES, as_text, signed
from corsair.evaluation.comparison import row_label, row_stop
from corsair.observability.logging import safe_text


def _plain(value: object) -> str:
    if isinstance(value, float):
        return str(round(value, 4))
    return "unknown" if value is None else safe_text(value)


def _ratio(count: object, total: object) -> str:
    """``count/total``; an unknown count (such as decisive on agent rows) stays unknown."""
    if not isinstance(count, int) or not isinstance(total, int):
        return "unknown"
    return f"{count}/{total}"


def _usage(values: Mapping[str, Any], show: Callable[[object], str]) -> str:
    """One compact usage cell: model calls, tokens in/out and agent seconds."""
    return (
        f"{show(values.get('llm_calls'))} LLM · "
        f"{show(values.get('input_tokens'))}/{show(values.get('output_tokens'))} tok · "
        f"{show(values.get('agent_seconds'))} s"
    )


def _replay_cell(replay: object) -> Text:
    """A native replay's demonstrates/does-not result beside the exact-match label."""
    if not isinstance(replay, Mapping):
        return Text("-")
    status = replay.get("status")
    if status == "demonstrated":
        return Text("demonstrates", style="green")
    if status == "not_demonstrated":
        roles = f"{_plain(replay.get('control'))}/{_plain(replay.get('adversarial'))}"
        covered = "covered" if replay.get("covered") else "not covered"
        return Text(f"does not · {roles} · {covered}", style="yellow")
    return Text(f"unavailable · {_plain(replay.get('reason'))}", style="red")


def print_evaluation(console: Console, rendered: dict[str, Any]) -> None:
    """Render an evaluation summary, its scored rows, groups and per-gate counts."""
    summary = rendered.get("summary", rendered)
    table = Table.grid(padding=(0, 2))
    counts: dict[str, dict] = {}
    for key, detail in summary.items():
        if isinstance(detail, dict):
            if detail:
                counts[key] = detail
                continue
            detail = "none"
        table.add_row(Text(key.replace("_", " "), style="cyan"), as_text(detail))
    console.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
    if "dataset_digest" in rendered:
        console.print(Text("Dataset: ") + as_text(rendered["dataset_digest"]))
    if "replay_note" in rendered:
        console.print(as_text(rendered["replay_note"]))
    if isinstance(rendered.get("rows"), list):
        _report_rows(console, rendered["rows"])
    if isinstance(rendered.get("families"), list):
        _groups(console, "Families", "family", rendered["families"])
    if isinstance(rendered.get("splits"), list):
        _groups(console, "Splits", "split", rendered["splits"])
    for key, detail in counts.items():
        _counts(console, key, detail)
    if "report" in rendered:
        console.print(Text("Report: ") + as_text(rendered["report"]))


def _counts(console: Console, key: str, counts: dict) -> None:
    """Render one per-gate count mapping, such as the evaluation gate ledger."""
    table = Table("Gate", "Count", expand=True)
    for gate, count in counts.items():
        table.add_row(as_text(gate), as_text(count))
    title = f"Corsair · {key.replace('_', ' ').capitalize()}"
    console.print(Panel(table, title=title, border_style="cyan"))


def _report_rows(console: Console, rows: list[dict[str, Any]]) -> None:
    """Render one table row per scored attempt; unknown usage stays unknown.

    A row's ``reason`` is the result's reason, which can be an auditor's review or a
    producer's abstention, so only its code-chosen stopping gate is shown."""
    table = Table(expand=True)
    replayed = any("replay" in row for row in rows)
    columns = ("Case", "Run", "Status", "Label", *(("Replay",) if replayed else ()))
    for column in (*columns, "Stop", "Usage"):
        table.add_column(column, overflow="fold")
    for row in rows:
        status = row.get("status")
        execution = row.get("execution_status")
        detail = _plain(status)
        if execution not in {None, "COMPLETED"}:
            detail += f" · {_plain(execution)}"
        replay = (_replay_cell(row.get("replay")),) if replayed else ()
        table.add_row(
            as_text(row.get("case_id")),
            as_text(row.get("run_id")),
            Text(detail, style=PASS_FAIL_STYLES.get(str(status), "cyan")),
            as_text(row_label(row)),
            *replay,
            as_text(row_stop(row) or "-"),
            as_text(_usage(row, _plain)),
        )
    console.print(Panel(table, title="Corsair · Cases", border_style="cyan"))


def _groups(console: Console, title: str, key: str, groups: list[dict[str, Any]]) -> None:
    """Render per-family or per-split summaries; an undeclared group is shown as such."""
    table = Table(expand=True)
    other = "Splits" if key == "family" else "Families"
    for column in (key.capitalize(), other, "Cases", "Pass", "Decisive", "Forbidden", "Ops"):
        table.add_column(column, overflow="fold")
    for group in groups:
        spread = group.get("splits") if key == "family" else group.get("families")
        table.add_row(
            as_text(group[key] if group[key] is not None else "(undeclared)"),
            as_text(", ".join(spread) if isinstance(spread, list) else spread),
            as_text(group["cases"]),
            as_text(_ratio(group["passed"], group["attempts"])),
            as_text(_ratio(group["decisive"], group["attempts"])),
            Text(
                _plain(group["forbidden_labels"]),
                style="red" if group["forbidden_labels"] else "cyan",
            ),
            as_text(group["operational_failures"]),
        )
    console.print(Panel(table, title=f"Corsair · {title}", border_style="cyan"))


def _family_deltas(console: Console, families: list[dict[str, Any]]) -> None:
    """Render each family's pass rate, decisive count and forbidden-label change."""
    table = Table(expand=True)
    for column in ("Family", "Pass rate", "Decisive", "Forbidden", "Regressions"):
        table.add_column(column, overflow="fold")

    def side(item: dict[str, Any], name: str, field: str) -> str:
        group = item[name]
        return "absent" if group is None else _plain(group.get(field))

    for item in families:
        family = item["family"]
        table.add_row(
            as_text(family if family is not None else "(undeclared)"),
            as_text(
                f"{side(item, 'baseline', 'pass_rate')} -> "
                f"{side(item, 'candidate', 'pass_rate')} ({signed(item['pass_rate_delta'])})"
            ),
            as_text(
                f"{side(item, 'baseline', 'decisive')} -> "
                f"{side(item, 'candidate', 'decisive')} ({signed(item['decisive_delta'])})"
            ),
            as_text(
                f"{side(item, 'baseline', 'forbidden_labels')} -> "
                f"{side(item, 'candidate', 'forbidden_labels')}"
            ),
            Text(str(item["regressions"]), style="red" if item["regressions"] else "green"),
        )
    console.print(Panel(table, title="Corsair · Families", border_style="cyan"))


def print_comparison(console: Console, value: dict[str, Any]) -> None:
    """Render a report comparison: dataset identity first, then deltas and changed cases."""
    digests = value["dataset_digest"]
    if not value["dataset_match"]:
        console.print(
            Panel(
                as_text(
                    "Dataset digests differ or are undeclared; this is not a comparison "
                    f"on one frozen dataset. baseline={_plain(digests['baseline'])} "
                    f"candidate={_plain(digests['candidate'])}"
                ),
                title="Corsair · Dataset mismatch",
                border_style="red",
            )
        )
    grid = Table.grid(padding=(0, 2))
    grid.add_row(
        Text("Result", style="cyan"),
        Text(
            "REGRESSION" if value["regression"] else "NO REGRESSION",
            style="red" if value["regression"] else "green",
        ),
    )
    if value["dataset_match"]:
        grid.add_row(Text("Dataset", style="cyan"), as_text(digests["baseline"]))
    gates = value.get("gate_delta", {})
    moved = [entry for entry in gates.get("gate_ledger", []) if entry["delta"]]
    grid.add_row(
        Text("gates moved", style="cyan"),
        as_text(
            ", ".join(f"{entry['gate']} {signed(entry['delta'])}" for entry in moved) or "none"
        ),
    )
    for key, count in value["counts"].items():
        grid.add_row(Text(key.replace("_", " "), style="cyan"), as_text(count))
    for key, delta in value["summary_delta"].items():
        grid.add_row(
            Text(key.replace("_", " "), style="cyan"),
            as_text(
                f"{_plain(delta['baseline'])} -> {_plain(delta['candidate'])} "
                f"({signed(delta['delta'])})"
            ),
        )
    for item in value["regressions"]:
        family = f" [{_plain(item['family'])}]" if item.get("family") else ""
        grid.add_row(
            Text("Regression", style="red"),
            as_text(
                f"{_plain(item['case_id'])} #{_plain(item['repeat'])}{family}: {item['reason']}"
            ),
        )
    console.print(Panel(grid, title="Corsair · Comparison", border_style="cyan"))
    _gate_delta(console, gates)
    if isinstance(value.get("families"), list):
        _family_deltas(console, value["families"])
    changed = [
        case
        for case in value["cases"]
        if case["flip"]
        or case["label_changed"]
        or case["new_forbidden_label"]
        or case["presence"] != "both"
    ]
    if not changed:
        console.print(Text(f"No per-case status or label changes in {len(value['cases'])}."))
        return
    table = Table(expand=True)
    for column in ("Case", "#", "Status", "Label", "Stop", "Change", "Usage Δ"):
        table.add_column(column, overflow="fold")
    for case in changed:
        regressed = (
            case["flip"] == "pass_to_fail"
            or case["new_forbidden_label"]
            or case["presence"] == "baseline_only"
        )
        change = case["flip"] or case["presence"]
        if case["new_forbidden_label"]:
            change += " · new forbidden label"
        table.add_row(
            as_text(case["case_id"]),
            as_text(case["repeat"]),
            as_text(f"{_plain(case['baseline_status'])} -> {_plain(case['candidate_status'])}"),
            as_text(f"{_plain(case['baseline_label'])} -> {_plain(case['candidate_label'])}"),
            as_text(f"{_plain(case.get('baseline_stop'))} -> {_plain(case.get('candidate_stop'))}"),
            Text(safe_text(change.replace("_", " ")), style="red" if regressed else "cyan"),
            as_text(_usage(case["usage_delta"], signed) if case["presence"] == "both" else "-"),
        )
    console.print(Panel(table, title="Corsair · Changed cases", border_style="cyan"))


def _gate_delta(console: Console, gates: Mapping[str, list[dict[str, Any]]]) -> None:
    """Per-gate counts on both sides, with the failing-row final stops beside them."""
    stops = {entry["gate"]: entry for entry in gates.get("failure_stops", [])}
    entries = gates.get("gate_ledger", [])
    if not entries:
        return
    table = Table("Gate", "Baseline", "Candidate", "Δ", "Failing stops", expand=True)
    for entry in entries:
        failing = stops.get(entry["gate"])
        table.add_row(
            as_text(entry["gate"]),
            as_text(entry["baseline"]),
            as_text(entry["candidate"]),
            Text(signed(entry["delta"]), style="cyan" if entry["delta"] else "dim"),
            as_text(
                f"{failing['baseline']} -> {failing['candidate']} ({signed(failing['delta'])})"
                if failing
                else "-"
            ),
        )
    console.print(Panel(table, title="Corsair · Gate ledger Δ", border_style="cyan"))
