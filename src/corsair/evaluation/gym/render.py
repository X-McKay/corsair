"""Markdown views of a gate verdict and a scorecard, from code-owned text only.

Only numbers, fixed labels, code identifiers (languages, recipe kinds, ledger gate names)
and the fixed reason sentences below are printed; no model-authored text reaches a view.
"""

from collections.abc import Mapping, Sequence

from corsair.contracts import GateReason, GateVerdict, GroupSummary, Scorecard

REASON_TEXT: dict[GateReason, str] = {
    GateReason.DATASET_MISMATCH: "The runs scored different frozen datasets.",
    GateReason.BUDGETS_MISMATCH: "The runs used different efficiency budgets.",
    GateReason.SLICED: "A run covered only part of its dataset.",
    GateReason.REPEATS_BELOW_MINIMUM: "A run has fewer repeats per case than the gate requires.",
    GateReason.TOKENS_UNKNOWN: "Effective token usage is unknown for a run.",
    GateReason.LANGUAGE_REGRESSED: "A language's majority verified accuracy fell.",
    GateReason.OBJECTIVE_BELOW_THRESHOLD: "The objective J gained less than the required margin.",
    GateReason.TOKENS_ABOVE_CEILING: "Effective tokens rose above the allowed ratio.",
}


def _number(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def _signed(value: float | None) -> str:
    return "unknown" if value is None else f"{value:+.3f}"


def _count(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _count_delta(before: int | None, after: int | None) -> str:
    return "unknown" if before is None or after is None else f"{after - before:+d}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _stops(stops: Mapping[str, int]) -> str:
    return ", ".join(f"{gate} {count}" for gate, count in stops.items()) or "none"


def render_gate(verdict: GateVerdict, baseline: Scorecard, candidate: Scorecard) -> str:
    """The gate decision, its fixed reasons and a side-by-side metric table."""
    lines = [
        f"## Gate: {verdict.decision.value}",
        "",
        f"Baseline `{verdict.baseline_run_id}`, candidate `{verdict.candidate_run_id}`.",
        "",
    ]
    lines.extend(f"- {REASON_TEXT[reason]}" for reason in verdict.reasons)
    if verdict.reasons:
        lines.append("")
    metrics = [
        ("Objective J", baseline.objective_j, candidate.objective_j),
        ("Macro reward", baseline.macro_reward, candidate.macro_reward),
        (
            "Macro verified accuracy",
            baseline.macro_verified_accuracy,
            candidate.macro_verified_accuracy,
        ),
        (
            "Worst language verified accuracy",
            baseline.worst_language_verified_accuracy,
            candidate.worst_language_verified_accuracy,
        ),
        (
            "Macro effective tokens",
            baseline.macro_effective_tokens,
            candidate.macro_effective_tokens,
        ),
        ("Macro p50 seconds", baseline.macro_p50_seconds, candidate.macro_p50_seconds),
    ]
    rows = [
        [
            name,
            _number(before),
            _number(after),
            _signed(None if before is None or after is None else after - before),
        ]
        for name, before, after in metrics
    ]
    rows.append(["Repeats", str(baseline.repeats), str(candidate.repeats), ""])
    lines.extend(_table(["Metric", "Baseline", "Candidate", "Delta"], rows))
    lines.append("")
    language_rows = []
    for language, delta in verdict.language_deltas.items():
        before = baseline.languages[language]
        after = candidate.languages.get(language)
        capped_after = None if after is None else after.capped_call_episodes
        language_rows.append(
            [
                language,
                _number(before.verified_accuracy),
                _number(None if after is None else after.verified_accuracy),
                _signed(delta),
                "yes" if language in verdict.regressed_languages else "no",
                _count(before.capped_call_episodes),
                _count(capped_after),
                _count_delta(before.capped_call_episodes, capped_after),
            ]
        )
    lines.extend(
        _table(
            [
                "Language",
                "Baseline verified",
                "Candidate verified",
                "Delta",
                "Regressed",
                "Baseline capped eps",
                "Candidate capped eps",
                "Capped delta",
            ],
            language_rows,
        )
    )
    return "\n".join(lines) + "\n"


def _group_rows(groups: Mapping[str, GroupSummary]) -> list[list[str]]:
    return [
        [
            name,
            str(summary.cases),
            str(summary.attempts),
            _number(summary.raw_accuracy),
            _number(summary.verified_accuracy),
            _number(summary.mean_reward),
            _number(summary.mean_effective_tokens, 0),
            _number(summary.p50_seconds, 1),
            _number(summary.p95_seconds, 1),
            str(summary.usage_unknown),
            _number(summary.mean_thought_share),
            _count(summary.capped_call_episodes),
            _count(summary.reasoning_cap_exhausted),
            _stops(summary.failure_stops),
        ]
        for name, summary in groups.items()
    ]


_GROUP_HEADER = [
    "Cases",
    "Attempts",
    "Raw acc",
    "Verified acc",
    "Mean reward",
    "Mean eff. tokens",
    "p50 s",
    "p95 s",
    "Usage unknown",
    "Thought share",
    "Capped eps",
    "Reasoning capped",
    "Failure stops",
]


def render_scorecard(scorecard: Scorecard) -> str:
    """Headline objective and per-language and per-kind summaries."""
    lines = [
        f"## Scorecard `{scorecard.run.run_id}`",
        "",
        f"- Objective J: {_number(scorecard.objective_j)}",
        f"- Macro reward: {_number(scorecard.macro_reward)}",
        f"- Macro verified accuracy: {_number(scorecard.macro_verified_accuracy)}",
        "- Worst language verified accuracy: "
        + _number(scorecard.worst_language_verified_accuracy),
        f"- Macro effective tokens: {_number(scorecard.macro_effective_tokens, 0)}",
        f"- Macro p50 seconds: {_number(scorecard.macro_p50_seconds, 1)}",
        f"- Macro thought share: {_number(scorecard.macro_thought_share)}",
        f"- Capped-call episodes: {_count(scorecard.capped_call_episodes)}; "
        f"reasoning cap exhausted: {_count(scorecard.reasoning_cap_exhausted)}",
        f"- Repeats: {scorecard.repeats}; sliced: {'yes' if scorecard.sliced else 'no'}",
        f"- Dataset digest: `{scorecard.dataset_digest}`",
        f"- Budgets digest: `{scorecard.budgets_digest or 'none'}`",
        "",
    ]
    lines.extend(_table(["Language", *_GROUP_HEADER], _group_rows(scorecard.languages)))
    lines.append("")
    lines.extend(_table(["Kind", *_GROUP_HEADER], _group_rows(scorecard.kinds)))
    return "\n".join(lines) + "\n"
