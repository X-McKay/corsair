"""Presentation only. Rich owns color/animation; Temporal owns execution and waiting."""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from contextlib import nullcontext
from typing import Any, Literal, Protocol, TypeVar, cast

from pydantic import TypeAdapter
from rich.console import Console, Group
from rich.json import JSON
from rich.panel import Panel
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


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


def _text(value: object) -> Text:
    return Text("unknown" if value is None else safe_text(value))


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
        elif isinstance(rendered, dict) and "runs" in rendered:
            self._runs(rendered)
        elif isinstance(rendered, dict) and "observations" in rendered:
            self._evidence(rendered)
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

    def _runs(self, value: dict[str, Any]) -> None:
        """Render a committed-run listing, newest first; identities fold, never truncate."""
        table = Table(expand=True)
        for column in ("Recorded (UTC)", "Run", "Case", "Verdict", "Status"):
            table.add_column(column, overflow="fold")
        for row in value["runs"]:
            status = row["execution_status"]
            table.add_row(
                _text(row["recorded_at"][:16].replace("T", " ")),
                _text(row["run_id"]),
                _text(row["case_id"]),
                _text(row["verdict"]),
                Text(safe_text(status), style=_STYLES.get(status, "cyan")),
            )
        self.out.print(Panel(table, title="Corsair · Committed runs", border_style="cyan"))
        if value["invalid_records"]:
            self.out.print(
                Text(f"{value['invalid_records']} committed record(s) could not be read")
            )

    def _evidence(self, value: dict[str, Any]) -> None:
        """Render per-role native receipts for one committed result, never payloads."""
        tables: list[Table] = []
        for item in value["observations"]:
            name = "Fixed revision" if item["fixed"] else f"Session {item['session']}"
            name = name if item["fixed"] else f"{name} round {item['round']}"
            table = Table(
                title=_text(f"{name} · {item['operation_id']}"),
                caption=_text(
                    f"committed={item['committed']} · evidence={item['evidence']} · "
                    f"admissible={item['receipts_admissible']} · gate={item['gate']}"
                ),
                expand=True,
            )
            for column in ("Role", "Outcome", "Ran", "Exit", "Lines", "Cleanup", "Container"):
                # Enum labels stay whole; identities and line lists fold, never truncate.
                table.add_column(column, overflow="fold", no_wrap=column in {"Role", "Outcome"})
            for role, entry in item["roles"].items():
                table.add_row(
                    _text(role),
                    _text(entry["outcome"]),
                    _text(entry["target_executed"]),
                    _text(entry["native_exit_code"]),
                    _text(",".join(str(line) for line in entry["covered_lines"]) or None),
                    _text(entry.get("cleanup_confirmed")),
                    _text((entry.get("container_id") or "")[:12] or entry["receipt"]),
                )
            tables.append(table)
        title = f"Corsair · Evidence {safe_text(value['run_id'])} · {safe_text(value['verdict'])}"
        body = Group(*tables) if tables else Text("No observations were recorded")
        self.out.print(Panel(body, title=title, border_style="cyan"))

    async def wait(
        self,
        awaitable: Awaitable[T],
        label: str,
        *,
        query: Callable[[], Awaitable[Mapping[str, object]]] | None = None,
    ) -> T:
        """Observe actual SDK completion; query failures never invent success or progress."""
        status = (
            self.err.status(Text(label), spinner="dots", spinner_style="cyan")
            if self.animate
            else None
        )
        task = asyncio.ensure_future(awaitable)
        last: Mapping[str, object] | None = None
        query_failed = False
        with status if status is not None else nullcontext():
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
                                detail = " · ".join(
                                    f"{key}={value}" for key, value in actual.items()
                                )
                                event(
                                    "workflow.progress",
                                    phase=phase if isinstance(phase, str) else None,
                                    round=round_index if isinstance(round_index, int) else None,
                                    completed=completed if isinstance(completed, int) else None,
                                    total=total if isinstance(total, int) else None,
                                )
                                if status:
                                    status.update(Text(f"{label} · {detail}"))
                                last = actual
                            query_failed = False
                        except Exception as error:
                            if not query_failed:
                                event(
                                    "workflow.progress_unavailable",
                                    level=logging.WARNING,
                                    error_type=type(error).__name__,
                                )
                            query_failed = True
                    await asyncio.wait({task}, timeout=1)
                return await task
            finally:
                if not task.done():
                    # Cancels local waiting, not the durable remote workflow.
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
