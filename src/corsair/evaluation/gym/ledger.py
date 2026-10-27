"""The append-only experiment ledger (``ledger.jsonl``) and its rendered ``LEDGER.md``.

The JSONL file is the machine record: one ``LedgerRow`` per reference run or
experiment, never rewritten. ``LEDGER.md`` keeps its hand-written header prose (everything
before ``## Baselines``) and regenerates the tables below it from the JSONL rows.
"""

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from corsair.contracts import (
    GateVerdict,
    LedgerDecision,
    LedgerRow,
    RunContext,
    Scorecard,
    TierGate,
)
from corsair.evaluation.gym.gate import gate as gate_scorecards
from corsair.evaluation.gym.scoring import SCORECARD_FILE, read_scorecard

GENERATED_HEADING = "## Baselines"
# Shown for a value an experiment row does not record, such as a gate it never ran.
ABSENT = "—"
GATED_TIERS = ("tier0", "tier1")

type Identity = tuple[str | None, str | None]


def candidate_identity(sources: Sequence[Identity]) -> Identity:
    """The branch and commit every source names; a short commit agrees with its full form."""
    branches = {branch for branch, _ in sources if branch}
    commits = sorted({commit for _, commit in sources if commit}, key=len)
    if len(branches) > 1 or any(not commits[-1].startswith(commit) for commit in commits):
        raise ValueError(
            "the scorecards, verify record and given branch or commit name different candidates"
        )
    return (next(iter(branches), None), commits[-1] if commits else None)


def build_ledger_row(
    scorecard: Scorecard | None,
    *,
    row_id: str,
    recorded_on: date,
    wave: int,
    entry: Literal["baseline", "experiment"],
    tier: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
    track: str | None = None,
    idea: str | None = None,
    gate: GateVerdict | None = None,
    tier0: TierGate | None = None,
    tier1: TierGate | None = None,
    decision: LedgerDecision | None = None,
    merge_commit: str | None = None,
    lesson: str = "",
    scorecard_path: str | None = None,
) -> LedgerRow:
    """One ledger row; scorecard metrics are recorded only when a scorecard is given."""
    sources: list[Identity] = [(branch, commit)]
    if scorecard is not None:
        sources.append((scorecard.run.git_branch, scorecard.run.git_commit))
    branch, commit = candidate_identity(sources)
    if branch is None or commit is None:
        raise ValueError("a ledger row needs the candidate's git branch and commit")
    metrics = (
        {}
        if scorecard is None
        else {
            "dataset_digest": scorecard.dataset_digest,
            "identity_digests": scorecard.identity_digests,
            "budgets_digest": scorecard.budgets_digest,
            "repeats": scorecard.repeats,
            "scorecard": scorecard_path,
            "objective_j": scorecard.objective_j,
            "macro_verified_accuracy": scorecard.macro_verified_accuracy,
            "worst_language_verified_accuracy": scorecard.worst_language_verified_accuracy,
            "macro_effective_tokens": scorecard.macro_effective_tokens,
            "macro_p50_seconds": scorecard.macro_p50_seconds,
        }
    )
    return LedgerRow.model_validate(
        {
            "id": row_id,
            "recorded_on": recorded_on,
            "wave": wave,
            "entry": entry,
            "branch": branch,
            "commit": commit,
            "tier": tier,
            "track": track,
            "idea": idea,
            **metrics,
            "gate": gate,
            "tier0": tier0,
            "tier1": tier1,
            "decision": decision,
            "merge_commit": merge_commit,
            "lesson": lesson,
        }
    )


def reference_scorecard(rows: Sequence[LedgerRow], reference: str) -> Path:
    """A gate reference's scorecard: a ledger row id names that row's scorecard, else a path."""
    for row in rows:
        if row.id == reference:
            if row.scorecard is None:
                raise ValueError(f"ledger row {row.id} records no scorecard to gate against")
            return Path(row.scorecard)
    return Path(reference)


