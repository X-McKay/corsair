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

from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    ExecutionStatus,
    InvestigationResult,
    NoGroundedCandidate,
    Observation,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    Usage,
    Verdict,
)
from corsair.evaluation.scoring import usage_metrics
from corsair.observability.logging import event, safe_text

# Colour by what the label means to an operator: a demonstrated exploit is the
# finding coming true (red), a scoped negative is the property holding (green),
# a non-decisive stop is yellow and an operational stop is magenta.
_VERDICT_STYLES: dict[Verdict, str] = {
    Verdict.EXPLOIT_DEMONSTRATED: "bold red",
    Verdict.COMPONENT_EXPLOIT_DEMONSTRATED: "red",
    Verdict.EXPLOIT_NOT_DEMONSTRATED: "green",
    Verdict.INCONCLUSIVE: "yellow",
    Verdict.UNABLE_TO_RUN: "magenta",
    Verdict.ERROR: "bold magenta",
}
_STATUS_STYLES: dict[ExecutionStatus, str] = {
    ExecutionStatus.COMPLETED: "green",
    ExecutionStatus.BLOCKED: "red",
    ExecutionStatus.ERROR: "red",
    ExecutionStatus.CANCELLED: "yellow",
}
_OUTCOME_STYLES: dict[RoleOutcome, str] = {
    RoleOutcome.HELD: "green",
    RoleOutcome.VIOLATION: "red",
    RoleOutcome.INVALID: "yellow",
    RoleOutcome.ERROR: "magenta",
}
_AUDIT_STYLES: dict[AuditDecision, str] = {
    AuditDecision.ACCEPT: "green",
    AuditDecision.REJECT: "red",
    AuditDecision.INSUFFICIENT: "yellow",
}
# Human words for the kernel's role outcomes; JSON keeps the enum values.
_OUTCOME_WORDS: dict[RoleOutcome, str] = {
    RoleOutcome.HELD: "held",
    RoleOutcome.VIOLATION: "violated",
    RoleOutcome.INVALID: "invalid",
    RoleOutcome.ERROR: "error",
}
_MAX_LINE_RANGES = 4
_MAX_RULE_CHARS = 48
T = TypeVar("T")


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


def _text(value: object) -> Text:
    return Text("unknown" if value is None else safe_text(value))


def _label(key: str) -> Text:
    return Text(key, style="cyan")


def _grid() -> Table:
    """A label/value grid whose values wrap rather than hide characters."""
    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    return grid


def _outcome(role: RoleObservation) -> Text:
    return Text(
        _OUTCOME_WORDS.get(role.outcome, role.outcome.value),
        style=_OUTCOME_STYLES.get(role.outcome, "cyan"),
    )


def _short(value: str, keep: int = 12) -> str:
    """Abbreviate a digest for reading; JSON output keeps the full value."""
    prefix, _, rest = value.rpartition(":")
    body = rest if prefix else value
    head = f"{prefix}:" if prefix else ""
    return f"{head}{body[:keep]}…" if len(body) > keep else value


def _line_ranges(lines: list[int]) -> str:
    """Compress covered target lines (12,13,14,20 -> L12-14, 20)."""
    ordered = sorted(set(lines))
    if not ordered:
        return "no lines"
    ranges: list[str] = []
    start = previous = ordered[0]
    for line in [*ordered[1:], None]:
        if line is not None and line == previous + 1:
            previous = line
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        if line is not None:
            start = previous = line
    shown = ", ".join(ranges[:_MAX_LINE_RANGES])
    hidden = len(ranges) - _MAX_LINE_RANGES
    return f"L{shown}" + (f" +{hidden} more" if hidden > 0 else "")


def _role_cell(role: RoleObservation | None) -> Text:
    """Outcome and coverage only; the role reason stays in the JSON receipt."""
    if role is None:
        return Text("not observed", style="dim")
    cell = _outcome(role)
    cell.append(f"\n{_line_ranges(role.covered_lines)}", style="dim")
    if not role.target_executed:
        cell.append("\nnot executed", style="yellow")
    return cell


