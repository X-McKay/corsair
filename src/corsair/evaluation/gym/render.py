"""Markdown views of a gate verdict and a scorecard, from code-owned text only.

Only numbers, fixed labels, code identifiers (languages, recipe kinds, ledger gate names)
and the fixed reason sentences below are printed; no model-authored text reaches a view.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateTrack,
    GateVerdict,
    GroupSummary,
    NoiseBand,
    NoiseSpread,
    OperationalEpisode,
    Scorecard,
    TargetExceptionEpisode,
)

REASON_TEXT: dict[GateReason, str] = {
    GateReason.DATASET_MISMATCH: "The runs scored different frozen datasets.",
    GateReason.BUDGETS_MISMATCH: "The runs used different efficiency budgets.",
    GateReason.SLICED: "A run covered only part of its dataset.",
    GateReason.REPEATS_BELOW_MINIMUM: "A run has fewer repeats per case than the gate requires.",
    GateReason.TOKENS_UNKNOWN: "Effective token usage is unknown for a run.",
    GateReason.LANGUAGE_REGRESSED: "A language's majority verified accuracy fell.",
    GateReason.OBJECTIVE_BELOW_THRESHOLD: "The objective J gained less than the required margin.",
    GateReason.TOKENS_ABOVE_CEILING: "Effective tokens rose above the allowed ratio.",
    GateReason.OPERATIONALLY_CONFOUNDED: (
        "A regressed language would not regress had its operational stops verified; "
        "re-run cleanly before reading it."
    ),
    GateReason.ACCURACY_NOT_IMPROVED: (
        "Neither macro nor the target language's verified accuracy rose by one case's majority."
    ),
    GateReason.ACCURACY_BELOW_BASELINE: "Macro verified accuracy fell below the baseline's.",
    GateReason.EFFICIENCY_NOT_IMPROVED: (
        "Neither macro effective tokens nor comparable macro p50 seconds fell by 10 %."
    ),
    GateReason.LATENCY_NOT_COMPARABLE: (
        "Latency was not counted: the runs recorded different or unknown concurrency, or an "
        "operational episode (or an unknown count of them)."
    ),
    GateReason.NOISE_MISMATCH: (
        "The noise band scored a different dataset, budgets or repeat count than the runs."
    ),
    GateReason.WITHIN_NOISE: (
        "Every regression lies within the measured noise band: run the candidate once more "
        "(a confirmation run) and gate that run before deciding."
    ),
    GateReason.IDENTITY_MISMATCH: (
        "The runs recorded different, or unknown, configuration identities."
    ),
    GateReason.REPEATS_MISMATCH: "The runs have different repeats per case.",
}

TRACK_TEXT: dict[GateTrack, str] = {
    "objective": (
        "Objective track: no language regressed, J gained at least 0.01 and macro "
        "effective tokens stayed within 1.10x."
    ),
    "accuracy": (
        "Accuracy track: no language regressed, macro (or the target language's) verified "
        "accuracy rose by at least one case's majority, and macro effective tokens stayed "
        "within 1.10x; J is reported, not decided on."
    ),
    "efficiency": (
        "Efficiency track: no language regressed, macro verified accuracy held, and macro "
        "effective tokens or comparable macro p50 seconds fell to 0.90x or below; J is "
        "reported, not decided on."
    ),
}


SMOKE_TEXT = (
    "Smoke gate: the track's improvement criterion is reported but does not decide; "
    "an ACCEPTED smoke gate is not an acceptance."
)

SINGLE_CASE_TEXT = (
    "One episode flips a single-case language's verified accuracy, and so J's worst-language "
    "term; read a regression there as one case."
)

NOISE_TEXT = (
    "A delta inside the band is noise; an improvement must exceed it, and a regression "
    "inside it is inconclusive."
)


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


def _identity_line(changes: Mapping[str, bool | None]) -> str:
    """Which identity components differ, and which are unknown on either side."""
    changed = [name for name, differs in changes.items() if differs]
    unknown = [name for name, differs in changes.items() if differs is None]
    line = "Identity changes: " + (", ".join(changed) or "none")
    return line + (f"; unknown: {', '.join(unknown)}" if unknown else "") + "."


def render_gate(verdict: GateVerdict, baseline: Scorecard, candidate: Scorecard) -> str:
    """The gate decision, its fixed reasons and a side-by-side metric table."""
    labels = (["smoke"] if verdict.smoke else []) + (
        [] if verdict.track == "objective" else [f"{verdict.track} track"]
    )
    title = f" ({', '.join(labels)})" if labels else ""
    lines = [
        f"## Gate{title}: {verdict.decision.value}",
        "",
        f"Baseline `{verdict.baseline_run_id}`, candidate `{verdict.candidate_run_id}`.",
        "",
        TRACK_TEXT[verdict.track],
        "",
    ]
    if verdict.target_language is not None:
        lines.extend([f"Target language: {verdict.target_language}.", ""])
    if verdict.smoke:
        lines.extend([SMOKE_TEXT, ""])
    lines.extend([_identity_line(verdict.identity_changes), ""])
    if verdict.single_case_languages:
        single = ", ".join(verdict.single_case_languages)
        lines.extend([f"Single-case languages: {single}. {SINGLE_CASE_TEXT}", ""])
    lines.extend(f"- {REASON_TEXT[reason]}" for reason in verdict.reasons)
    if verdict.operationally_confounded_languages:
        confounded = ", ".join(verdict.operationally_confounded_languages)
        lines.append(f"- Operationally confounded: {confounded}")
    if verdict.reasons:
        lines.append("")
    lines.extend(_noise_lines(verdict))
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
    rows.append(["Token ratio", "", _number(verdict.token_ratio), ""])
    rows.append(["p50 seconds ratio", "", _number(verdict.seconds_ratio), ""])
    lines.extend(_table(["Metric", "Baseline", "Candidate", "Delta"], rows))
    lines.append("")
    language_rows = []
    for language, delta in verdict.language_deltas.items():
        before = baseline.languages[language]
        after = candidate.languages.get(language)
        capped_after = None if after is None else after.capped_call_episodes
        operational_after = None if after is None else after.operational_episodes
        target_after = None if after is None else after.target_exception_episodes
        language_rows.append(
            [
                language,
                _number(before.verified_accuracy),
                _number(None if after is None else after.verified_accuracy),
                _signed(delta),
                _regressed(verdict, language),
                _count(before.capped_call_episodes),
                _count(capped_after),
                _count_delta(before.capped_call_episodes, capped_after),
                _count(before.operational_episodes),
                _count(operational_after),
                _count_delta(before.operational_episodes, operational_after),
                _count(before.target_exception_episodes),
                _count(target_after),
                _count_delta(before.target_exception_episodes, target_after),
                "yes" if language in verdict.operationally_confounded_languages else "no",
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
                "Baseline operational eps",
                "Candidate operational eps",
                "Operational delta",
                "Baseline target-exception eps",
                "Candidate target-exception eps",
                "Target-exception delta",
                "Confounded",
            ],
            language_rows,
        )
    )
    return "\n".join(lines) + "\n"


def _regressed(verdict: GateVerdict, language: str) -> str:
    if language not in verdict.regressed_languages:
        return "no"
    return "yes (single case)" if language in verdict.single_case_languages else "yes"


def _difference_band(spread: NoiseSpread | None) -> str:
    return "unknown" if spread is None else f"±{spread.band:.3f}"


def _ratio_band(spread: NoiseSpread | None, suffix: str = "") -> str:
    if spread is None or spread.max_ratio is None:
        return "unknown"
    return f"{1 / spread.max_ratio:.3f}{suffix} to {spread.max_ratio:.3f}{suffix}"


def _noise_lines(verdict: GateVerdict) -> list[str]:
    """The band a gate read, each metric's delta against it, and what lies within it."""
    noise = verdict.noise
    if noise is None:
        return []
    runs = ", ".join(f"`{run}`" for run in noise.runs)
    lines = [f"Noise band from {noise.n_runs} runs: {runs}. {NOISE_TEXT}", ""]
    if verdict.decision is GateDecision.INCOMPARABLE:
        # Nothing was compared, so no delta was read against the band.
        return lines

    def within(flag: bool) -> str:
        return "yes" if flag else "no"

    metrics = set(verdict.within_noise)
    rows = [
        [
            "Objective J",
            _signed(verdict.delta_j),
            _difference_band(noise.objective_j),
            within("objective_j" in metrics),
        ],
        [
            "Macro verified accuracy",
            _signed(verdict.delta_macro_verified_accuracy),
            _difference_band(noise.macro_verified_accuracy),
            within("macro_verified_accuracy" in metrics),
        ],
        [
            "Token ratio",
            _number(verdict.token_ratio),
            _ratio_band(noise.macro_effective_tokens),
            within("macro_effective_tokens" in metrics),
        ],
        [
            "p50 seconds ratio",
            _number(verdict.seconds_ratio),
            _ratio_band(noise.macro_p50_seconds),
            within("macro_p50_seconds" in metrics),
        ],
    ]
    rows.extend(
        [
            f"{language} verified accuracy",
            _signed(delta),
            _difference_band(noise.languages.get(language)),
            within(language in verdict.languages_within_noise),
        ]
        for language, delta in verdict.language_deltas.items()
    )
    lines.extend(_table(["Metric", "Delta", "Noise band", "Within noise"], rows))
    named = ", ".join(verdict.within_noise) or "none"
    languages = ", ".join(verdict.languages_within_noise) or "none"
    lines.extend(["", f"Within noise: {named}; languages: {languages}.", ""])
    return lines