def latest_baseline(rows: Sequence[LedgerRow], tier: str) -> str:
    """The id of the most recent baseline row with a scorecard for one tier."""
    ids = [row.id for row in rows if row.entry == "baseline" and row.tier == tier and row.scorecard]
    if not ids:
        raise ValueError(f"the ledger has no {tier} baseline row with a scorecard")
    return ids[-1]


def gate_tier(
    rows: Sequence[LedgerRow], candidate: Path, reference: str
) -> tuple[TierGate, RunContext]:
    """Gate one tier's candidate (a run directory or a scorecard file) against a reference."""
    run_dir = candidate if candidate.is_dir() else None
    path = candidate / SCORECARD_FILE if run_dir is not None else candidate
    card = read_scorecard(path)
    verdict = gate_scorecards(read_scorecard(reference_scorecard(rows, reference)), card)
    gated = TierGate(
        reference=reference,
        scorecard=str(path),
        run_dir=None if run_dir is None else str(run_dir),
        gate=verdict,
    )
    return gated, card.run


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


def gate_cell(verdict: GateVerdict | None) -> str:
    """Code-owned gate result: the decision, its reason codes and any regressed languages."""
    if verdict is None:
        return ABSENT
    details = ", ".join(reason.value for reason in verdict.reasons)
    if verdict.regressed_languages:
        details += "; regressed: " + ", ".join(verdict.regressed_languages)
    return f"{verdict.decision.value} ({details})" if details else verdict.decision.value


def tier_gate(row: LedgerRow, tier: str) -> GateVerdict | None:
    """A row's gate for one tier: its tier gate, else a ``--baseline`` gate of that tier."""
    gated = row.tier0 if tier == "tier0" else row.tier1
    if gated is not None:
        return gated.gate
    return row.gate if row.tier == tier else None


def _per_tier(row: LedgerRow, value: Callable[[GateVerdict], str]) -> str:
    gates = [tier_gate(row, tier) for tier in GATED_TIERS]
    if all(verdict is None for verdict in gates):
        return ABSENT
    return " / ".join(ABSENT if verdict is None else value(verdict) for verdict in gates)


def _signed(value: float | None) -> str:
    return "unknown" if value is None else f"{value:+.3f}"


def _decision(row: LedgerRow) -> str:
    if row.decision is None:
        return ABSENT
    if row.merge_commit is None:
        return row.decision
    return f"{row.decision} `{_cell(row.merge_commit[:7])}`"


def _baseline_rows(rows: Sequence[LedgerRow]) -> list[list[str]]:
    return [
        [
            _cell(row.id),
            f"`{row.commit[:7]}`",
            _cell(row.tier),
            str(row.repeats),
            f"`{(row.dataset_digest or '')[:12]}`",
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
            f"`{_cell(row.branch)}@{_cell(row.commit[:7])}`",
            *(gate_cell(tier_gate(row, tier)) for tier in GATED_TIERS),
            _per_tier(row, lambda verdict: _signed(verdict.delta_j)),
            _per_tier(row, lambda verdict: _number(verdict.token_ratio)),
            _decision(row),
            _cell(row.lesson),
        ]
        for row in rows
        if row.entry == "experiment" and row.wave == wave
    ]


def _gates_summary(row: LedgerRow) -> str:
    return "; ".join(
        f"{tier} {gate_cell(verdict)}"
        for tier in GATED_TIERS
        if (verdict := tier_gate(row, tier)) is not None
    )


def _rejected_rows(rows: Sequence[LedgerRow]) -> list[list[str]]:
    return [
        [_cell(row.idea or row.id), str(row.wave), _cell(row.lesson or _gates_summary(row))]
        for row in rows
        if row.decision == "rejected"
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
                [
                    "Experiment",
                    "Track",
                    "Branch@commit",
                    "Tier0 gate",
                    "Tier1 gate",
                    "ΔJ (t0 / t1)",
                    "Token ratio (t0 / t1)",
                    "Decision",
                    "Lesson",
                ],
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
