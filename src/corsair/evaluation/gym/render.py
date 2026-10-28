"""Markdown views of a gate verdict and a scorecard, from code-owned text only.

Only numbers, fixed labels, code identifiers (languages, recipe kinds, ledger gate names)
and the fixed reason sentences below are printed; no model-authored text reaches a view.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from corsair.contracts import (
    CaseStability,
    EpisodeRate,
    FlipNoise,
    GateDecision,
    GateReason,
    GateTrack,
    GateVerdict,
    GroupSummary,
    NoiseBand,
    NoiseCase,
    NoiseSpread,
    OperationalEpisode,
    PairedCase,
    Scorecard,
    TargetExceptionEpisode,
)
from corsair.evaluation.gym.gate import deciding_accuracy_spread, inside_band

REASON_TEXT: dict[GateReason, str] = {
    GateReason.DATASET_MISMATCH: "The runs scored different frozen datasets.",
    GateReason.BUDGETS_MISMATCH: "The runs used different efficiency budgets.",
    GateReason.SLICED: "A run covered only part of its dataset.",
    GateReason.REPEATS_BELOW_MINIMUM: "A run has fewer repeats per case than the gate requires.",
    GateReason.TOKENS_UNKNOWN: "Effective token usage is unknown for a run.",
    GateReason.LANGUAGE_REGRESSED: "A language's majority verified accuracy fell.",
    GateReason.OBJECTIVE_BELOW_THRESHOLD: "The objective J gained less than the required margin.",
    GateReason.TOKENS_ABOVE_CEILING: (
        "Effective tokens rose above the allowed ratio (to the noise band's mean when a band "
        "was read)."
    ),
    GateReason.OPERATIONALLY_CONFOUNDED: (
        "A regressed language would not regress had its operational stops verified; "
        "re-run cleanly before reading it."
    ),
    GateReason.ACCURACY_NOT_IMPROVED: (
        "Neither macro nor the target language's verified accuracy rose by one case's "
        "majority beyond noise (the band's spread, or an exact test on the language's "
        "episodes)."
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
        "Every regression lies within the measured noise (the band's spread, or an exact "
        "test on episodes that does not separate the rates): run the candidate once more "
        "(a confirmation run) and gate that run before deciding."
    ),
    GateReason.PAIRED_REGRESSION: (
        "More cases of the deciding languages went from a majority pass to a majority fail "
        "than the reverse."
    ),
    GateReason.SLICE_MISMATCH: (
        "The candidate's slice is not a set of cases the baseline scored, or the baseline "
        "is sliced to other cases."
    ),
    GateReason.SLICE_REGRESSED: (
        "A slice case went from a majority pass to a majority fail outside noise."
    ),
    GateReason.SLICE_NOT_IMPROVED: (
        "No slice case went from a majority fail to a majority pass outside noise."
    ),
    GateReason.IDENTITY_MISMATCH: (
        "The runs recorded different, or unknown, configuration identities."
    ),
    GateReason.REPEATS_MISMATCH: "The runs have different repeats per case.",
}

# A gate given a noise band measures these reasons' deltas from the band's mean.
BAND_REASON_TEXT: dict[GateReason, str] = {
    GateReason.LANGUAGE_REGRESSED: (
        "A language's majority verified accuracy fell below the noise band's mean for it "
        "(below the installed reference's, for a language the band lacks)."
    ),
    GateReason.OBJECTIVE_BELOW_THRESHOLD: (
        "The objective J gained less than the required margin over the noise band's mean, "
        "or not beyond the band."
    ),
    GateReason.ACCURACY_NOT_IMPROVED: (
        "Neither macro nor the target language's verified accuracy rose above the noise "
        "band's mean by one case's majority beyond noise (the band's spread, or an exact "
        "test on the language's episodes)."
    ),
    GateReason.ACCURACY_BELOW_BASELINE: (
        "Macro verified accuracy fell below the noise band's mean."
    ),
    GateReason.WITHIN_NOISE: (
        "Every regression, measured from the noise band's mean, lies within the measured "
        "noise (the band's spread, or an exact test on episodes that does not separate the "
        "rates): run the candidate once more (a confirmation run) and gate that run before "
        "deciding."
    ),
}


def reason_text(reason: GateReason, verdict: GateVerdict) -> str:
    """A reason's fixed sentence; the band-mean wording when the gate measured from it."""
    if verdict.anchored_to_band and reason in BAND_REASON_TEXT:
        return BAND_REASON_TEXT[reason]
    return REASON_TEXT[reason]


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

