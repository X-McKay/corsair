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

from pydantic import TypeAdapter, ValidationError
from rich.console import Console, Group, RenderableType
from rich.json import JSON
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
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
from corsair.evaluation.comparison import row_label, row_stop
from corsair.evaluation.scoring import usage_metrics
from corsair.observability.logging import event, safe_error_detail, safe_text
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.ports.scm import SourceAdmissionError

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
_STYLES: dict[str, str] = {
    "pass": "green",
    "fail": "red",
    "unavailable": "yellow",
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
# Seconds between native status queries while a durable workflow remains open.
_POLL_SECONDS = 1.0
# Most recent phase transitions shown in the live panel.
_TIMELINE_ROWS = 8


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json", "markdown"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


_TEMPORAL_REMEDY = (
    "Start Temporal (for example `temporal server start-dev`) or set temporal_address and "
    "temporal_namespace in --settings, then run `corsair doctor`."
)
_DOCKER_REMEDY = "Start the Docker daemon (or set DOCKER_HOST), then run `corsair doctor`."
_IMAGE_REMEDY = (
    "Build the trusted image with `just images`, or set image in --settings to a built tag, "
    "then run `corsair doctor`."
)
_JSON_REMEDY = "The file is not valid JSON; check it for truncation or an editing mistake."
_SOURCE_REMEDIES = (
    (
        "outside configured source_root",
        "Set source_root in --settings to a directory that contains the request's sources "
        "(the default is the current directory).",
    ),
    (
        "expected_digest",
        "The source tree differs from the request's frozen expected_digest. Restore that "
        "source, or write a new request for the changed source; never edit a frozen digest.",
    ),
    (
        "source path does not exist",
        "Check source.path in the request; it resolves relative to the request file.",
    ),
    (
        "configured source_root",
        "Set source_root in --settings to an existing, readable directory that is not a "
        "symbolic link.",
    ),
    (
        "limit",
        "Narrow the request's source path to the code under test, or review "
        "source_limit_bytes and source_limit_files in --settings.",
    ),
    (
        "are not admitted",
        "Remove symbolic links and special files from the source tree; only regular files "
        "and directories are admitted.",
    ),
)


def _module_error(error: BaseException, module: str, name: str) -> bool:
    """Match an SDK exception class only if its module is already loaded; never import it."""
    kind = getattr(sys.modules.get(module), name, None)
    return isinstance(kind, type) and isinstance(error, kind)


def failure_remedy(error: BaseException) -> str | None:
    """Return one fixed next step for a known failure class, or ``None``.

    The exception text is matched against fixed patterns but never echoed: every remedy is a
    constant, so it cannot carry credentials, endpoints or provider content. The original,
    sanitized error detail is still reported beside it.
    """
    text = str(error)
    if isinstance(error, ValidationError):
        if any(
            item["type"] == "json_invalid"
            for item in error.errors(include_input=False, include_url=False)
        ):
            return _JSON_REMEDY
        return (
            "Correct the fields named above; see docs/reference/configuration.md for settings "
            "and docs/reference/schemas.md for requests and submissions."
        )
    if isinstance(error, json.JSONDecodeError):
        return _JSON_REMEDY
    if isinstance(error, FileNotFoundError):
        return (
            "Check the path: command arguments and --settings resolve from the current "
            "directory, request source paths from the request file's directory."
        )
    if isinstance(error, IsADirectoryError | NotADirectoryError):
        return "Pass the path of a file, not a directory, and check each parent directory."
    if isinstance(error, PermissionError):
        return "Check file permissions: inputs must be readable and artifact_root writable."
    if isinstance(error, SourceAdmissionError):
        return next((remedy for pattern, remedy in _SOURCE_REMEDIES if pattern in text), None)
    if isinstance(error, SandboxUnavailable):
        return _IMAGE_REMEDY if "image" in text else _DOCKER_REMEDY
    if _module_error(error, "docker.errors", "ImageNotFound"):
        return _IMAGE_REMEDY
    if _module_error(error, "docker.errors", "DockerException"):
        return _DOCKER_REMEDY
    if _module_error(error, "temporalio.service", "RPCError"):
        # Already loaded whenever an RPCError exists; importing it eagerly costs ~0.3 s.
        from temporalio.service import RPCError, RPCStatusCode

        status = cast(RPCError, error).status
        if status == RPCStatusCode.NOT_FOUND and text.startswith("Namespace"):
            return (
                "Create the namespace (`temporal operator namespace create`) or set "
                "temporal_namespace in --settings."
            )
        if status == RPCStatusCode.NOT_FOUND:
            return (
                "Check the run id and temporal_namespace; `temporal workflow list` shows "
                "existing runs."
            )
        if status in {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}:
            return _TEMPORAL_REMEDY
        return None
    if isinstance(error, RuntimeError) and text.startswith("Failed client connect"):
        return _TEMPORAL_REMEDY
    if isinstance(error, TimeoutError):
        return (
            "A service did not answer in time; run `corsair doctor` to check Temporal and Docker."
        )
    if isinstance(error, ValueError) and text.startswith("No committed result"):
        return (
            "Check the run id and artifact_root in --settings; for a run that has not "
            "finished, use `corsair inspect RUN_ID --online`."
        )
    return None


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


def _target_caption(item: Mapping[str, Any]) -> str:
    """The kernel's target line, and that it was derived when prepare bound it."""
    line = item.get("target_line")
    if line is None:
        return ""
    derived = item.get("line_provenance") == "recipe_function"
    return f" · target=L{line}" + (" (derived from recipe function)" if derived else "")


def _cleanup_text(confirmed: bool) -> Text:
    return Text("confirmed", style="green") if confirmed else Text("NOT confirmed", style="red")


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
        self.markdown = requested == "markdown"
        # JSON mode must remain free of cursor movement even when running on a TTY.
        colors = not options.no_color and requested not in {"json", "markdown"}
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
        """Write a complete JSON receipt, a Markdown record or a compact human rendering."""
        rendered = TypeAdapter(Any).dump_python(value, mode="json")
        if self.markdown:
            from corsair.entrypoints.markdown import to_markdown

            sys.stdout.write(to_markdown(rendered))
            return
        if not self.human:
            print(json.dumps(rendered, indent=2, ensure_ascii=False))
            return
        if isinstance(rendered, dict) and "disposition" in rendered:
            self._result(InvestigationResult.model_validate(rendered))
        elif isinstance(rendered, dict) and {"operation_id", "submission_digest"} <= set(rendered):
            self._observation(Observation.model_validate(rendered))
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
                detail = _text(check["detail"])
                if check.get("remedy"):
                    detail.append("\n→ ").append(_text(check["remedy"]))
                table.add_row(
                    _text(check["name"]), Text(check["status"].upper(), style=style), detail
                )
            self.out.print(Panel(table, title="Corsair · Environment checks", border_style="cyan"))
            self.out.print(_text(rendered["qualification"]))
        elif isinstance(rendered, dict) and "cases" in rendered and "regression" in rendered:
            self._comparison(rendered)
        elif isinstance(rendered, dict) and ("summary" in rendered or "attempts" in rendered):
            summary = rendered.get("summary", rendered)
            table = Table.grid(padding=(0, 2))
            counts: dict[str, dict] = {}
            for key, detail in summary.items():
                if isinstance(detail, dict):
                    if detail:
                        counts[key] = detail
                        continue
                    detail = "none"
                table.add_row(Text(key.replace("_", " "), style="cyan"), _text(detail))
            self.out.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
            if "dataset_digest" in rendered:
                self.out.print(Text("Dataset: ") + _text(rendered["dataset_digest"]))
            if isinstance(rendered.get("rows"), list):
                self._report_rows(rendered["rows"])
            for key, detail in counts.items():
                self._counts(key, detail)
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

    def _counts(self, key: str, counts: dict) -> None:
        """Render one per-gate count mapping, such as the evaluation gate ledger."""
        table = Table("Gate", "Count", expand=True)
        for gate, count in counts.items():
            table.add_row(_text(gate), _text(count))
        title = f"Corsair · {key.replace('_', ' ').capitalize()}"
        self.out.print(Panel(table, title=title, border_style="cyan"))

    def _report_rows(self, rows: list[dict[str, Any]]) -> None:
        """Render one table row per scored attempt; unknown usage stays unknown."""
        table = Table(expand=True)
        for column in ("Case", "Run", "Status", "Label", "Stop", "Usage", "Reason"):
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
                _text(row_stop(row) or "-"),
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
        gates = value.get("gate_delta", {})
        moved = [entry for entry in gates.get("gate_ledger", []) if entry["delta"]]
        grid.add_row(
            Text("gates moved", style="cyan"),
            _text(
                ", ".join(f"{entry['gate']} {_signed(entry['delta'])}" for entry in moved) or "none"
            ),
        )
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
        self._gate_delta(gates)
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
                _text(case["case_id"]),
                _text(case["repeat"]),
                _text(f"{_plain(case['baseline_status'])} -> {_plain(case['candidate_status'])}"),
                _text(f"{_plain(case['baseline_label'])} -> {_plain(case['candidate_label'])}"),
                _text(
                    f"{_plain(case.get('baseline_stop'))} -> {_plain(case.get('candidate_stop'))}"
                ),
                Text(safe_text(change.replace("_", " ")), style="red" if regressed else "cyan"),
                _text(_usage(case["usage_delta"], _signed) if case["presence"] == "both" else "-"),
            )
        self.out.print(Panel(table, title="Corsair · Changed cases", border_style="cyan"))

    def _gate_delta(self, gates: Mapping[str, list[dict[str, Any]]]) -> None:
        """Per-gate counts on both sides, with the failing-row final stops beside them."""
        stops = {entry["gate"]: entry for entry in gates.get("failure_stops", [])}
        entries = gates.get("gate_ledger", [])
        if not entries:
            return
        table = Table("Gate", "Baseline", "Candidate", "Δ", "Failing stops", expand=True)
        for entry in entries:
            failing = stops.get(entry["gate"])
            table.add_row(
                _text(entry["gate"]),
                _text(entry["baseline"]),
                _text(entry["candidate"]),
                Text(_signed(entry["delta"]), style="cyan" if entry["delta"] else "dim"),
                _text(
                    f"{failing['baseline']} -> {failing['candidate']} ({_signed(failing['delta'])})"
                    if failing
                    else "-"
                ),
            )
        self.out.print(Panel(table, title="Corsair · Gate ledger Δ", border_style="cyan"))

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
                    + _target_caption(item)
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

    def report_failure(self, error: Exception) -> None:
        """Log a failed command with its sanitized detail and, when known, a fixed remedy."""
        remedy = failure_remedy(error)
        event(
            "cli.failed",
            level=logging.ERROR,
            error_type=type(error).__name__,
            message=safe_error_detail(error),
            **({} if remedy is None else {"remedy": remedy}),
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
