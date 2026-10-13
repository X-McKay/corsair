"""SPEC-0072: the run's activity in the terminal, a view over ``corsair.composition.progress`` events.

On a terminal: a colored log of stage outcomes, model turns, tool calls and retries, under a live status line
with the current stage, turn and budget spent. Anywhere else (a pipe, a log file, ``NO_COLOR``, ``TERM=dumb``):
the same events as plain timestamped lines with no colors, cursor movement or wrapping. It writes to stderr by
default so a command's own stdout (a result line or JSON) stays machine-readable. The events' text is already
cleaned (``progress.clean``); everything is printed as ``Text``, never parsed as markup.
"""

from datetime import datetime, timezone
import sys
from time import perf_counter
from typing import IO

from rich.console import Console
from rich.status import Status
from rich.text import Text

from corsair.composition.progress import (GateDecided, ModelFailed, ModelTurn, Retry, RevisionEnded, RevisionStarted,
                                          RunEnded, RunEvent, StageEnded, StageStarted, ToolCalled, ToolReturned,
                                          Usage, clean)

STAGE_WIDTH = 15


def _count(value: int) -> str:
    return f"{value / 1000:.1f}".removesuffix(".0") + "k" if value >= 1000 else str(value)


def spend(usage: Usage, *, live: bool = False) -> str:
    """Usage against its caps: ``tools 4/16 · tokens 12.3k/128k · 41s/300s`` (live) or totals at a stage's end."""
    def of(value, cap, show=str):
        return f"{show(value)}/{show(cap)}" if cap is not None else show(value)
    parts = [f"turns {usage.requests}" if not live else None,
             f"tools {of(usage.tool_calls, usage.tool_calls_limit)}",
             f"tokens {of(usage.tokens, usage.tokens_limit, _count)}",
             f"{usage.elapsed_seconds:.0f}s" + (f"/{usage.timeout_seconds:.0f}s" if usage.timeout_seconds else "")]
    return " · ".join(part for part in parts if part)


