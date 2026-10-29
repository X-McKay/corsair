"""Workflow progress while a command waits: `investigate`, `eval`, `inspect --watch` and
every other `Terminal.wait` with a native status query.

An animated terminal redraws ``progress_panel`` (status fields, then evaluation child rows
with a progress bar, or the most recent phase transitions); a plain human terminal prints
one ``progress_line`` per status change, or one ``child_line`` per evaluation child state
change found by ``child_changes``. Every field comes from the status query and local time.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from corsair.contracts import BatchItem, ExecutionStatus, InvestigationResult
from corsair.contracts.intake_agent import IntakeResult
from corsair.contracts.intake_pipeline import IntakeInvestigationResult
from corsair.entrypoints.render.common import as_text, clock, label_grid, short_digest
from corsair.observability.logging import safe_text

# Most recent phase transitions shown in the live panel.
_TIMELINE_ROWS = 8
# Evaluation child rows shown in the live panel; the query already orders them by state.
_CHILD_TABLE_ROWS = 16
_CHILD_STYLES = {"running": "cyan", "failed": "red", "completed": "green", "pending": "dim"}


def _instant(value: object) -> datetime | None:
    """Parse a timezone-aware ISO timestamp from a status query, else None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _count(value: object, limit: object) -> str:
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        return f"{value}/{limit}"
    return str(value)


def _offset(at: datetime | None, started: datetime | None) -> str:
    if at is None:
        return "unknown"
    return f"+{clock((at - started).total_seconds())}" if started else at.strftime("%H:%M:%S")


def progress_fields(
    status: Mapping[str, object] | None, now: datetime, waited: float
) -> list[tuple[str, str]]:
    """Ordered display fields from a native status query plus local time only."""
    started = _instant(status.get("started")) if status else None
    elapsed = (now - started).total_seconds() if started else waited
    fields = [("elapsed", clock(elapsed))]
    if status is None:
        return [*fields, ("status", "waiting for the workflow status query")]
    if "phase" in status:
        fields.append(("phase", safe_text(status["phase"])))
    if "session" in status:
        fields.append(("session", _count(status["session"], status.get("max_sessions"))))
    if "round" in status:
        fields.append(("round", _count(status["round"], status.get("max_rounds"))))
    if status.get("gate") is not None:
        fields.append(("last gate", safe_text(status["gate"])))
    if "completed" in status:
        fields.append(("cases", _count(status["completed"], status.get("total"))))
    for key in ("running", "errors"):
        if key in status:
            fields.append((key, safe_text(status[key])))
    deadline = _instant(status.get("deadline"))
    if deadline is not None:
        remaining = (deadline - now).total_seconds()
        left = f"{clock(remaining)} left" if remaining > 0 else "passed"
        fields.append(("deadline", f"{deadline.isoformat(timespec='seconds')} ({left})"))
    for key, label in (("investigation_run_id", "investigation"), ("image_reference", "image")):
        if status.get(key) is not None:
            fields.append((label, safe_text(status[key])))
    if isinstance(status.get("image_id"), str):
        fields.append(("image ID", short_digest(str(status["image_id"]))))
    if status.get("child_status_unavailable") is True:
        fields.append(("status", "Investigation status unavailable"))
    return fields


def completion_label(value: object) -> str:
    """Operational completion from typed receipts; never infer a security verdict."""
    if isinstance(value, IntakeInvestigationResult):
        if value.stop_reason == "CANCELLED":
            return "Cancelled"
        if value.status == "incomplete":
            return "Incomplete"
        if value.stop_reason == "INTAKE_ERROR":
            return "Failed"
        if value.status == "stopped":
            return "Stopped"
        return _execution_label(value.investigation_execution_status)
    if isinstance(value, InvestigationResult):
        return _execution_label(value.execution_status)
    if isinstance(value, IntakeResult):
        if value.decision.status == "error":
            return "Failed"
        return "Completed" if value.decision.classification == "in_scope_supported" else "Stopped"
    if isinstance(value, list) and any(
        isinstance(item, BatchItem) and item.error for item in value
    ):
        return "Completed with errors"
    return "Completed"


def _execution_label(status: ExecutionStatus | None) -> str:
    return {
        ExecutionStatus.COMPLETED: "Completed",
        ExecutionStatus.ERROR: "Failed",
        ExecutionStatus.CANCELLED: "Cancelled",
        ExecutionStatus.BLOCKED: "Stopped",
    }.get(status, "Incomplete")


def wait_summary(label: str, outcome: str, waited: float, reconnect: str | None) -> Panel:
    """A static final frame with local wait duration and a safe reconnect instruction."""
    style = "red" if outcome == "Failed" else "cyan" if outcome == "Completed" else "yellow"
    grid = label_grid()
    grid.add_row(Text(outcome, style=f"bold {style}"), as_text(label))
    grid.add_row("Waited", as_text(clock(waited)))
    if outcome == "Detached" and reconnect is not None:
        grid.add_row("Workflow", Text("Local wait ended; durable execution was not cancelled."))
        grid.add_row("Reconnect", as_text(reconnect))
    return Panel(grid, title="Corsair · Run status", border_style=style)


def _child_rows(status: Mapping[str, object] | None) -> list[Mapping[str, object]]:
    """Evaluation child rows from a status query, in the order the workflow returned."""
    children = status.get("children") if status else None
    if not isinstance(children, list):
        return []
    return [row for row in children if isinstance(row, Mapping)]