def render_noise(band: NoiseBand) -> str:
    """Each metric per run with its mean, half-range, deviation and the band a gate reads."""
    runs = [f"`{run}`" for run in band.runs]
    lines = [
        f"## Noise band: {band.n_runs} runs",
        "",
        f"- Dataset digest: `{band.dataset_digest}`",
        f"- Budgets digest: `{band.budgets_digest or 'none'}`",
        f"- Repeats: {band.repeats}",
        "- Configuration identity: "
        + (
            ", ".join(f"`{value[:12]}`" for value in band.run_identity.get("config", []))
            or "unknown"
        ),
        "",
    ]
    metrics: list[tuple[str, NoiseSpread | None, int, bool]] = [
        ("Objective J", band.objective_j, 3, False),
        ("Macro verified accuracy", band.macro_verified_accuracy, 3, False),
        ("Macro effective tokens", band.macro_effective_tokens, 0, True),
        ("Macro p50 seconds", band.macro_p50_seconds, 1, True),
    ]
    metrics.extend(
        (f"{language} verified accuracy", spread, 3, False)
        for language, spread in band.languages.items()
    )
    rows = []
    for name, spread, digits, ratio in metrics:
        if spread is None:
            rows.append(
                [name, *("unknown" for _ in runs), "unknown", "unknown", "unknown", "unknown"]
            )
            continue
        rows.append(
            [
                name,
                *(_number(value, digits) for value in spread.values),
                _number(spread.mean, digits),
                _number(spread.half_range, digits),
                _number(spread.stdev, digits),
                _ratio_band(spread, "x") if ratio else _difference_band(spread),
            ]
        )
    lines.extend(_table(["Metric", *runs, "Mean", "Half-range", "Stdev", "Gate band"], rows))
    lines.extend(["", NOISE_TEXT])
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
            _count(summary.operational_episodes),
            _count(summary.target_exception_episodes),
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
    "Operational eps",
    "Target-exception eps",
]


