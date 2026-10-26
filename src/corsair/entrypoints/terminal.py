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
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.contracts import InvestigationResult
from corsair.evaluation.comparison import row_label
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
    "pass": "green",
    "fail": "red",
    "unavailable": "yellow",
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


def _plain(value: object) -> str:
    if isinstance(value, float):
        return str(round(value, 4))
    return "unknown" if value is None else safe_text(value)


def _signed(value: object) -> str:
    """Render a delta with its sign; an unknown delta is never shown as zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "unknown"
    return f"{round(value, 4):+}"


def _usage(values: Mapping[str, Any], show: Callable[[object], str]) -> str:
    """One compact usage cell: model calls, tokens in/out and agent seconds."""
    return (
        f"{show(values.get('llm_calls'))} LLM · "
        f"{show(values.get('input_tokens'))}/{show(values.get('output_tokens'))} tok · "
        f"{show(values.get('agent_seconds'))} s"
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
        elif isinstance(rendered, dict) and "cases" in rendered and "regression" in rendered:
            self._comparison(rendered)
        elif isinstance(rendered, dict) and ("summary" in rendered or "attempts" in rendered):
            summary = rendered.get("summary", rendered)
            table = Table.grid(padding=(0, 2))
            for key, detail in summary.items():
                table.add_row(Text(key.replace("_", " "), style="cyan"), _text(detail))
            self.out.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
            if "dataset_digest" in rendered:
                self.out.print(Text("Dataset: ") + _text(rendered["dataset_digest"]))
            if isinstance(rendered.get("rows"), list):
                self._report_rows(rendered["rows"])
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

    def _report_rows(self, rows: list[dict[str, Any]]) -> None:
        """Render one table row per scored attempt; unknown usage stays unknown."""
        table = Table(expand=True)
        for column in ("Case", "Run", "Status", "Label", "Usage", "Reason"):
            table.add_column(column, overflow="fold")
        for row in rows:
            status = row.get("status")
            execution = row.get("execution_status")
            detail = _plain(status)
            if execution not in {None, "COMPLETED"}:
                detail += f" · {_plain(execution)}"
            table.add_row(
                _text(row.get("case_id")),
                _text(row.get("run_id")),
                Text(detail, style=_STYLES.get(str(status), "cyan")),
                _text(row_label(row)),
                _text(_usage(row, _plain)),
                _text(row.get("reason") or ""),
            )
        self.out.print(Panel(table, title="Corsair · Cases", border_style="cyan"))

    def _comparison(self, value: dict[str, Any]) -> None:
        """Render a report comparison: dataset identity first, then deltas and changed cases."""
        digests = value["dataset_digest"]
        if not value["dataset_match"]:
            self.out.print(
                Panel(
                    _text(
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
            grid.add_row(Text("Dataset", style="cyan"), _text(digests["baseline"]))
        for key, count in value["counts"].items():
            grid.add_row(Text(key.replace("_", " "), style="cyan"), _text(count))
        for key, delta in value["summary_delta"].items():
            grid.add_row(
                Text(key.replace("_", " "), style="cyan"),
                _text(
                    f"{_plain(delta['baseline'])} -> {_plain(delta['candidate'])} "
                    f"({_signed(delta['delta'])})"
                ),
            )
        for item in value["regressions"]:
            grid.add_row(
                Text("Regression", style="red"),
                _text(f"{_plain(item['case_id'])} #{_plain(item['repeat'])}: {item['reason']}"),
            )
        self.out.print(Panel(grid, title="Corsair · Comparison", border_style="cyan"))
        changed = [
            case
            for case in value["cases"]
            if case["flip"]
            or case["label_changed"]
            or case["new_forbidden_label"]
            or case["presence"] != "both"
        ]
        if not changed:
            self.out.print(Text(f"No per-case status or label changes in {len(value['cases'])}."))
            return
        table = Table(expand=True)
        for column in ("Case", "#", "Status", "Label", "Change", "Usage Δ"):
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
                _text(case["case_id"]),
                _text(case["repeat"]),
                _text(f"{_plain(case['baseline_status'])} -> {_plain(case['candidate_status'])}"),
                _text(f"{_plain(case['baseline_label'])} -> {_plain(case['candidate_label'])}"),
                Text(safe_text(change.replace("_", " ")), style="red" if regressed else "cyan"),
                _text(_usage(case["usage_delta"], _signed) if case["presence"] == "both" else "-"),
            )
        self.out.print(Panel(table, title="Corsair · Changed cases", border_style="cyan"))

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