def _child_elapsed(row: Mapping[str, object], now: datetime) -> str:
    """A running child's time so far, a finished child's duration, else nothing."""
    started = _instant(row.get("started"))
    if started is None:
        return ""
    finished = _instant(row.get("finished")) or now
    return clock((finished - started).total_seconds())


def _child_table(status: Mapping[str, object], now: datetime, width: int) -> Table | None:
    rows = _child_rows(status)
    if not rows:
        return None
    table = (
        label_grid()
        if width < 80
        else Table("State", "Case", "Repeat", "Elapsed", "Run", box=None, pad_edge=False)
    )
    for row in rows[:_CHILD_TABLE_ROWS]:
        state = safe_text(row.get("state"))
        cells = [
            as_text(row.get("case_id")),
            as_text(row.get("repeat")),
            as_text(_child_elapsed(row, now)),
            as_text(row.get("run_id")),
        ]
        if width < 80:
            cells = [
                as_text(
                    f"{safe_text(row.get('case_id'))} · repeat {safe_text(row.get('repeat'))}\n"
                    f"{safe_text(row.get('run_id'))} · {_child_elapsed(row, now)}"
                )
            ]
        table.add_row(Text(state, style=_CHILD_STYLES.get(state, "")), *cells)
    omitted = status.get("children_omitted")
    hidden = max(0, len(rows) - _CHILD_TABLE_ROWS)
    hidden += omitted if isinstance(omitted, int) and not isinstance(omitted, bool) else 0
    if hidden > 0:
        table.add_row(as_text(f"… {hidden} more"), *([""] * (1 if width < 80 else 4)))
    return table


def child_changes(
    seen: dict[str, str], status: Mapping[str, object] | None
) -> list[Mapping[str, object]]:
    """Rows whose state differs from the last one seen for that run; updates ``seen``.

    A child first seen while still pending is not a change, so the first poll of a
    large batch prints nothing per child.
    """
    changed: list[Mapping[str, object]] = []
    for row in _child_rows(status):
        run_id, state = safe_text(row.get("run_id")), safe_text(row.get("state"))
        previous = seen.get(run_id)
        if previous != state and not (previous is None and state == "pending"):
            changed.append(row)
        seen[run_id] = state
    return changed


def child_line(
    label: str, row: Mapping[str, object], fields: list[tuple[str, str]], now: datetime
) -> Text:
    """One plain line for one evaluation child's state change, after the batch counts."""
    child = [
        ("case", f"{safe_text(row.get('case_id'))} r{safe_text(row.get('repeat'))}"),
        ("state", safe_text(row.get("state"))),
    ]
    elapsed = _child_elapsed(row, now)
    if elapsed:
        child.append(("case elapsed", elapsed))
    return progress_line(label, [*fields, *child])


def progress_line(label: str, fields: list[tuple[str, str]]) -> Text:
    """One plain line for a non-animated terminal: no cursor movement."""
    return as_text(" · ".join([label, *(f"{key} {value}" for key, value in fields)]))


def progress_panel(
    label: str,
    status: Mapping[str, object] | None,
    fields: list[tuple[str, str]],
    *,
    now: datetime | None = None,
    unavailable_for: float | None = None,
    animate: bool = True,
    width: int = 80,
) -> Panel:
    """Compact live view: status fields, then evaluation child rows with a progress bar or
    the most recent phase transitions, whichever the status query carries."""
    summary = label_grid()
    phase = next((value for key, value in fields if key == "phase"), "in progress")
    summary.add_row(Spinner("dots", style="cyan") if animate else Text("Phase"), as_text(phase))
    if unavailable_for is not None:
        summary.add_row(
            Text("Status unavailable", style="yellow"),
            as_text(
                f"Last update {clock(unavailable_for)} ago; showing retained state."
                if status is not None
                else "No status received; waiting for query recovery."
            ),
        )
    for key, value in fields:
        if key != "phase":
            summary.add_row(Text(key.capitalize(), style="cyan"), as_text(value))
    total = status.get("total") if status else None
    completed = status.get("completed") if status else None
    if isinstance(total, int) and isinstance(completed, int) and total > 0:
        bar = ProgressBar(total=total, completed=min(completed, total), width=30)
        summary.add_row(Text("Progress", style="cyan"), bar)
    parts: list[RenderableType] = [summary]
    children = _child_table(status, now or datetime.now(UTC), width) if status else None
    if children is not None:
        parts.extend([Text(""), children])
    timeline = status.get("timeline") if status else None
    if isinstance(timeline, list) and timeline:
        started = _instant(status.get("started")) if status else None
        table = Table("At", "Session", "Round", "Phase", box=None, pad_edge=False)
        entries = [entry for entry in timeline if isinstance(entry, Mapping)]
        if len(entries) > _TIMELINE_ROWS:
            table.add_row(as_text(f"… {len(entries) - _TIMELINE_ROWS} earlier"), "", "", "")
        for entry in entries[-_TIMELINE_ROWS:]:
            table.add_row(
                as_text(_offset(_instant(entry.get("at")), started)),
                as_text(entry.get("session")),
                as_text(entry.get("round")),
                as_text(entry.get("phase")),
            )
        parts.extend([Text(""), table])
    return Panel(
        Group(*parts), title=f"Corsair · {safe_text(label)}", border_style="cyan", expand=False
    )