def _usage_lines(usage: Usage) -> str:
    tokens = (
        "tokens unknown"
        if usage.input_tokens is None or usage.output_tokens is None
        else f"{usage.input_tokens}/{usage.output_tokens} tok"
    )
    return f"\n{usage.llm_calls} llm · {usage.tool_calls} tool\n{tokens}"


def _producer_cell(item: RoundResult) -> Text:
    """Decision kind and gate name only: abstention and feedback reasons can be model text."""
    decision = item.producer.decision
    if decision is None:
        cell = Text("no decision", style="yellow")
    elif isinstance(decision.root, NoGroundedCandidate):
        cell = Text("abstained", style="yellow")
    else:
        cell = Text("proposal")
    feedback = item.producer.feedback
    if feedback is None and item.observation is not None:
        feedback = item.observation.feedback
    if feedback is not None:
        cell.append(f"\ngate: {safe_text(feedback.gate)}", style="yellow")
    cell.append(_usage_lines(item.producer.usage), style="dim")
    return cell


def _audit_cell(audit: AuditOutput | None) -> Text:
    """Decision and rule name only; the auditor's free-text reason is never shown."""
    if audit is None:
        return Text("not audited", style="dim")
    if audit.review is None:
        cell = Text("no review", style="yellow")
        if audit.feedback:
            cell.append(f"\ngate: {safe_text(audit.feedback.gate)}", style="yellow")
        return cell
    review = audit.review
    rule = safe_text(review.rule)
    if len(rule) > _MAX_RULE_CHARS:
        rule = rule[: _MAX_RULE_CHARS - 1] + "…"
    cell = Text(review.decision.value, style=_AUDIT_STYLES.get(review.decision, "cyan"))
    cell.append(f"\n{rule}", style="dim")
    return cell


def _rounds_table(rounds: list[RoundResult]) -> Table:
    table = Table(title="Rounds", title_justify="left", expand=True)
    table.add_column("S.R", no_wrap=True)
    for column in ("Producer", "Control", "Adversarial", "Audit"):
        table.add_column(column, overflow="fold")
    for item in rounds:
        observation = item.observation
        table.add_row(
            Text(f"{item.session}.{item.index}"),
            _producer_cell(item),
            _role_cell(observation.control if observation else None),
            _role_cell(observation.adversarial if observation else None),
            _audit_cell(item.audit),
        )
    return table


def _roles_table(observation: Observation, title: str, *, caption: bool = False) -> Table:
    """Kernel-authored role facts for a native observation; no payload or model content."""
    table = Table(title=title, title_justify="left", expand=True)
    if caption:
        summary = Text("cleanup ") + _cleanup_text(observation.cleanup_confirmed)
        if observation.feedback is not None:
            summary.append(f" · gate: {safe_text(observation.feedback.gate)}", style="yellow")
        table.caption = summary
        table.caption_justify = "left"
    for column in ("Role", "Outcome", "Ran", "Exit", "Coverage", "Reason"):
        table.add_column(column, overflow="fold")
    for name, role in (("control", observation.control), ("adversarial", observation.adversarial)):
        if role is None:
            table.add_row(
                Text(name), Text("not observed", style="dim"), *(Text("") for _ in "1234")
            )
            continue
        table.add_row(
            Text(name),
            _outcome(role),
            Text("yes" if role.target_executed else "no"),
            _text(role.native_exit_code),
            Text(_line_ranges(role.covered_lines)),
            _text(role.reason or "-"),
        )
    return table