class TerminalDisplay:
    """A ``RunObserver``. Use as a context manager so the live status line is started and cleared."""

    def __init__(self, title: str | None = None, *, file: IO[str] | None = None, console: Console | None = None):
        self.console = console or Console(file=file or sys.stderr, highlight=False, soft_wrap=True)
        self.live = self.console.is_terminal and not self.console.is_dumb_terminal
        self.title, self.started = title and clean(title, 160), perf_counter()
        self.stage: str | None = None
        self.state = ""
        self.status: Status | None = None
        self.pending: dict[str, list[str]] = {}  # Arguments of calls not yet returned, per tool, in call order

    def __enter__(self) -> "TerminalDisplay":
        if self.title:
            self._line(Text.assemble(("corsair ", "bold cyan"), (self.title, "bold")), plain=f"run {self.title}")
        if self.live:
            self.status = self.console.status("starting", spinner="dots")
            self.status.start()
        return self

    def __exit__(self, *exc) -> None:
        if self.status is not None:
            self.status.stop()
            self.status = None

    def __call__(self, event: RunEvent) -> None:
        match event:
            case StageStarted(stage):
                self.stage, self.state = stage, "starting"
                self._row(stage, ("▸", "cyan"), ("started", "cyan"), "")
            case StageEnded(stage, "ready", detail, usage):
                self._row(stage, ("✓", "green"), ("ready", "bold green"), detail, usage)
                self.stage, self.state = None, "between stages"
            case StageEnded(stage, _, reason, usage):
                self._row(stage, ("✗", "red"), ("stopped", "bold red"), reason, usage, detail_style="red")
                self.stage, self.state = None, "stopped"
            case ModelTurn(stage, turn, tools, answered, usage):
                asked = ", ".join(tools + (("final answer",) if answered else ())) or "no tool call"
                self._sub(Text.assemble((f"turn {turn}", "magenta"), "  ", (asked, ""), "  ",
                                        (spend(usage, live=True), "dim")),
                          plain=f"{stage} turn {turn}: {asked} | {spend(usage, live=True)}")
                self.state = f"turn {turn} · {spend(usage, live=True)}"
            case ToolCalled(stage, tool, arguments):
                self.pending.setdefault(tool, []).append(arguments)
                self._update(f"{self.state} · running {tool}")
            case ToolReturned(stage, tool, outcome, detail, elapsed):
                calls = self.pending.get(tool) or [""]
                arguments = calls.pop(0)
                style = {"ok": "green", "retry": "yellow", "error": "red"}[outcome]
                mark = {"ok": "⚙", "retry": "↻", "error": "✗"}[outcome]
                self._sub(Text.assemble((mark + " ", style), (tool, "bold"), (f"({arguments})", "dim"), " ",
                                        (outcome, style), (f" {elapsed:.1f}s", "dim"),
                                        (f"  {detail}" if detail else "", style)),
                          plain=f"{stage} tool {tool}({arguments}) {outcome} {elapsed:.1f}s"
                                + (f": {detail}" if detail else ""))
            case Retry(stage, target, name, detail):
                about = f"{target}{' of ' + name if name else ''}"
                self._sub(Text.assemble(("↻ retry ", "yellow"), (about, "bold yellow"), (f"  {detail}", "yellow")),
                          plain=f"{stage} retry {about}: {detail}")
            case ModelFailed(stage, kind, detail):
                self._sub(Text.assemble(("✗ model error ", "red"), (kind, "bold red"), (f"  {detail}", "red")),
                          plain=f"{stage} model error {kind}: {detail}")
            case RevisionStarted(revision):
                self._update(f"running the {revision} revision")
            case RevisionEnded(revision, outcome, detail):
                style = "green" if outcome == "ran" else "red"
                self._sub(Text.assemble((f"{revision} ", "bold"), (outcome, style), (f"  {detail}", "")),
                          plain=f"execution {revision} {outcome}: {detail}")
            case GateDecided(verdict):
                self._row("gate", ("◆", "blue"), ("decided", "bold blue"), verdict)
            case RunEnded(stopped_at, reason, verdict):
                if stopped_at is None:
                    head, plain = Text("Result  complete", "bold green"), "result complete"
                else:
                    head, plain = Text(f"Result  stopped at {stopped_at}", "bold red"), f"result stopped at {stopped_at}"
                tail = f" — {verdict}" if verdict else (f" — {reason}" if stopped_at else "")
                self._line(Text.assemble(head, (tail, "bold")), plain=plain + tail)
        self._update(None)

    def _update(self, state: str | None) -> None:
        if self.status is None:
            return
        stage = self.stage or "corsair"
        self.status.update(Text.assemble((stage, "bold cyan"), "  ", (state or self.state, "dim")))

    def _row(self, stage: str, mark: tuple[str, str], word: tuple[str, str], detail: str, usage: Usage | None = None,
             *, detail_style: str = "") -> None:
        totals = spend(usage) if usage else ""
        self._line(Text.assemble(mark, " ", (stage.ljust(STAGE_WIDTH), "bold"), (word[0].ljust(8), word[1]), " ",
                                 (detail, detail_style), (f"  {totals}" if totals else "", "dim")),
                   plain=f"{stage} {word[0]}" + (f": {detail}" if detail else "") + (f" | {totals}" if totals else ""))

    def _sub(self, text: Text, *, plain: str) -> None:
        self._line(Text.assemble("    ", text), plain=plain)

    def _line(self, text: Text, *, plain: str) -> None:
        if self.live:
            elapsed = Text(f"{perf_counter() - self.started:6.1f}s ", "dim")
            self.console.print(Text.assemble(elapsed, text), soft_wrap=True)
        else:
            stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
            self.console.print(Text(f"{stamp} {plain}"), soft_wrap=True, style=None)
