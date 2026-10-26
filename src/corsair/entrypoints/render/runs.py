"""Committed-run views: `runs` (the listing, newest first) and `inspect RUN_ID --evidence`
(per-role native receipts for one committed result, never payloads).

Identities and line lists fold rather than truncate; the evidence caption names the
kernel's target line and whether it was derived from the recipe function or bound from a
different declared line.
"""

from collections.abc import Mapping
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.entrypoints.render.common import PASS_FAIL_STYLES, as_text
from corsair.observability.logging import safe_text


def _target_caption(item: Mapping[str, Any]) -> str:
    """The kernel's target line, and where it came from: derived by prepare from the
    recipe function, or bound by line binding from a different declared line."""
    line = item.get("target_line")
    if line is None:
        return ""
    declared = item.get("declared_line")
    if item.get("line_provenance") == "recipe_function":
        origin = " (derived from recipe function)"
    elif declared is not None and declared != line:
        origin = f" (declared L{declared}, bound to its reported statement)"
    else:
        origin = ""
    return f" · target=L{line}{origin}"


def print_runs(console: Console, value: dict[str, Any]) -> None:
    """Render a committed-run listing, newest first; identities fold, never truncate."""
    table = Table(expand=True)
    for column in ("Recorded (UTC)", "Run", "Case", "Verdict", "Status"):
        table.add_column(column, overflow="fold")
    for row in value["runs"]:
        status = row["execution_status"]
        table.add_row(
            as_text(row["recorded_at"][:16].replace("T", " ")),
            as_text(row["run_id"]),
            as_text(row["case_id"]),
            as_text(row["verdict"]),
            Text(safe_text(status), style=PASS_FAIL_STYLES.get(status, "cyan")),
        )
    console.print(Panel(table, title="Corsair · Committed runs", border_style="cyan"))
    if value["invalid_records"]:
        console.print(Text(f"{value['invalid_records']} committed record(s) could not be read"))


def print_evidence(console: Console, value: dict[str, Any]) -> None:
    """Render per-role native receipts for one committed result, never payloads."""
    tables: list[Table] = []
    for item in value["observations"]:
        name = "Fixed revision" if item["fixed"] else f"Session {item['session']}"
        name = name if item["fixed"] else f"{name} round {item['round']}"
        table = Table(
            title=as_text(f"{name} · {item['operation_id']}"),
            caption=as_text(
                f"committed={item['committed']} · evidence={item['evidence']} · "
                f"admissible={item['receipts_admissible']} · gate={item['gate']}"
                + _target_caption(item)
            ),
            expand=True,
        )
        for column in ("Role", "Outcome", "Ran", "Exit", "Lines", "Cleanup", "Container"):
            # Enum labels stay whole; identities and line lists fold, never truncate.
            table.add_column(column, overflow="fold", no_wrap=column in {"Role", "Outcome"})
        for role, entry in item["roles"].items():
            table.add_row(
                as_text(role),
                as_text(entry["outcome"]),
                as_text(entry["target_executed"]),
                as_text(entry["native_exit_code"]),
                as_text(",".join(str(line) for line in entry["covered_lines"]) or None),
                as_text(entry.get("cleanup_confirmed")),
                as_text((entry.get("container_id") or "")[:12] or entry["receipt"]),
            )
        tables.append(table)
    title = f"Corsair · Evidence {safe_text(value['run_id'])} · {safe_text(value['verdict'])}"
    body = Group(*tables) if tables else Text("No observations were recorded")
    console.print(Panel(body, title=title, border_style="cyan"))
