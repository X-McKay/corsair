"""Investigation result views: `investigate`, `inspect RUN_ID`, `explain`, `verify` and the
result half of `inspect --explain`.

A result leads with its verdict and case stop, then one row per round with the gate-ledger
stop, the fixed-revision roles, the recorded phase durations and an identity/totals panel.
A native reference observation (`verify`) shows role facts without a verdict. Only
code-owned facts are shown: verdict, disposition, stage and gate names, the verifier's fixed
role and gate reasons, and the explanation rules. Payloads, plans and the result's ``reason``
(an auditor's review or a producer's abstention on some paths) never are; JSON keeps them.
"""

from collections.abc import Mapping
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    ExecutionStatus,
    InvestigationResult,
    Observation,
    PhaseTransition,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    Usage,
    Verdict,
)
from corsair.entrypoints.render.common import (
    as_text,
    clock,
    field_label,
    label_grid,
    short_digest,
)
from corsair.evaluation.ledger import RoundKey, gate_ledger, verified_rounds
from corsair.evaluation.scoring import usage_metrics
from corsair.observability.logging import safe_text

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
# Gate-ledger stops coloured like the verdicts they lead to; the rest are non-decisive.
_STOP_STYLES: dict[str, str] = {
    "demonstrated": "red",
    "component_demonstrated": "red",
    "clean_negative": "green",
    "evidence_unverified": "dim",
    "kernel_error": "magenta",
}
# Every recipe probes the component seam, whatever scope the finding claimed; the claim is
# ``result.scope`` and is labelled as such.
_EVIDENCE_SCOPE = "component (recipe seam)"
# Case-level ledger stops whose reason is a fixed, code-authored sentence. Every other
# ledger reason may repeat model text (an abstention, an audit reason) or the result's
# own reason, so the human view names only the stage and gate.
_CODE_REASON_STOPS = frozenset({"fix_not_blocked", "negative_threshold_unmet", "budget_exhausted"})


def _outcome(role: RoleObservation) -> Text:
    return Text(
        _OUTCOME_WORDS.get(role.outcome, role.outcome.value),
        style=_OUTCOME_STYLES.get(role.outcome, "cyan"),
    )


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
    elif decision.kind == "no_grounded_candidate":
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


def _stop_cell(entry: Mapping[str, Any] | None) -> Text:
    """Gate and stage only: a round's ledger reason can be model text."""
    if entry is None:
        return Text("unknown", style="dim")
    gate = str(entry["gate"])
    cell = Text(safe_text(gate), style=_STOP_STYLES.get(gate, "yellow"))
    cell.append(f"\n{safe_text(entry['stage'])}", style="dim")
    return cell


def _case_stop(ledger: list[dict]) -> Text:
    """Why the case stopped: its policy stops, else the last round's stopping gate."""
    stops = [entry for entry in ledger if entry["round"] is None]
    if not stops:
        last = ledger[-1]
        cell = Text(safe_text(last["gate"]), style=_STOP_STYLES.get(last["gate"], "yellow"))
        cell.append(f" · {safe_text(last['stage'])} at {last['session']}.{last['round']}")
        return cell
    cell = Text()
    for position, entry in enumerate(stops):
        if position:
            cell.append("; ")
        cell.append(safe_text(entry["gate"]), style=_STOP_STYLES.get(entry["gate"], "yellow"))
        if entry["gate"] in _CODE_REASON_STOPS:
            cell.append(f": {safe_text(entry['reason'])}")
    return cell


def _rounds_table(rounds: list[RoundResult], stops: Mapping[RoundKey, dict]) -> Table:
    table = Table(title="Rounds", title_justify="left", expand=True)
    table.add_column("S.R", no_wrap=True)
    for column in ("Producer", "Control", "Adversarial", "Audit", "Stopped at"):
        table.add_column(column, overflow="fold")
    for item in rounds:
        observation = item.observation
        table.add_row(
            Text(f"{item.session}.{item.index}"),
            _producer_cell(item),
            _role_cell(observation.control if observation else None),
            _role_cell(observation.adversarial if observation else None),
            _audit_cell(item.audit),
            _stop_cell(stops.get((item.session, item.index))),
        )
    if any(entry["gate"] == "evidence_unverified" for entry in stops.values()):
        table.caption = Text(
            "evidence_unverified: the round's receipts were not validated against the "
            "artifact store here, so no kernel gate is named; the verdict is the recorded one.",
            style="dim",
        )
        table.caption_justify = "left"
    return table