NOISE_CASES_TEXT = (
    "Each case's episodes are pooled over the runs. A case is stable pass when a run of the "
    "band's repeats at its pooled rate fails its majority with probability at most 0.05, "
    "stable fail when it passes its majority with probability at most 0.05, and unstable "
    "otherwise. A gate reads a flip, and a deciding language, by Fisher's exact test on the "
    "candidate's episodes against these pooled episodes."
)

LEGACY_CASES_TEXT = (
    "The band carries no pooled counts (it was written before them): a case is stable when "
    "its majority outcome was the same in every run and unstable otherwise, and a gate reads "
    "a flip of an unstable case, or in a language whose band is a whole case, as noise."
)

# Why a flip is within noise, as the paired view names it.
FLIP_NOISE_TEXT: dict[FlipNoise, str] = {
    "language_band": "language band",
    "unstable_case": "unstable case",
    "episode_rate": "episode rate",
}

INSTALLED = " (installed reference)"
NOT_IN_BAND_TEXT = "Not in the noise band (read against the installed reference)"


def band_anchor_text(runs: int) -> str:
    """The one sentence a gate view measured from the band's mean leads with."""
    return (
        f"Deltas are measured from the mean of the noise band's {runs} runs, which the gate "
        "decides on; the installed reference's deltas follow, labelled (installed reference)."
    )


NOISE_TEXT = (
    "A gate measures each delta from the band's mean. A delta inside the band is noise; an "
    "improvement must exceed it, and a regression "
    "inside it is inconclusive. Token and p50 seconds ratios are to the band's mean and "
    "within noise between its runs' min / mean and max / mean."
)

POOLED_GATE_TEXT = (
    "The band carries pooled per-case counts: a flip, and a deciding language read by its "
    "episodes, is outside noise only when Fisher's exact test (two-sided) on the candidate's "
    "episodes against the band's pooled episodes gives p below 0.05 in its direction. The "
    "half-ranges below are information."
)

LEGACY_GATE_TEXT = (
    "The band carries no pooled per-case counts: flips and languages are read against its "
    "spreads and its per-run majority classification, as before pooled counts."
)

RATES_TEXT = (
    "Deciding languages by episode rate (the candidate's episodes against the band's pooled "
    "episodes of the language's cases; Fisher's exact test, two-sided). A language regresses "
    "only when its rate is lower with p below 0.05 and improves only when it is higher with p "
    "below 0.05."
)

DECIDING_TEXT = (
    "Only these languages decide language regressions, the accuracy criterion and the "
    "accuracy floor; the others are shown with their deltas but do not decide. J, its "
    "threshold and the token ratio are unchanged."
)

SLICE_TEXT = (
    "Slice gate: a slice screen, not an acceptance. It decides only on the paired majority "
    "outcomes of the slice cases: a slice case going from pass to fail outside the noise "
    "band rejects, and at least one must go from fail to pass outside it. J, macro "
    "accuracy, tokens and language deltas are over the slice and do not decide. A passing "
    "screen goes on to the full tier run; it never merges anything."
)

SLICE_NOISE_TEXT = (
    "A slice gate reads the band per case only: with pooled counts, a flip the exact test on "
    "the candidate's episodes against the band's pooled episodes does not separate (p at "
    "least 0.05) is within noise and counts neither way; without them, so is a flip in a "
    "language whose band is a whole case or of a case the band classifies unstable."
)

SLICE_UNSTABLE_TEXT = (
    "Unstable in the noise band (a flip there counts neither way; a sentinel there guards nothing)"
)

SLICE_PAIRED_TEXT = (
    "Each slice case, by whether the majority of its repeats verified. Every slice case "
    "decides; flips within the noise band do not count."
)