def _operational_lines(stops: Sequence[OperationalEpisode]) -> list[str]:
    if not stops:
        return []
    lines = ["", "Operational stops (scored as failures; re-run before reading them):", ""]
    lines.extend(f"- `{item.case_id}` repeat {item.repeat}: {item.reason.value}" for item in stops)
    return lines


def _target_exception_lines(episodes: Sequence[TargetExceptionEpisode]) -> list[str]:
    if not episodes:
        return []
    lines = [
        "",
        "Target-side exceptions (verdict ERROR from a completed run that raised in the target; "
        "scored 0, neither a false label nor an infrastructure fault):",
        "",
    ]
    lines.extend(f"- `{item.case_id}` repeat {item.repeat}" for item in episodes)
    return lines


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
        f"- Operational episodes: {_count(scorecard.operational_episodes)}",
        f"- Target-exception episodes: {_count(scorecard.target_exception_episodes)}",
        f"- Repeats: {scorecard.repeats}; sliced: {'yes' if scorecard.sliced else 'no'}",
        f"- Dataset digest: `{scorecard.dataset_digest}`",
        f"- Budgets digest: `{scorecard.budgets_digest or 'none'}`",
        "",
    ]
    lines.extend(_table(["Language", *_GROUP_HEADER], _group_rows(scorecard.languages)))
    lines.append("")
    lines.extend(_table(["Kind", *_GROUP_HEADER], _group_rows(scorecard.kinds)))
    lines.extend(_operational_lines(scorecard.operational_stops))
    lines.extend(_target_exception_lines(scorecard.target_exceptions))
    return "\n".join(lines) + "\n"


_RUNS_HEADER = [
    "Run",
    "Commit",
    "Tier",
    "Repeats",
    "Sliced",
    "J",
    "Verified acc",
    "Worst language",
    "Eff. tokens",
    "p50 s",
    "Capped eps",
    "Run directory",
]


def _commit(row: Mapping[str, Any]) -> str:
    """The start commit, then a marker when the checkout changed before the run finished."""
    commit = row.get("git_commit")
    if not commit:
        return "unknown"
    text = commit[:7] + ("+dirty" if row.get("git_dirty") else "")
    if row.get("commit_changed"):
        text += f", changed to {str(row['git_commit_at_finish'])[:7]} at finish"
    if row.get("source_dirty_at_finish") and not row.get("git_dirty"):
        text += ", dirty at finish"
    return text


def render_runs(rows: Sequence[Mapping[str, Any]]) -> str:
    """Stored runs, newest first, as ``corsair gym runs`` lists them."""
    if not rows:
        return "No stored gym runs.\n"
    table = [
        [
            f"`{row['run_id']}`",
            _commit(row),
            row.get("tier") or "unknown",
            str(row["repeats"]),
            "yes" if row["sliced"] else "no",
            _number(row["objective_j"]),
            _number(row["macro_verified_accuracy"]),
            "unknown"
            if row["worst_language"] is None
            else f"{row['worst_language']} {_number(row['worst_language_verified_accuracy'])}",
            _number(row["macro_effective_tokens"], 0),
            _number(row["macro_p50_seconds"], 1),
            _count(row["capped_call_episodes"]),
            f"`{row['run_dir']}`",
        ]
        for row in rows
    ]
    return "\n".join(_table(_RUNS_HEADER, table)) + "\n"