def _cleanup_text(confirmed: bool) -> Text:
    return Text("confirmed", style="green") if confirmed else Text("NOT confirmed", style="red")


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
            self._result(InvestigationResult.model_validate(rendered))
        elif isinstance(rendered, dict) and {"operation_id", "submission_digest"} <= set(rendered):
            self._observation(Observation.model_validate(rendered))
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

    def _result(self, result: InvestigationResult) -> None:
        """Verdict first, then rounds, identity and totals; never model or payload content."""
        style = _VERDICT_STYLES.get(result.verdict, "cyan") if result.verdict else "cyan"
        header = _grid()
        header.add_row(
            _label("Verdict"),
            Text(result.verdict.value, style=style)
            if result.verdict
            else Text("not recorded", style="yellow"),
        )
        header.add_row(
            _label("Execution"),
            Text(
                result.execution_status.value,
                style=_STATUS_STYLES.get(result.execution_status, "cyan"),
            ),
        )
        header.add_row(_label("Disposition"), _text(result.disposition.value))
        header.add_row(_label("Scope"), _text(result.scope.value))
        header.add_row(_label("Fix"), _text(result.fix_status.value))
        header.add_row(_label("Reason"), _text(result.reason))
        header.add_row(_label("Run"), _text(result.run_id))
        header.add_row(_label("Case"), _text(result.case_id))
        self.out.print(Panel(header, title="Corsair · Investigation", border_style=style))
        if result.rounds:
            self.out.print(_rounds_table(result.rounds))
        else:
            self.out.print(Text("No rounds recorded.", style="dim"))
        if result.fix_observation is not None:
            self.out.print(_roles_table(result.fix_observation, "Fixed revision", caption=True))
        self.out.print(self._identity(result))

    @staticmethod
    def _identity(result: InvestigationResult) -> Panel:
        table = _grid()
        manifest = result.manifest
        if manifest is not None:
            table.add_row(_label("Package"), _text(manifest.package_version))
            table.add_row(_label("Image"), _text(_short(manifest.image_id)))
            for key, value in (
                ("Request", manifest.request_digest),
                ("Config", manifest.config_digest),
                ("Producer prompt", manifest.producer_prompt_digest),
                ("Auditor prompt", manifest.auditor_prompt_digest),
            ):
                table.add_row(_label(key), _text(_short(value)))
            for role, model in manifest.models.items():
                table.add_row(_label(f"{role.title()} model"), _text(model))
            table.add_row(
                _label("Evidence policy"),
                _text(
                    f"{manifest.negative_threshold} negatives · {manifest.max_sessions} sessions"
                ),
            )
        else:
            table.add_row(_label("Manifest"), Text("not recorded", style="yellow"))
        totals = Table.grid(padding=(0, 2))
        totals.add_row(_label("Usage complete"), _text(str(result.usage_complete).lower()))
        for key, total in usage_metrics(result).items():
            if key == "agent_seconds" and total is not None:
                total = f"{total:.1f}"
            name = key.replace("_", " ").capitalize().replace("Llm", "LLM")
            totals.add_row(_label(name), _text(total))
        totals.add_row(_label("Cost"), Text("unknown"))
        layout = Table.grid(padding=(0, 4), expand=True)
        layout.add_column(ratio=3)
        layout.add_column(ratio=2)
        layout.add_row(table, totals)
        artifact = _grid()
        reference = result.result_artifact
        artifact.add_row(_label("Result SHA-256"), _text(reference.sha256 if reference else None))
        return Panel(Group(layout, artifact), title="Identity · Totals", border_style="cyan")

    def _observation(self, observation: Observation) -> None:
        """A native reference replay: role facts and identity, explicitly without a verdict."""
        header = _grid()
        header.add_row(_label("Verdict"), Text("none · no security verdict", style="dim"))
        header.add_row(_label("Operation"), _text(observation.operation_id))
        header.add_row(_label("Source"), _text(_short(observation.source_digest)))
        header.add_row(_label("Submission"), _text(_short(observation.submission_digest)))
        header.add_row(_label("Cleanup"), _cleanup_text(observation.cleanup_confirmed))
        if observation.feedback is not None:
            gate = Text(safe_text(observation.feedback.gate), style="yellow")
            gate.append(f" · {safe_text(observation.feedback.reason)}")
            header.add_row(_label("Gate"), gate)
        artifact = observation.artifact
        header.add_row(_label("Evidence SHA-256"), _text(artifact.sha256 if artifact else None))
        self.out.print(
            Panel(header, title="Corsair · Native reference observation", border_style="cyan")
        )
        self.out.print(_roles_table(observation, "Roles"))

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
