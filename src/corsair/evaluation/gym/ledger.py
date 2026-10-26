"""The append-only experiment ledger (``ledger.jsonl``) and its rendered ``LEDGER.md``.

The JSONL file is the machine record: one ``LedgerRow`` per reference run or gated
experiment, never rewritten. ``LEDGER.md`` keeps its hand-written header prose (everything
before ``## Baselines``) and regenerates the tables below it from the JSONL rows.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from corsair.contracts import GateDecision, GateVerdict, LedgerRow, Scorecard
from corsair.evaluation.gym.render import REASON_TEXT

GENERATED_HEADING = "## Baselines"


def build_ledger_row(
    scorecard: Scorecard,
    *,
    row_id: str,
    recorded_on: date,
    wave: int,
    entry: Literal["baseline", "experiment"],
    tier: str,
    track: str | None = None,
    idea: str | None = None,
    gate: GateVerdict | None = None,
    lesson: str = "",
    scorecard_path: str | None = None,
) -> LedgerRow:
    """One ledger row from a scorecard and, for an experiment, its gate verdict."""
    run = scorecard.run
    if run.git_branch is None or run.git_commit is None:
        raise ValueError("a ledger row needs the scorecard's git branch and commit")
    return LedgerRow(
        id=row_id,
        recorded_on=recorded_on,
        wave=wave,
        entry=entry,
        branch=run.git_branch,
        commit=run.git_commit,
        tier=tier,
        track=track,
        idea=idea,
        dataset_digest=scorecard.dataset_digest,
        identity_digests=scorecard.identity_digests,
        budgets_digest=scorecard.budgets_digest,
        repeats=scorecard.repeats,
        scorecard=scorecard_path,
        objective_j=scorecard.objective_j,
        macro_verified_accuracy=scorecard.macro_verified_accuracy,
        worst_language_verified_accuracy=scorecard.worst_language_verified_accuracy,
        macro_effective_tokens=scorecard.macro_effective_tokens,
        macro_p50_seconds=scorecard.macro_p50_seconds,
        gate=gate,
        lesson=lesson,
    )


def read_ledger(path: Path) -> list[LedgerRow]:
    """Every row of the ledger; a missing file is an empty ledger."""
    if not path.exists():
        return []
    return [LedgerRow.model_validate_json(line) for line in path.read_text().splitlines() if line]


def append_ledger(path: Path, row: LedgerRow) -> None:
    """Append one row after validating the existing ledger; an existing id is refused."""
    existing = read_ledger(path)
    if any(item.id == row.id for item in existing):
        raise ValueError(f"ledger already records {row.id}")
    content = path.read_bytes() if path.exists() else b""
    if content and not content.endswith(b"\n"):
        raise ValueError("ledger does not end with a newline; refusing to append")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(row.model_dump_json() + "\n")


def _cell(value: str | None) -> str:
    """One Markdown table cell: single line, pipes escaped."""
    if not value:
        return ""
    return " ".join(value.split()).replace("|", "\\|")


def _number(value: float | None, digits: int = 3) -> str:
    return "unknown" if value is None else f"{value:.{digits}f}"


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def gate_summary(gate: GateVerdict | None) -> str:
    """Code-owned one-line gate result: deltas, or the fixed reasons it was not comparable."""
    if gate is None:
        return ""
    if gate.decision is GateDecision.INCOMPARABLE:
        return "; ".join(REASON_TEXT[reason] for reason in gate.reasons)
    parts = [
        f"ΔJ {'unknown' if gate.delta_j is None else f'{gate.delta_j:+.3f}'}",
        f"tokens ×{_number(gate.token_ratio)}",
    ]
    if gate.regressed_languages:
        parts.append("regressed: " + ", ".join(gate.regressed_languages))
    return "; ".join(parts)


def _baseline_rows(rows: Sequence[LedgerRow]) -> list[list[str]]:
    return [
        [
            _cell(row.id),
            f"`{row.commit[:7]}`",
            _cell(row.tier),
            str(row.repeats),
            f"`{row.dataset_digest[:12]}`",
            _number(row.objective_j),
            _number(row.macro_verified_accuracy),
            _number(row.worst_language_verified_accuracy),
            _number(row.macro_effective_tokens, 0),
            _number(row.macro_p50_seconds, 1),
            _cell(row.scorecard),
        ]
        for row in rows
        if row.entry == "baseline"
    ]


def _wave_rows(rows: Sequence[LedgerRow], wave: int) -> list[list[str]]:
    return [
        [
            _cell(row.id),
            _cell(row.track),
            f"`{_cell(row.branch)}`",
            row.gate.decision.value if row.gate is not None else "",
            _cell(gate_summary(row.gate)),
            _cell(row.lesson),
        ]
        for row in rows
        if row.entry == "experiment" and row.wave == wave
    ]


def _rejected_rows(rows: Sequence[LedgerRow]) -> list[list[str]]:
    return [
        [_cell(row.idea or row.id), str(row.wave), _cell(row.lesson or gate_summary(row.gate))]
        for row in rows
        if row.gate is not None and row.gate.decision is GateDecision.REJECTED
    ]


def ledger_header(markdown: str) -> str:
    """The hand-written prose above the generated tables."""
    head, found, _ = markdown.partition(f"\n{GENERATED_HEADING}\n")
    if not found:
        raise ValueError(f"LEDGER.md has no '{GENERATED_HEADING}' heading")
    return head.rstrip("\n") + "\n"


def render_ledger(rows: Sequence[LedgerRow], header: str) -> str:
    """Deterministic Markdown: header prose, baselines, waves, then rejected ideas."""
    lines = [header.rstrip("\n"), "", GENERATED_HEADING, ""]
    lines.extend(
        _table(
            [
                "Id",
                "Commit",
                "Tier",
                "Repeats",
                "Dataset digest",
                "Objective J",
                "Macro verified acc",
                "Worst language",
                "Macro eff. tokens",
                "p50 s",
                "Scorecard",
            ],
            _baseline_rows(rows),
        )
    )
    lines.extend(["", "## Waves"])
    for wave in sorted({row.wave for row in rows if row.entry == "experiment"}):
        lines.extend(["", f"### Wave {wave}", ""])
        lines.extend(
            _table(
                ["Experiment", "Track", "Branch", "Decision", "Gate result", "Lesson"],
                _wave_rows(rows, wave),
            )
        )
    lines.extend(["", "## Rejected ideas (do not retry without new evidence)", ""])
    lines.extend(_table(["Idea", "Wave", "Why it failed"], _rejected_rows(rows)))
    return "\n".join(lines) + "\n"


def render_ledger_file(ledger_path: Path, markdown_path: Path) -> str:
    """Rewrite ``LEDGER.md`` below its header from the JSONL ledger; return the text."""
    text = render_ledger(read_ledger(ledger_path), ledger_header(markdown_path.read_text()))
    markdown_path.write_text(text)
    return text
