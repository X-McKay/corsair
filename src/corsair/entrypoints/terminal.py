"""Presentation only. Rich owns color/animation; Temporal owns execution and waiting."""

import argparse
import asyncio
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, TypeVar, cast

from pydantic import TypeAdapter
from rich.console import Console, Group, RenderableType
from rich.json import JSON
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from corsair.contracts import InvestigationResult
from corsair.evaluation.scoring import usage_metrics
from corsair.observability.logging import event, safe_text

_STYLES: dict[str, str] = {
    "SUPPORTED": "green",
    "CONDITIONAL": "yellow",
    "INCONCLUSIVE": "yellow",
    "ERROR": "red",
    "BLOCKED": "red",
    "CANCELLED": "yellow",
    "COMPLETED": "green",
}
T = TypeVar("T")
# Seconds between native status queries while a durable workflow remains open.
_POLL_SECONDS = 1.0
# Most recent phase transitions shown in the live panel.
_TIMELINE_ROWS = 8


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


def _text(value: object) -> Text:
    return Text("unknown" if value is None else safe_text(value))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


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


_PROGRESS_KEYS = frozenset(
    {"phase", "session", "round", "max_sessions", "max_rounds", "gate", "started", "deadline"}
    | {"timeline", "completed", "total", "running", "errors"}
)


def _offset(at: datetime | None, started: datetime | None) -> str:
    if at is None:
        return "unknown"
    return f"+{_clock((at - started).total_seconds())}" if started else at.strftime("%H:%M:%S")


def progress_fields(
    status: Mapping[str, object] | None, now: datetime, waited: float
) -> list[tuple[str, str]]:
    """Ordered display fields from a native status query plus local time only."""
    started = _instant(status.get("started")) if status else None
    elapsed = (now - started).total_seconds() if started else waited
    fields = [("elapsed", _clock(elapsed))]
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
        left = f"{_clock(remaining)} left" if remaining > 0 else "passed"
        fields.append(("deadline", f"{deadline.isoformat(timespec='seconds')} ({left})"))
    for key, value in status.items():
        if key not in _PROGRESS_KEYS and isinstance(value, str | int | float | bool):
            fields.append((key.replace("_", " "), safe_text(value)))
    return fields


def progress_line(label: str, fields: list[tuple[str, str]]) -> Text:
    """One plain line for a non-animated terminal: no cursor movement."""
    return _text(" · ".join([label, *(f"{key} {value}" for key, value in fields)]))


def progress_panel(
    label: str, status: Mapping[str, object] | None, fields: list[tuple[str, str]]
) -> Panel:
    """Compact live view: current status fields and the most recent phase transitions."""
    summary = Table.grid(padding=(0, 2))
    phase = next((value for key, value in fields if key == "phase"), "in progress")
    summary.add_row(Spinner("dots", style="cyan"), Text(phase, style="bold"))
    for key, value in fields:
        if key != "phase":
            summary.add_row(Text(key.capitalize(), style="cyan"), _text(value))
    parts: list[RenderableType] = [summary]
    timeline = status.get("timeline") if status else None
    if isinstance(timeline, list) and timeline:
        started = _instant(status.get("started")) if status else None
        table = Table("At", "Session", "Round", "Phase", box=None, pad_edge=False)
        entries = [entry for entry in timeline if isinstance(entry, Mapping)]
        if len(entries) > _TIMELINE_ROWS:
            table.add_row(_text(f"… {len(entries) - _TIMELINE_ROWS} earlier"), "", "", "")
        for entry in entries[-_TIMELINE_ROWS:]:
            table.add_row(
                _text(_offset(_instant(entry.get("at")), started)),
                _text(entry.get("session")),
                _text(entry.get("round")),
                _text(entry.get("phase")),
            )
        parts.extend([Text(""), table])
    return Panel(
        Group(*parts), title=f"Corsair · {safe_text(label)}", border_style="cyan", expand=False
    )