PAIRED_TEXT = (
    "Each case scored on both sides, by whether the majority of its repeats verified. "
    "Only flips in deciding languages outside noise count toward a paired regression."
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
    labels = (
        (["slice"] if verdict.slice else [])
        + (["smoke"] if verdict.smoke else [])
        + ([] if verdict.track == "objective" else [f"{verdict.track} track"])
    )
    title = f" ({', '.join(labels)})" if labels else ""
    lines = [
        f"## Gate{title}: {verdict.decision.value}",
        "",
        f"Baseline `{verdict.baseline_run_id}`, candidate `{verdict.candidate_run_id}`.",
        "",
        SLICE_TEXT if verdict.slice else TRACK_TEXT[verdict.track],
        "",
    ]
    # The band the deltas were measured from; none without a band or before band deltas.
    band = verdict.noise if verdict.anchored_to_band else None
    if band is not None:
        lines.extend([band_anchor_text(band.n_runs), ""])
        missing = [name for name in verdict.language_deltas if name not in band.languages]
        if missing:
            lines.extend([f"{NOT_IN_BAND_TEXT}: {', '.join(missing)}.", ""])
    if verdict.slice:
        cases = ", ".join(f"`{case}`" for case in verdict.slice_cases) or "none"
        repeats = _count(verdict.slice_repeats)
        lines.extend([f"Slice: {len(verdict.slice_cases)} cases × {repeats} repeats: {cases}.", ""])
        lines.extend(_slice_stability_lines(verdict))
    if verdict.target_language is not None:
        lines.extend([f"Target language: {verdict.target_language}.", ""])
    if verdict.smoke:
        lines.extend([SMOKE_TEXT, ""])
    lines.extend([_identity_line(verdict.identity_changes), ""])
    if verdict.single_case_languages:
        single = ", ".join(verdict.single_case_languages)
        lines.extend([f"Single-case languages: {single}. {SINGLE_CASE_TEXT}", ""])
    if verdict.deciding_languages:
        deciding = ", ".join(verdict.deciding_languages)
        reported = ", ".join(verdict.reported_languages) or "none"
        lines.extend(
            [
                f"Deciding languages (at least {verdict.min_cases} cases): {deciding}; "
                f"reported only: {reported}. {DECIDING_TEXT}",
                "",
            ]
        )
    lines.extend(f"- {reason_text(reason, verdict)}" for reason in verdict.reasons)
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
    suffix = "" if band is None else INSTALLED
    rows = [] if band is None else _band_mean_rows(verdict, candidate)
    rows.extend(
        [
            name + suffix,
            _number(before),
            _number(after),
            _signed(None if before is None or after is None else after - before),
        ]
        for name, before, after in metrics
    )
    deciding_metrics = [
        ("Deciding macro verified accuracy", verdict.deciding_macro_verified_accuracy),
        ("Deciding worst language verified accuracy", verdict.deciding_worst_language),
        ("Deciding objective J (informational)", verdict.objective_j_deciding),
    ]
    rows.extend(
        [
            name + suffix,
            _number(metric.baseline),
            _number(metric.candidate),
            _signed(metric.delta),
        ]
        for name, metric in deciding_metrics
        if metric is not None
    )
    rows.append(["Repeats", str(baseline.repeats), str(candidate.repeats), ""])
    rows.append(["Token ratio (installed reference)", "", _number(verdict.token_ratio), ""])
    rows.append(["p50 seconds ratio (installed reference)", "", _number(verdict.seconds_ratio), ""])
    if verdict.noise is not None and not verdict.slice:
        rows.append(["Token ratio (band mean)", "", _number(verdict.token_ratio_to_band), ""])
        rows.append(
            ["p50 seconds ratio (band mean)", "", _number(verdict.seconds_ratio_to_band), ""]
        )
    lines.extend(_table(["Metric", "Baseline", "Candidate", "Delta"], rows))
    lines.append("")
    language_rows = []
    for language, delta in verdict.language_deltas.items():
        before = baseline.languages[language]
        after = candidate.languages.get(language)
        capped_after = None if after is None else after.capped_call_episodes
        operational_after = None if after is None else after.operational_episodes
        target_after = None if after is None else after.target_exception_episodes
        accuracy = [
            _number(before.verified_accuracy),
            _number(None if after is None else after.verified_accuracy),
            _signed(delta),
            _regressed(verdict, language, baseline),
        ]
        if band is not None:
            spread = band.languages.get(language)
            accuracy = [
                "not in band" if spread is None else _number(spread.mean),
                accuracy[1],
                _band_delta(verdict, language),
                accuracy[3],
                accuracy[0],
                accuracy[2],
            ]
        language_rows.append(
            [
                language,
                *accuracy,
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
    accuracy_header = ["Baseline verified", "Candidate verified", "Delta", "Regressed"]
    if band is not None:
        accuracy_header = [
            "Band mean verified",
            "Candidate verified",
            "Delta (band mean)",
            "Regressed",
            "Installed reference verified",
            "Delta (installed reference)",
        ]
    lines.extend(
        _table(
            [
                "Language",
                *accuracy_header,
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
    lines.extend(_paired_lines(verdict, baseline))
    return "\n".join(lines) + "\n"


def _slice_stability_lines(verdict: GateVerdict) -> list[str]:
    """Which slice cases the band classifies unstable, when a band was read and matched."""
    noise = verdict.noise
    if noise is None or GateReason.NOISE_MISMATCH in verdict.reasons:
        return []
    if noise.cases is None:
        return [
            "Unstable in the noise band: unknown (the band recorded no per-case stability).",
            "",
        ]
    named = ", ".join(f"`{case}`" for case in verdict.slice_unstable_cases) or "none"
    return [f"{SLICE_UNSTABLE_TEXT}: {named}.", ""]


def _reported_only(card: Scorecard, language: str) -> str:
    cases = card.languages[language].cases
    return "reported only (single case)" if cases == 1 else f"reported only ({cases} cases)"


def _regressed(verdict: GateVerdict, language: str, baseline: Scorecard) -> str:
    if verdict.slice:
        return "not decided (slice)"
    if language in verdict.reported_languages:
        return _reported_only(baseline, language)
    if language not in verdict.regressed_languages:
        return "no"
    return "yes (single case)" if language in verdict.single_case_languages else "yes"


def _band_mean_rows(verdict: GateVerdict, candidate: Scorecard) -> list[list[str]]:
    """The metric rows measured from the band's mean: mean, candidate, delta."""
    headline = [
        ("Objective J", candidate.objective_j, verdict.delta_j_to_band),
        (
            "Macro verified accuracy",
            candidate.macro_verified_accuracy,
            verdict.delta_macro_verified_accuracy_to_band,
        ),
        (
            "Worst language verified accuracy",
            candidate.worst_language_verified_accuracy,
            verdict.delta_worst_language_verified_accuracy_to_band,
        ),
    ]
    rows = [
        [f"{name} (band mean)", _number(after - delta), _number(after), _signed(delta)]
        for name, after, delta in headline
        if delta is not None
    ]
    deciding = [
        ("Deciding macro verified accuracy", verdict.deciding_macro_verified_accuracy_to_band),
        ("Deciding worst language verified accuracy", verdict.deciding_worst_language_to_band),
    ]
    rows.extend(
        [
            f"{name} (band mean)",
            _number(metric.baseline),
            _number(metric.candidate),
            _signed(metric.delta),
        ]
        for name, metric in deciding
        if metric is not None
    )
    return rows


def _band_delta(verdict: GateVerdict, language: str) -> str:
    """A language's delta from the band's mean, or its installed-reference delta (labelled)
    when the band lacks it."""
    delta = _signed(verdict.language_deltas_to_band.get(language))
    if verdict.noise is not None and language not in verdict.noise.languages:
        return delta + INSTALLED
    return delta


def _episodes(rate: EpisodeRate) -> str:
    """``candidate v/n vs reference v/n episodes, p <p>``."""
    return (
        f"{rate.candidate_verified}/{rate.candidate_episodes} vs "
        f"{rate.reference_verified}/{rate.reference_episodes} episodes, p {rate.p_value:.3f}"
    )


def _flip(case: PairedCase) -> str:
    notes = [case.language]
    if not case.deciding:
        notes.append("reported only")
    if case.rate is not None:
        notes.append(_episodes(case.rate))
    if case.within_noise:
        reason = None if case.noise_reason is None else FLIP_NOISE_TEXT[case.noise_reason]
        notes.append(f"within noise: {reason}" if reason else "within noise")
    return f"`{case.case_id}` ({', '.join(notes)})"


def _case_ids(cases: Sequence[NoiseCase], stability: CaseStability) -> str:
    return ", ".join(f"`{case.case_id}`" for case in cases if case.stability == stability)


def _stability_counts(cases: Sequence[NoiseCase]) -> str:
    counts = Counter(case.stability for case in cases)
    return (
        f"{counts['stable_pass']} stable pass, {counts['stable_fail']} stable fail, "
        f"{counts['unstable']} unstable"
    )


def _band_stability_lines(noise: NoiseBand | None) -> list[str]:
    """The paired view's lines for the band's per-case classification, when a band was read."""
    if noise is None:
        return []
    if noise.cases is None:
        return ["- Noise band per-case stability: unknown (the band recorded none)."]
    rule = "by pooled episodes" if noise.pooled else "by per-run majority, no pooled counts"
    lines = [f"- Noise band per-case stability ({rule}): {_stability_counts(noise.cases)}."]
    for label, stability in (("Unstable", "unstable"), ("Stable fail", "stable_fail")):
        named = _case_ids(noise.cases, stability)
        if named:
            lines.append(f"- {label} in the band: {named}")
    return lines


def _paired_lines(verdict: GateVerdict, baseline: Scorecard) -> list[str]:
    """The paired per-case table, the flipped cases and what a paired regression counts."""
    paired = verdict.paired
    if paired is None:
        if verdict.deciding_languages and verdict.decision is not GateDecision.INCOMPARABLE:
            return ["", "Paired per-case outcomes: unknown (no trajectories were read)."]
        return []

    def decides(language: str) -> str:
        if language in verdict.reported_languages and language in baseline.languages:
            return _reported_only(baseline, language)
        return "yes"

    rows = [
        [
            language,
            str(counts.pass_to_fail),
            str(counts.fail_to_pass),
            str(counts.stable_pass),
            str(counts.stable_fail),
            decides(language),
        ]
        for language, counts in paired.languages.items()
    ]
    rows.append(
        [
            "All cases",
            str(paired.pass_to_fail),
            str(paired.fail_to_pass),
            str(paired.stable_pass),
            str(paired.stable_fail),
            "",
        ]
    )
    text = SLICE_PAIRED_TEXT if verdict.slice else PAIRED_TEXT
    lines = ["", f"Paired per-case outcomes. {text}", ""]
    lines.extend(
        _table(
            ["Language", "Pass to fail", "Fail to pass", "Stable pass", "Stable fail", "Decides"],
            rows,
        )
    )
    lines.append("")
    for label, cases in (
        ("Pass to fail", paired.pass_to_fail_cases),
        ("Fail to pass", paired.fail_to_pass_cases),
    ):
        flipped = ", ".join(_flip(case) for case in cases) or "none"
        lines.append(f"- {label}: {flipped}")
    lines.append(
        f"- Deciding flips outside noise: {paired.deciding_pass_to_fail} pass to fail, "
        f"{paired.deciding_fail_to_pass} fail to pass"
    )
    lines.extend(_band_stability_lines(verdict.noise))
    for label, cases in (
        ("Baseline only (not paired)", paired.baseline_only),
        ("Candidate only (not paired)", paired.candidate_only),
    ):
        if cases:
            lines.append(f"- {label}: " + ", ".join(f"`{case}`" for case in cases))
    return lines


def _difference_band(spread: NoiseSpread | None) -> str:
    return "unknown" if spread is None else f"±{spread.band:.3f}"


def _mean_ratio_band(spread: NoiseSpread | None, suffix: str = "") -> str:
    """The band's runs as ratios to its mean: min / mean to max / mean."""
    if spread is None or spread.mean <= 0:
        return "unknown"
    low, high = min(spread.values) / spread.mean, max(spread.values) / spread.mean
    return f"{low:.3f}{suffix} to {high:.3f}{suffix}"


def _rate(verified: int, episodes: int) -> str:
    return f"{verified}/{episodes} ({verified / episodes:.3f})"


def _rate_lines(verdict: GateVerdict) -> list[str]:
    """Each deciding language's episodes against the band's pooled episodes, and the test."""
    if not verdict.language_rates:
        return []
    rows = [
        [
            language,
            _rate(rate.reference_verified, rate.reference_episodes),
            _rate(rate.candidate_verified, rate.candidate_episodes),
            f"{rate.p_value:.3f}",
            "yes" if language in verdict.languages_within_noise else "no",
        ]
        for language, rate in verdict.language_rates.items()
    ]
    lines = [RATES_TEXT, ""]
    lines.extend(
        _table(["Language", "Reference episodes", "Candidate episodes", "p", "Within noise"], rows)
    )
    return [*lines, ""]


def _noise_lines(verdict: GateVerdict) -> list[str]:
    """The band a gate read, each metric's delta against it, and what lies within it."""
    noise = verdict.noise
    if noise is None:
        return []
    runs = ", ".join(f"`{run}`" for run in noise.runs)
    pooled = POOLED_GATE_TEXT if noise.pooled else LEGACY_GATE_TEXT
    if verdict.slice:
        return [f"Noise band from {noise.n_runs} runs: {runs}. {SLICE_NOISE_TEXT}", "", pooled, ""]
    lines = [f"Noise band from {noise.n_runs} runs: {runs}. {NOISE_TEXT}", "", pooled, ""]
    if verdict.decision is GateDecision.INCOMPARABLE:
        # Nothing was compared, so no delta was read against the band.
        return lines

    def within(flag: bool) -> str:
        return "yes" if flag else "no"

    metrics = set(verdict.within_noise)
    # Deltas from the band's mean; a record written before them shows the installed
    # reference's, as it was decided.
    anchored = verdict.anchored_to_band
    delta_j = verdict.delta_j_to_band if anchored else verdict.delta_j
    accuracy = (
        verdict.delta_macro_verified_accuracy_to_band
        if anchored
        else verdict.delta_macro_verified_accuracy
    )
    rows = [
        [
            "Objective J",
            _signed(delta_j),
            _difference_band(noise.objective_j),
            within("objective_j" in metrics),
        ],
        [
            "Macro verified accuracy",
            _signed(accuracy),
            _difference_band(noise.macro_verified_accuracy),
            within("macro_verified_accuracy" in metrics),
        ],
        [
            "Token ratio to band mean",
            _number(verdict.token_ratio_to_band),
            _mean_ratio_band(noise.macro_effective_tokens),
            within("macro_effective_tokens" in metrics),
        ],
        [
            "p50 seconds ratio to band mean",
            _number(verdict.seconds_ratio_to_band),
            _mean_ratio_band(noise.macro_p50_seconds),
            within("macro_p50_seconds" in metrics),
        ],
    ]
    deciding = (
        verdict.deciding_macro_verified_accuracy_to_band or verdict.deciding_macro_verified_accuracy
    )
    if verdict.deciding_languages:
        band = deciding_accuracy_spread(noise, verdict.deciding_languages)
        deciding_delta = None if deciding is None else deciding.delta
        rows.append(
            [
                "Deciding macro verified accuracy",
                _signed(deciding_delta),
                _difference_band(band),
                within(inside_band(deciding_delta, band)),
            ]
        )
    rows.extend(
        [
            f"{language} verified accuracy",
            _band_delta(verdict, language) if anchored else _signed(delta),
            _difference_band(noise.languages.get(language)),
            within(language in verdict.languages_within_noise)
            + (" (episode rate)" if language in verdict.language_rates else ""),
        ]
        for language, delta in verdict.language_deltas.items()
    )
    lines.extend(_table(["Metric", "Delta", "Noise band", "Within noise"], rows))
    lines.append("")
    lines.extend(_rate_lines(verdict))
    named = ", ".join(verdict.within_noise) or "none"
    languages = ", ".join(verdict.languages_within_noise) or "none"
    lines.extend([f"Within noise: {named}; languages: {languages}.", ""])
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
                _mean_ratio_band(spread, "x") if ratio else _difference_band(spread),
            ]
        )
    lines.extend(_table(["Metric", *runs, "Mean", "Half-range", "Stdev", "Gate band"], rows))
    lines.extend(["", NOISE_TEXT, "", *_noise_case_lines(band)])
    return "\n".join(lines) + "\n"


def _noise_case_lines(band: NoiseBand) -> list[str]:
    """The band's per-case classification: counts, the unstable and failing cases, and
    with pooled counts each case's episodes and majority-pass probability."""
    if band.cases is None:
        if not band.cases_unknown_runs:
            return [
                "Per-case stability: not recorded (a band written before per-case stability); "
                "the band carries no pooled counts."
            ]
        runs = ", ".join(f"`{run}`" for run in band.cases_unknown_runs)
        return [
            f"Per-case stability: unknown; no trajectories reproducing run {runs}; "
            "the band carries no pooled counts."
        ]
    text = NOISE_CASES_TEXT if band.pooled else LEGACY_CASES_TEXT
    lines = [f"Per-case stability: {_stability_counts(band.cases)}. {text}", ""]
    unstable = "Unstable" if band.pooled else "Unstable (a flip counts neither way)"
    for label, stability in ((unstable, "unstable"), ("Stable fail", "stable_fail")):
        lines.append(f"- {label}: {_case_ids(band.cases, stability) or 'none'}")
    if not band.pooled:
        return lines
    rows = [
        [
            f"`{case.case_id}`",
            case.language,
            *(str(count) for count in case.verified_episodes),
            _rate(case.verified or 0, case.episodes or 1),
            _number(case.majority_pass_probability),
            case.stability.replace("_", " "),
        ]
        for case in band.cases
    ]
    runs = [f"`{run}` verified" for run in band.runs]
    header = ["Case", "Language", *runs, "Pooled verified", "Majority-pass probability"]
    lines.extend(["", *_table([*header, "Stability"], rows)])
    return lines


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
