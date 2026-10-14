"""Terminal presentation only; records and native usage remain the source of truth.

No model text, arguments, source, or tool results enter the live display. Live token
updates/per-tool durations are intentionally not invented from final aggregates.
"""
from __future__ import annotations

import os
import sys
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from .runs import printable


def _value(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}" if isinstance(value, float) else printable(value)


def console(*, color: str = "auto", stderr: bool = False) -> Console:
    return Console(file=sys.stderr if stderr else sys.stdout, no_color=True if color == "never" else None,
                   color_system=None if color == "never" else "auto", highlight=False)


class StageReporter:
    """One native indeterminate spinner on a TTY; append-only stderr logs everywhere else."""

    def __init__(self, *, color: str = "auto", animate: bool = True):
        self.console = console(color=color, stderr=True)
        self.interactive = animate and self.console.is_terminal and os.environ.get("TERM") != "dumb"
        self.progress = Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(),
                                 console=self.console, auto_refresh=True, transient=True)
        self.task = None

    def __enter__(self) -> StageReporter:
        if self.interactive:
            self.progress.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.interactive:
            self.progress.stop()
        if exc_type is not None:
            self.console.print(Text("CANCELLED" if exc_type.__name__ in ("CancelledError", "KeyboardInterrupt")
                                    else "INTERRUPTED", style="yellow"))

    def announce(self, text: str) -> None:
        self.console.print(Text(printable(text)))

    def __call__(self, step: str, status: str) -> None:
        state = "RUNNING" if status == "started" else "DONE" if status.startswith("ok ") else "STOPPED"
        line = f"{state:<8} {printable(step):<28} {printable(status)}"
        self.console.print(Text(line, style="cyan" if state == "RUNNING" else "green" if state == "DONE" else "yellow"))
        if self.interactive:
            description = f"{state} {printable(step)}"
            if self.task is None:
                self.task = self.progress.add_task(description, total=None)
            else:
                self.progress.update(self.task, description=description)
            if state == "RUNNING":
                self.progress.reset(self.task, total=None, description=description)
            else:
                self.progress.stop_task(self.task)


def agent_table(agents: dict[str, dict[str, Any]]) -> Table:
    table = Table(title="Agent telemetry (recorded totals)", expand=False)
    for name in ("Agent", "Calls", "Requests", "Input tokens", "Output tokens", "Tools", "Retries", "Agent s", "Status"):
        table.add_column(name)
    for name, usage in agents.items():
        table.add_row(Text(printable(name)), *(_value(usage.get(key)) for key in
                      ("calls", "requests", "input_tokens", "output_tokens", "tool_calls", "retries", "wall_s")),
                      Text(", ".join(f"{printable(status)}: {count}" for status, count in (usage.get("statuses") or {}).items())))
    return table


def render_result(verdict: Any, run_dir: Any, data: dict[str, Any], *, color: str = "auto") -> None:
    out = console(color=color)
    out.print(Text(f"label: {verdict.label.value}\nrule: {verdict.rule_id}\n"
                   f"terminal reason: {verdict.terminal_reason.value}\nrun dir: {printable(run_dir)}", style="bold"))
    totals = data["totals"]
    out.print(Text(f"Elapsed s: {_value(totals.get('wall_s'))}  Tokens: {_value(totals.get('tokens'))}  "
                   f"Requests: {_value(totals.get('requests'))}  Tool calls: {_value(totals.get('tool_calls'))}"))
    if data["agents"]:
        out.print(agent_table(data["agents"]))
        out.print("Agent seconds sum recorded calls, not elapsed run time. Missing telemetry is unknown.")