def _duration(seconds: float) -> str:
    return f"{seconds:.1f} s" if seconds < 60 else clock(seconds)


def _timeline_table(timeline: list[PhaseTransition]) -> Table:
    """Recorded phase durations: each transition lasts until the next one, and the last
    one (normally ``record``) has no recorded end. Unknown times stay unknown."""
    table = Table(title="Phases", title_justify="left", expand=True)
    for column in ("S.R", "Phase", "At", "Duration"):
        table.add_column(column, overflow="fold")
    first = timeline[0].at
    totals: dict[str, float | None] = {}
    for entry, following in zip(timeline, [*timeline[1:], None], strict=True):
        offset = None
        if entry.at is not None and first is not None:
            offset = f"+{clock((entry.at - first).total_seconds())}"
        duration: str | None = "-"
        if following is not None:
            seconds = None
            if entry.at is not None and following.at is not None:
                seconds = (following.at - entry.at).total_seconds()
            total = totals.get(entry.phase, 0.0)
            totals[entry.phase] = None if total is None or seconds is None else total + seconds
            duration = None if seconds is None else _duration(seconds)
        table.add_row(
            as_text(f"{entry.session}.{entry.round}"),
            as_text(entry.phase),
            as_text(offset),
            as_text(duration),
        )
    notes = []
    if timeline[0].phase != "prepare":
        notes.append("earlier transitions not retained")
    if totals:
        notes.append(
            "totals: "
            + " · ".join(
                f"{phase} {'unknown' if total is None else _duration(total)}"
                for phase, total in totals.items()
            )
        )
    if notes:
        table.caption = as_text("; ".join(notes))
        table.caption_justify = "left"
    return table


def _roles_table(observation: Observation, title: str, *, caption: bool = False) -> Table:
    """Verifier-authored role facts for a native observation; no payload or model content.

    Role reasons are the verifier's fixed sentences (steps/verification.py); target output
    never reaches them."""
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
            as_text(role.native_exit_code),
            Text(_line_ranges(role.covered_lines)),
            as_text(role.reason or "-"),
        )
    return table


def _cleanup_text(confirmed: bool) -> Text:
    return Text("confirmed", style="green") if confirmed else Text("NOT confirmed", style="red")


def print_result(
    console: Console, result: InvestigationResult, store: ArtifactStore | None = None
) -> None:
    """Verdict and case stop first, then rounds with their gate-ledger stop, phases,
    identity and totals; never model or payload content. The ledger only describes
    the recorded verdict: it is computed by the evaluator's pure ``gate_ledger``."""
    ledger = gate_ledger(result, verified_rounds(result, store))
    stops = {
        (entry["session"], entry["round"]): entry for entry in ledger if entry["round"] is not None
    }
    style = _VERDICT_STYLES.get(result.verdict, "cyan") if result.verdict else "cyan"
    header = label_grid()
    header.add_row(
        field_label("Verdict"),
        Text(result.verdict.value, style=style)
        if result.verdict
        else Text("not recorded", style="yellow"),
    )
    header.add_row(field_label("Case stop"), _case_stop(ledger))
    header.add_row(
        field_label("Execution"),
        Text(
            result.execution_status.value,
            style=_STATUS_STYLES.get(result.execution_status, "cyan"),
        ),
    )
    header.add_row(field_label("Disposition"), as_text(result.disposition.value))
    header.add_row(field_label("Claimed scope"), as_text(result.scope.value))
    header.add_row(field_label("Evidence scope"), as_text(_EVIDENCE_SCOPE))
    header.add_row(field_label("Fix"), as_text(result.fix_status.value))
    header.add_row(field_label("Run"), as_text(result.run_id))
    header.add_row(field_label("Case"), as_text(result.case_id))
    console.print(Panel(header, title="Corsair · Investigation", border_style=style))
    if result.rounds:
        console.print(_rounds_table(result.rounds, stops))
    else:
        console.print(Text("No rounds recorded.", style="dim"))
    if result.fix_observation is not None:
        console.print(_roles_table(result.fix_observation, "Fixed revision", caption=True))
    if result.timeline:
        console.print(_timeline_table(result.timeline))
    console.print(_identity(result))


