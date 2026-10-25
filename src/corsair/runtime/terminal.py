"""Presentation only. Rich owns color/animation; Temporal owns execution and waiting."""

import asyncio
import json
import logging
import sys
from contextlib import nullcontext
from typing import Any

from pydantic import TypeAdapter
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.contracts import InvestigationResult
from corsair.observability.evaluation import usage_metrics
from corsair.observability.logging import event, safe_text

_STYLES = {
    "SUPPORTED": "green",
    "CONDITIONAL": "yellow",
    "INCONCLUSIVE": "yellow",
    "ERROR": "red",
    "BLOCKED": "red",
    "CANCELLED": "yellow",
    "COMPLETED": "green",
}


def _text(value) -> Text:
    return Text("unknown" if value is None else safe_text(value))


class Terminal:
    def __init__(self, args):
        requested = getattr(args, "format", "auto")
        self.human = requested == "human" or (requested == "auto" and sys.stdout.isatty())
        # JSON mode must remain free of cursor movement even when running on a TTY.
        colors = not getattr(args, "no_color", False) and requested != "json"
        animation = self.human and not getattr(args, "no_animation", False)
        animation = animation and getattr(args, "log_format", "text") != "json"
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

    def emit(self, value) -> None:
        value = TypeAdapter(Any).dump_python(value, mode="json")
        if not self.human:
            print(json.dumps(value, indent=2, ensure_ascii=False))
            return
        if isinstance(value, dict) and "disposition" in value:
            self._result(value)
        elif isinstance(value, dict) and "checks" in value:
            table = Table("Check", "Status", "Details", expand=True)
            for check in value["checks"]:
                style = {"pass": "green", "fail": "red", "warn": "yellow"}.get(
                    check["status"], "cyan"
                )
                table.add_row(
                    _text(check["name"]),
                    Text(check["status"].upper(), style=style),
                    _text(check["detail"]),
                )
            self.out.print(Panel(table, title="Corsair · Environment checks", border_style="cyan"))
            self.out.print(_text(value["qualification"]))
        elif isinstance(value, dict) and ("summary" in value or "attempts" in value):
            summary = value.get("summary", value)
            table = Table.grid(padding=(0, 2))
            for key, detail in summary.items():
                table.add_row(Text(key.replace("_", " "), style="cyan"), _text(detail))
            self.out.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
            if "report" in value:
                self.out.print(Text("Report: ") + _text(value["report"]))
        else:
            self.out.print(
                Panel(
                    JSON(json.dumps(value, ensure_ascii=False)),
                    title="Corsair · Native receipt",
                    border_style="cyan",
                )
            )

    def _result(self, value: dict) -> None:
        table = Table.grid(padding=(0, 2), expand=True)
        label = value["disposition"]
        table.add_row(Text("Disposition", style="cyan"), Text(label, style=_STYLES.get(label)))
        for key in ("run_id", "case_id", "execution_status", "scope", "reason", "fix_status"):
            table.add_row(Text(key.replace("_", " ").title(), style="cyan"), _text(value.get(key)))
        for item in value.get("rounds", []):
            observation = item.get("observation") or {}
            for role in ("control", "adversarial"):
                evidence = observation.get(role) or {}
                detail = (
                    f"{evidence.get('outcome', 'not observed')} · "
                    f"exit={evidence.get('native_exit_code')} · "
                    f"coverage={evidence.get('covered_lines', [])}"
                )
                table.add_row(_text(f"Round {item['index']} {role}"), _text(detail))
            audit = (item.get("audit") or {}).get("review") or {}
            table.add_row(_text(f"Round {item['index']} audit"), _text(audit.get("decision")))
            usage = item["producer"]["usage"]
            table.add_row(
                _text(f"Round {item['index']} producer"),
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

    async def wait(self, awaitable, label: str, *, query=None):
        """Observe actual SDK completion; query failures never invent success/progress."""
        status = (
            self.err.status(Text(label), spinner="dots", spinner_style="cyan")
            if self.animate
            else None
        )
        task = asyncio.ensure_future(awaitable)
        last = None
        query_failed = False
        with status if status is not None else nullcontext():
            try:
                while not task.done():
                    if query is not None:
                        try:
                            async with asyncio.timeout(2):
                                actual = await query()
                            if actual != last:
                                detail = " · ".join(
                                    f"{key}={value}" for key, value in actual.items()
                                )
                                event("workflow.progress", **actual)
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