class Terminal:
    def __init__(self, args: TerminalOptions | argparse.Namespace) -> None:
        options = cast(TerminalOptions, args)
        requested = options.format
        self.human = requested == "human" or (requested == "auto" and sys.stdout.isatty())
        # JSON mode must remain free of cursor movement even when running on a TTY.
        colors = not options.no_color and requested != "json"
        animation = self.human and not options.no_animation
        animation = animation and options.log_format != "json"
        self.out = Console(
            no_color=not colors,
            color_system="auto" if colors else None,
            force_interactive=False,
            markup=False,
            highlight=False,
        )
        self.err = Console(
            stderr=True,
            no_color=not colors,
            color_system="auto" if colors else None,
            force_interactive=None if animation else False,
            markup=False,
            highlight=False,
        )
        self.animate = animation and self.err.is_interactive

    def emit(self, value: object) -> None:
        """Write a complete JSON receipt or a compact human rendering to stdout."""
        rendered = TypeAdapter(Any).dump_python(value, mode="json")
        if not self.human:
            print(json.dumps(rendered, indent=2, ensure_ascii=False))
            return
        if isinstance(rendered, dict) and "disposition" in rendered:
            self._result(rendered)
        elif isinstance(rendered, dict) and "checks" in rendered:
            table = Table("Check", "Status", "Details", expand=True)
            for check in rendered["checks"]:
                style = {"pass": "green", "fail": "red", "warn": "yellow"}.get(
                    check["status"], "cyan"
                )
                table.add_row(
                    _text(check["name"]),
                    Text(check["status"].upper(), style=style),
                    _text(check["detail"]),
                )
            self.out.print(Panel(table, title="Corsair · Environment checks", border_style="cyan"))
            self.out.print(_text(rendered["qualification"]))
        elif isinstance(rendered, dict) and ("summary" in rendered or "attempts" in rendered):
            summary = rendered.get("summary", rendered)
            table = Table.grid(padding=(0, 2))
            for key, detail in summary.items():
                table.add_row(Text(key.replace("_", " "), style="cyan"), _text(detail))
            self.out.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
            if "report" in rendered:
                self.out.print(Text("Report: ") + _text(rendered["report"]))
        else:
            self.out.print(
                Panel(
                    JSON(json.dumps(rendered, ensure_ascii=False)),
                    title="Corsair · Native receipt",
                    border_style="cyan",
                )
            )

    def _result(self, value: dict[str, Any]) -> None:
        """Render a validated investigation result without exposing model content."""
        table = Table.grid(padding=(0, 2), expand=True)
        label = value["disposition"]
        table.add_row(
            Text("Disposition", style="cyan"), Text(label, style=_STYLES.get(label, "cyan"))
        )
        for key in ("run_id", "case_id", "execution_status", "scope", "reason", "fix_status"):
            table.add_row(Text(key.replace("_", " ").title(), style="cyan"), _text(value.get(key)))
        for item in value.get("rounds", []):
            observation = item.get("observation") or {}
            session = item.get("session", 1)
            name = (
                f"Round {item['index']}"
                if session == 1
                else f"Session {session} round {item['index']}"
            )
            for role in ("control", "adversarial"):
                evidence = observation.get(role) or {}
                detail = (
                    f"{evidence.get('outcome', 'not observed')} · "
                    f"exit={evidence.get('native_exit_code')} · "
                    f"coverage={evidence.get('covered_lines', [])}"
                )
                table.add_row(_text(f"{name} {role}"), _text(detail))
            audit = (item.get("audit") or {}).get("review") or {}
            table.add_row(_text(f"{name} audit"), _text(audit.get("decision")))
            usage = item["producer"]["usage"]
            table.add_row(
                _text(f"{name} producer"),
                _text(f"{usage['llm_calls']} LLM / {usage['tool_calls']} tool calls"),
            )
            feedback = item["producer"].get("feedback") or observation.get("feedback")
            if feedback:
                table.add_row(Text("Gate", style="yellow"), _text(feedback["gate"]))
        table.add_row(
            Text("Usage complete", style="cyan"), _text(value.get("usage_complete", True))
        )
        for key, total in usage_metrics(InvestigationResult.model_validate(value)).items():
            table.add_row(Text(key.replace("_", " ").title(), style="cyan"), _text(total))
        for role, model in (value.get("manifest") or {}).get("models", {}).items():
            table.add_row(Text(f"{role.title()} model", style="cyan"), _text(model))
        table.add_row(Text("Cost", style="cyan"), Text("unknown"))
        artifact = value.get("result_artifact") or {}
        table.add_row(Text("Result SHA-256", style="cyan"), _text(artifact.get("sha256")))
        self.out.print(
            Panel(table, title="Corsair · Investigation", border_style=_STYLES.get(label, "cyan"))
        )

    async def wait(
        self,
        awaitable: Awaitable[T],
        label: str,
        *,
        query: Callable[[], Awaitable[Mapping[str, object]]] | None = None,
    ) -> T:
        """Observe actual SDK completion; query failures never invent success or progress.

        With a status query, an animated terminal shows a live panel, a plain human terminal
        prints one line per status change, and JSON mode writes nothing beyond the logs.
        """
        begun = time.monotonic()
        last: Mapping[str, object] | None = None

        def frame() -> Panel:
            fields = progress_fields(last, _utcnow(), time.monotonic() - begun)
            return progress_panel(label, last, fields)

        display: AbstractContextManager[object] = nullcontext()
        if self.animate and query is not None:
            display = Live(
                console=self.err, get_renderable=frame, refresh_per_second=4, transient=False
            )
        elif self.animate:
            display = self.err.status(Text(label), spinner="dots", spinner_style="cyan")
        task = asyncio.ensure_future(awaitable)
        query_failed = False
        with display:
            try:
                while not task.done():
                    if query is not None:
                        try:
                            async with asyncio.timeout(2):
                                actual = await query()
                            if actual != last:
                                phase = actual.get("phase")
                                round_index = actual.get("round")
                                completed = actual.get("completed")
                                total = actual.get("total")
                                event(
                                    "workflow.progress",
                                    phase=phase if isinstance(phase, str) else None,
                                    round=round_index if isinstance(round_index, int) else None,
                                    completed=completed if isinstance(completed, int) else None,
                                    total=total if isinstance(total, int) else None,
                                )
                                last = actual
                                if self.human and not self.animate:
                                    fields = progress_fields(
                                        last, _utcnow(), time.monotonic() - begun
                                    )
                                    self.err.print(progress_line(label, fields), soft_wrap=True)
                            query_failed = False
                        except Exception as error:
                            if not query_failed:
                                event(
                                    "workflow.progress_unavailable",
                                    level=logging.WARNING,
                                    error_type=type(error).__name__,
                                )
                            query_failed = True
                    await asyncio.wait({task}, timeout=_POLL_SECONDS)
                return await task
            finally:
                if not task.done():
                    # Cancels local waiting, not the durable remote workflow.
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