def _identity(result: InvestigationResult) -> Panel:
    table = label_grid()
    manifest = result.manifest
    if manifest is not None:
        table.add_row(field_label("Package"), as_text(manifest.package_version))
        table.add_row(field_label("Image"), as_text(short_digest(manifest.image_id)))
        for key, value in (
            ("Request", manifest.request_digest),
            ("Config", manifest.config_digest),
            ("Producer prompt", manifest.producer_prompt_digest),
            ("Auditor prompt", manifest.auditor_prompt_digest),
        ):
            table.add_row(field_label(key), as_text(short_digest(value)))
        for role, model in manifest.models.items():
            table.add_row(field_label(f"{role.title()} model"), as_text(model))
        table.add_row(
            field_label("Evidence policy"),
            as_text(f"{manifest.negative_threshold} negatives · {manifest.max_sessions} sessions"),
        )
    else:
        table.add_row(field_label("Manifest"), Text("not recorded", style="yellow"))
    totals = Table.grid(padding=(0, 2))
    totals.add_row(field_label("Usage complete"), as_text(str(result.usage_complete).lower()))
    for key, total in usage_metrics(result).items():
        if key == "agent_seconds" and total is not None:
            total = f"{total:.1f}"
        name = key.replace("_", " ").capitalize().replace("Llm", "LLM")
        totals.add_row(field_label(name), as_text(total))
    totals.add_row(field_label("Cost"), Text("unknown"))
    layout = Table.grid(padding=(0, 4), expand=True)
    layout.add_column(ratio=3)
    layout.add_column(ratio=2)
    layout.add_row(table, totals)
    artifact = label_grid()
    reference = result.result_artifact
    artifact.add_row(
        field_label("Result SHA-256"), as_text(reference.sha256 if reference else None)
    )
    return Panel(Group(layout, artifact), title="Identity · Totals", border_style="cyan")


def print_observation(console: Console, observation: Observation) -> None:
    """A native reference replay: role facts and identity, explicitly without a verdict."""
    header = label_grid()
    header.add_row(field_label("Verdict"), Text("none · no security verdict", style="dim"))
    header.add_row(field_label("Operation"), as_text(observation.operation_id))
    header.add_row(field_label("Source"), as_text(short_digest(observation.source_digest)))
    header.add_row(field_label("Submission"), as_text(short_digest(observation.submission_digest)))
    header.add_row(field_label("Cleanup"), _cleanup_text(observation.cleanup_confirmed))
    if observation.feedback is not None:
        gate = Text(safe_text(observation.feedback.gate), style="yellow")
        gate.append(f" · {safe_text(observation.feedback.reason)}")
        header.add_row(field_label("Gate"), gate)
    artifact = observation.artifact
    header.add_row(field_label("Evidence SHA-256"), as_text(artifact.sha256 if artifact else None))
    console.print(
        Panel(header, title="Corsair · Native reference observation", border_style="cyan")
    )
    console.print(_roles_table(observation, "Roles"))


def print_explanation(
    console: Console, value: dict[str, Any], store: ArtifactStore | None = None
) -> None:
    """Render the verdict explanation in order, after the result panel when it is present."""
    if isinstance(value.get("result"), dict):
        print_result(console, InvestigationResult.model_validate(value["result"]), store)
    verdict = value.get("verdict")
    style = _VERDICT_STYLES.get(Verdict(verdict), "cyan") if verdict else "cyan"
    table = label_grid()
    for statement in value["statements"]:
        table.add_row(field_label(statement["kind"]), as_text(statement["text"]))
    title = f"Corsair · Why {safe_text(verdict or 'no verdict')} · {safe_text(value['run_id'])}"
    console.print(Panel(table, title=title, border_style=style))
