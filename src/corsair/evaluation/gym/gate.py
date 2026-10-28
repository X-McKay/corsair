"""Decide whether a candidate scorecard beats its baseline; exit codes 0, 1 and 2.

INCOMPARABLE is never a regression verdict: different datasets or budgets, a sliced run,
too few repeats or unknown token usage mean the two scorecards answer different questions.
Identity changes, operational stops and target-side exception episodes are reported beside
the decision and never change it: a different prompt, skill, image or model is what a
candidate is, an operational stop keeps its ERROR score, and a target-side exception
already scores 0 on its scorecard.

A gate decides on one track; every track first requires that no language's majority
verified accuracy fell, and every verdict reports ΔJ, the token ratio and the p50 seconds
ratio:

- ``objective``: J gained at least ``MIN_OBJECTIVE_GAIN`` and macro effective tokens
  stayed within ``MAX_TOKEN_RATIO`` of the baseline.
- ``accuracy``: macro verified accuracy rose by at least ``min_accuracy_gain`` (one
  case's majority flipping in the language with the most cases), or the named target
  language rose by at least one flip of its own, and tokens stayed within
  ``MAX_TOKEN_RATIO``. J is reported, never decided on: with one case in a language one
  ERROR episode moves J by more than its margin.
- ``efficiency``: macro verified accuracy is at least the baseline's, and macro
  effective tokens or macro p50 seconds fell to ``MAX_EFFICIENT_RATIO`` or below. Seconds
  count only when both runs record the same concurrency and no operational episode;
  otherwise ``latency_not_comparable`` is reported and only tokens can qualify.

A smoke gate (``smoke=True``, for a tier where every language already verifies, so the
track's improvement criterion is noise) still reports that criterion's reason but decides
only on language regressions, the token ceiling, the accuracy floor and the INCOMPARABLE
conditions; its verdict says ``smoke`` so its ACCEPTED is never read as an acceptance.

A gate given a noise band (``noise``, from ``corsair gym noise``: two or more runs of one
configuration) reads each metric's delta against it. A difference lies within noise when
its magnitude is at most the band (max - min across those runs). Token and p50 seconds
ratios are then taken against the mean of the band's runs (``token_ratio_to_band``,
``seconds_ratio_to_band``; the ratios to the installed baseline are still reported): the
token ceiling and the efficiency ratios read them, and a ratio lies within noise between
the band's min / mean and max / mean. An improvement criterion is then met only beyond the
band. When every deciding reason is a regression (``language_regressed``,
``objective_below_threshold``, ``accuracy_below_baseline``, ``tokens_above_ceiling``) whose
metric lies within noise, the verdict is INCONCLUSIVE (with ``within_noise``) instead of
REJECTED, and a confirmation run decides; one regression outside the band, or an unmet
improvement criterion of the accuracy or efficiency track, still rejects. A band scored on
another dataset, budgets or repeat count makes the gate INCOMPARABLE (``noise_mismatch``).
Without a band every decision is as above.

Deciding languages (``min_cases``): with ``min_cases`` above 1 only baseline languages with
at least that many cases decide ``language_regressed``, ``accuracy_not_improved`` and
``accuracy_below_baseline`` (macro verified accuracy and the minimum gain are then taken
over the deciding languages, against the band's per-run mean of their accuracies); the
others are reported only. J and its threshold are unchanged; ``objective_j_deciding``
recomputes J over the deciding languages for information. With ``min_cases`` 1 every
language decides, as before.

Paired outcomes: given both runs' trajectories, every case scored on both sides is
compared by its majority outcome (``pass_to_fail``, ``fail_to_pass``, ``stable_pass``,
``stable_fail``). On the accuracy or objective track a gate that would otherwise accept
rejects with ``paired_regression`` when, among the deciding languages, more cases went
from pass to fail than from fail to pass.

With a band carrying pooled per-case counts (``NoiseBand.pooled``), a flip is outside
noise only when Fisher's exact test, two-sided, on the candidate's episodes of the case
(verified or not) against the band's pooled episodes of it gives p below
``SIGNIFICANCE_LEVEL`` and the candidate's rate moved in the flip's direction; otherwise it
is noise (``episode_rate``) and never counts. A case the band did not record falls back to
its language band. Deciding languages (given the candidate's trajectories) use the same
test on the candidate's episodes pooled over the language's cases against the band's
pooled episodes of its cases (``language_rates``): a language whose majority accuracy fell
is a regression outside noise only when its rate is lower with p below the level, and the
accuracy track's language criterion holds only when the rate is higher with p below it.

With a band without pooled counts (written before them) the earlier rules hold: a flip in
a language whose band is a whole case (±1.0) is noise (``language_band``), and so is a flip
of a case the band classifies ``unstable`` (``unstable_case``); deciding languages are read
against their spreads.

Slice screens (``slice=True``): a sliced candidate (``gym run --case``) is gated against
an unsliced baseline, or one sliced to exactly the same cases, on the candidate's cases
only, by their paired majority outcomes alone. It is REJECTED with ``slice_regressed``
when a slice case went from pass to fail outside the noise band and with
``slice_not_improved`` when none went from fail to pass outside it; otherwise ACCEPTED,
which is a screen for the full tier run and never an acceptance. Different datasets or
budgets, too few repeats on either side, a band of another dataset, budgets or baseline
repeat count, and a slice the baseline did not score (``slice_mismatch``) are INCOMPARABLE.
J, macro accuracy, tokens and language deltas are recomputed over the slice and reported;
they never decide, and neither does unknown token usage. The verdict names the slice
cases the band classifies ``unstable`` (``slice_unstable_cases``), so a coin-flip sentinel
is visible; that is reported, never a refusal.
"""

from collections import Counter
from collections.abc import Collection, Sequence
from statistics import mean

from corsair.contracts import (
    DecidingMetric,
    EpisodeRate,
    FlipNoise,
    GateDecision,
    GateReason,
    GateTrack,
    GateVerdict,
    NoiseBand,
    NoiseMetric,
    NoiseSpread,
    PairedCase,
    PairedCounts,
    PairedOutcomes,
    RunIdentity,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.exact import fisher_exact
from corsair.evaluation.gym.scoring import build_scorecard, case_outcomes, objective_terms

MIN_REPEATS = 3
MIN_OBJECTIVE_GAIN = 0.01
MAX_TOKEN_RATIO = 1.10
# The efficiency track's ceiling on the token or p50 seconds ratio: at least 10 % lower.
MAX_EFFICIENT_RATIO = 0.90
# Floating-point slack so a gain or ratio exactly at its threshold is decided as written.
_EPSILON = 1e-9
# Each track's improvement criterion: reported by a smoke gate, never deciding it.
_IMPROVEMENT = frozenset(
    {
        GateReason.OBJECTIVE_BELOW_THRESHOLD,
        GateReason.ACCURACY_NOT_IMPROVED,
        GateReason.EFFICIENCY_NOT_IMPROVED,
    }
)
# Reasons that explain a verdict without ever causing a rejection.
_INFORMATIONAL = frozenset(
    {
        GateReason.OPERATIONALLY_CONFOUNDED,
        GateReason.LATENCY_NOT_COMPARABLE,
        GateReason.WITHIN_NOISE,
    }
)
# The regressions a noise band can make INCONCLUSIVE, by the headline metric each is read
# against; ``language_regressed`` is read per regressed language.
_REGRESSION_METRIC: dict[GateReason, NoiseMetric] = {
    GateReason.OBJECTIVE_BELOW_THRESHOLD: "objective_j",
    GateReason.ACCURACY_BELOW_BASELINE: "macro_verified_accuracy",
    GateReason.TOKENS_ABOVE_CEILING: "macro_effective_tokens",
}


def incomparable_reasons(
    baseline: Scorecard, candidate: Scorecard, min_repeats: int
) -> list[GateReason]:
    reasons = []
    if baseline.dataset_digest != candidate.dataset_digest:
        reasons.append(GateReason.DATASET_MISMATCH)
    if baseline.budgets_digest != candidate.budgets_digest:
        reasons.append(GateReason.BUDGETS_MISMATCH)
    if baseline.sliced or candidate.sliced:
        reasons.append(GateReason.SLICED)
    if min(baseline.repeats, candidate.repeats) < min_repeats:
        reasons.append(GateReason.REPEATS_BELOW_MINIMUM)
    if baseline.macro_effective_tokens is None or candidate.macro_effective_tokens is None:
        reasons.append(GateReason.TOKENS_UNKNOWN)
    return reasons


def noise_mismatch(noise: NoiseBand, baseline: Scorecard, candidate: Scorecard) -> bool:
    """Whether the band scored another dataset, budgets or repeat count than either side."""
    return any(
        noise.dataset_digest != card.dataset_digest
        or noise.budgets_digest != card.budgets_digest
        or noise.repeats != card.repeats
        for card in (baseline, candidate)
    )


def spread(values: Sequence[float], *, ratio: bool = False) -> NoiseSpread:
    """Mean, half-range and sample deviation; ``max_ratio`` for a positive scale metric."""
    values = list(values)
    average = sum(values) / len(values)
    stdev = (sum((value - average) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    positive = ratio and min(values) > 0
    return NoiseSpread(
        values=values,
        mean=average,
        half_range=(max(values) - min(values)) / 2,
        stdev=stdev,
        max_ratio=max(values) / min(values) if positive else None,
    )


def single_case_languages(card: Scorecard) -> list[str]:
    """Languages with one case: one episode flips their whole verified accuracy."""
    return sorted(language for language, summary in card.languages.items() if summary.cases == 1)


def deciding_languages(card: Scorecard, min_cases: int) -> list[str]:
    """Baseline languages with at least ``min_cases`` cases: the languages that decide."""
    return sorted(
        language for language, summary in card.languages.items() if summary.cases >= min_cases
    )


def admit_min_cases(baseline: Scorecard, min_cases: int, target_language: str | None) -> None:
    """Some baseline language must decide, and a target language must be one of them."""
    if min_cases < 1:
        raise ValueError("min_cases is at least 1")
    deciding = deciding_languages(baseline, min_cases)
    if not deciding:
        raise ValueError(f"no baseline language has {min_cases} or more cases")
    if target_language is not None and target_language not in deciding:
        raise ValueError(
            f"{target_language} has fewer than {min_cases} cases and does not decide; "
            "it cannot be the target language"
        )


def language_deltas(baseline: Scorecard, candidate: Scorecard) -> dict[str, float | None]:
    """Candidate minus baseline majority verified accuracy, per baseline language."""
    deltas: dict[str, float | None] = {}
    for language, before in sorted(baseline.languages.items()):
        after = candidate.languages.get(language)
        if after is None or before.verified_accuracy is None or after.verified_accuracy is None:
            deltas[language] = None
        else:
            deltas[language] = after.verified_accuracy - before.verified_accuracy
    return deltas


def identity_changes(baseline: Scorecard, candidate: Scorecard) -> dict[str, bool | None]:
    """Per ``RunIdentity`` component, whether its recorded values differ; unknown if absent."""
    changes: dict[str, bool | None] = {}
    for component in RunIdentity.model_fields:
        before = baseline.run_identity.get(component)
        after = candidate.run_identity.get(component)
        changes[component] = None if not before or not after else before != after
    return changes


def operationally_confounded(
    baseline: Scorecard, candidate: Scorecard, regressed: Sequence[str]
) -> list[str]:
    """Regressed languages that would not regress had their operational episodes verified."""
    confounded = []
    for language in regressed:
        before, after = baseline.languages.get(language), candidate.languages.get(language)
        if before is None or after is None or before.verified_accuracy is None:
            continue
        ceiling = after.verified_accuracy_without_operational_failures
        if (
            after.operational_episodes
            and ceiling is not None
            and ceiling >= before.verified_accuracy - _EPSILON
        ):
            confounded.append(language)
    return confounded


def token_ratio(baseline: Scorecard, candidate: Scorecard) -> float | None:
    before, after = baseline.macro_effective_tokens, candidate.macro_effective_tokens
    if before is None or after is None or before <= 0:
        return None
    return after / before


def seconds_ratio(baseline: Scorecard, candidate: Scorecard) -> float | None:
    before, after = baseline.macro_p50_seconds, candidate.macro_p50_seconds
    if before is None or after is None or before <= 0:
        return None
    return after / before


def band_ratio(value: float | None, spread: NoiseSpread | None) -> float | None:
    """``value`` over the mean of the band's runs; unknown when either is."""
    if value is None or spread is None or spread.mean <= 0:
        return None
    return value / spread.mean


def latency_comparable(baseline: Scorecard, candidate: Scorecard) -> bool:
    """Seconds compare only at one recorded concurrency and with no operational episode."""
    return (
        baseline.run.concurrency is not None
        and baseline.run.concurrency == candidate.run.concurrency
        and baseline.operational_episodes == 0
        and candidate.operational_episodes == 0
    )


def language_step(card: Scorecard, language: str) -> float | None:
    """How far one case's majority flip moves ``language``'s verified accuracy: 1/cases."""
    summary = card.languages.get(language)
    return None if summary is None or summary.cases == 0 else 1 / summary.cases


def min_accuracy_gain(card: Scorecard, languages: Collection[str] | None = None) -> float:
    """The smallest macro verified accuracy change one case's majority flip can make.

    Macro accuracy is the mean over languages of each language's fraction of cases whose
    majority of repeats verified, so one flip in language L moves it by
    1 / (languages x cases of L); the smallest such step is in the language with the most
    cases: 1 / (languages x max cases). With six languages and ten python cases that is
    1/60. Any rise with no language regressed is at least this step. ``languages``
    restricts the macro to those languages (the deciding ones); default every language.
    """
    names = list(card.languages) if languages is None else list(languages)
    cases = [card.languages[name].cases for name in names if card.languages[name].cases]
    if not cases:
        raise ValueError("a scorecard without cases has no accuracy step")
    return 1 / (len(names) * max(cases))


def deciding_metrics(
    baseline: Scorecard, candidate: Scorecard, languages: Collection[str]
) -> tuple[DecidingMetric, DecidingMetric, DecidingMetric] | None:
    """Macro verified accuracy, worst-language verified accuracy and J over ``languages``.

    Unknown when the candidate lacks one of them.
    """
    if any(language not in candidate.languages for language in languages):
        return None
    before = objective_terms({name: baseline.languages[name] for name in languages})
    after = objective_terms({name: candidate.languages[name] for name in languages})
    pairs = [
        (before.macro_verified_accuracy, after.macro_verified_accuracy),
        (before.worst_language_verified_accuracy, after.worst_language_verified_accuracy),
        (before.objective_j, after.objective_j),
    ]
    accuracy, worst, objective = (
        DecidingMetric(baseline=old, candidate=new, delta=new - old) for old, new in pairs
    )
    return accuracy, worst, objective


def deciding_accuracy_spread(noise: NoiseBand, languages: Collection[str]) -> NoiseSpread | None:
    """The band's spread of macro verified accuracy over ``languages`` only: per run, the
    mean of those languages' verified accuracies. Unknown when the band lacks one."""
    spreads = [noise.languages.get(language) for language in languages]
    known = [item for item in spreads if item is not None]
    if not known or len(known) != len(spreads):
        return None
    return spread([mean(item.values[run] for item in known) for run in range(noise.n_runs)])


def _whole_case(band: NoiseSpread | None) -> bool:
    """A language whose runs differed by its whole range: one case flipping between 1 and 0."""
    return band is not None and band.band >= 1.0 - _EPSILON


def unstable_cases(noise: NoiseBand | None) -> set[str]:
    """The cases ``noise`` classifies ``unstable``; none without a band or its cases."""
    if noise is None or noise.cases is None:
        return set()
    return {case.case_id for case in noise.cases if case.stability == "unstable"}


def episode_rate(
    reference_verified: int,
    reference_episodes: int,
    candidate_verified: int,
    candidate_episodes: int,
) -> EpisodeRate:
    """The candidate's episodes against the reference's, with Fisher's exact p-value."""
    return EpisodeRate(
        reference_verified=reference_verified,
        reference_episodes=reference_episodes,
        candidate_verified=candidate_verified,
        candidate_episodes=candidate_episodes,
        p_value=fisher_exact(
            candidate_verified, candidate_episodes, reference_verified, reference_episodes
        ),
    )


def _pooled_cases(noise: NoiseBand | None) -> dict[str, tuple[int, int]]:
    """Per case the band pooled: (verified, episodes); none without pooled counts."""
    if noise is None or not noise.pooled:
        return {}
    return {
        case.case_id: (case.verified or 0, case.episodes or 0)
        for case in noise.cases or []
        if case.episodes
    }


def _episode_counts(trajectories: Sequence[Trajectory]) -> dict[str, tuple[int, int]]:
    """Per case id: (verified episodes, episodes)."""
    verified = Counter(item.case_id for item in trajectories if item.verified)
    episodes = Counter(item.case_id for item in trajectories)
    return {case: (verified[case], count) for case, count in episodes.items()}


def language_rates(
    noise: NoiseBand | None, candidate: Sequence[Trajectory], languages: Collection[str]
) -> dict[str, EpisodeRate]:
    """Per language in ``languages``: the candidate's episodes of its cases against the
    band's pooled episodes of its cases. Empty without pooled counts; a language either
    side has no episodes of is left out (it is read against its spread)."""
    if noise is None or not noise.pooled:
        return {}
    rates = {}
    for language in sorted(languages):
        reference = [case for case in noise.cases or [] if case.language == language]
        rows = [item for item in candidate if item.language == language]
        if not reference or not rows:
            continue
        rates[language] = episode_rate(
            sum(case.verified or 0 for case in reference),
            sum(case.episodes or 0 for case in reference),
            sum(item.verified for item in rows),
            len(rows),
        )
    return rates


def _flip_noise(
    noise: NoiseBand | None,
    case: str,
    language: str,
    unstable: Collection[str],
    rate: EpisodeRate | None,
    direction: int,
) -> FlipNoise | None:
    """Why a flip in ``direction`` (+1 fail to pass, -1 pass to fail) is within ``noise``;
    ``None`` when it is a real flip. With the case's pooled counts (``rate``) only the
    exact test decides; otherwise the case is a coin-flip, or its language's band is a
    whole case."""
    if noise is None:
        return None
    if rate is not None:
        return None if rate.separates(direction) else "episode_rate"
    if case in unstable:
        return "unstable_case"
    return "language_band" if _whole_case(noise.languages.get(language)) else None


_PAIRING = {
    (True, True): "stable_pass",
    (True, False): "pass_to_fail",
    (False, True): "fail_to_pass",
    (False, False): "stable_fail",
}
_FLIP_DIRECTION = {"pass_to_fail": -1, "fail_to_pass": 1}


def paired_outcomes(
    baseline: Sequence[Trajectory],
    candidate: Sequence[Trajectory],
    *,
    deciding: Collection[str],
    noise: NoiseBand | None = None,
) -> PairedOutcomes:
    """Every case scored on both sides by its baseline and candidate majority outcome.

    A flip in a language outside ``deciding`` is listed but never counted in
    ``deciding_pass_to_fail``/``deciding_fail_to_pass``; with ``noise`` neither is a flip
    within noise (module docstring): by Fisher's exact test on the case's episodes when the
    band pooled them, else by its language band or ``unstable`` classification.
    """
    before, after = case_outcomes(baseline), case_outcomes(candidate)
    unstable = unstable_cases(noise)
    pooled = _pooled_cases(noise)
    episodes = _episode_counts(candidate)
    totals: Counter[str] = Counter()
    languages: dict[str, Counter[str]] = {}
    flips: dict[str, list[PairedCase]] = {"pass_to_fail": [], "fail_to_pass": []}
    decided: Counter[str] = Counter()
    for case in sorted(before.keys() & after.keys()):
        language, was = before[case]
        outcome = _PAIRING[(was, after[case][1])]
        totals[outcome] += 1
        languages.setdefault(language, Counter())[outcome] += 1
        if outcome not in flips:
            continue
        rate = None
        if case in pooled:
            rate = episode_rate(*pooled[case], *episodes[case])
        reason = _flip_noise(noise, case, language, unstable, rate, _FLIP_DIRECTION[outcome])
        flip = PairedCase(
            case_id=case,
            language=language,
            deciding=language in deciding,
            within_noise=reason is not None,
            noise_reason=reason,
            **({} if rate is None else rate.model_dump()),
        )
        flips[outcome].append(flip)
        if flip.deciding and not flip.within_noise:
            decided[outcome] += 1
    return PairedOutcomes(
        pass_to_fail=totals["pass_to_fail"],
        fail_to_pass=totals["fail_to_pass"],
        stable_pass=totals["stable_pass"],
        stable_fail=totals["stable_fail"],
        languages={
            language: PairedCounts(
                pass_to_fail=counts["pass_to_fail"],
                fail_to_pass=counts["fail_to_pass"],
                stable_pass=counts["stable_pass"],
                stable_fail=counts["stable_fail"],
            )
            for language, counts in sorted(languages.items())
        },
        pass_to_fail_cases=flips["pass_to_fail"],
        fail_to_pass_cases=flips["fail_to_pass"],
        deciding_pass_to_fail=decided["pass_to_fail"],
        deciding_fail_to_pass=decided["fail_to_pass"],
        baseline_only=sorted(before.keys() - after.keys()),
        candidate_only=sorted(after.keys() - before.keys()),
    )


def trajectories_reproduce(card: Scorecard, trajectories: Sequence[Trajectory]) -> bool:
    """Whether ``trajectories`` give ``card``'s languages, per-language case counts and
    majority verified accuracy: the per-case record belongs to that scorecard."""
    outcomes = case_outcomes(trajectories)
    if {language for language, _ in outcomes.values()} != set(card.languages):
        return False
    for language, summary in card.languages.items():
        flags = [verified for name, verified in outcomes.values() if name == language]
        if len(flags) != summary.cases:
            return False
        accuracy = summary.verified_accuracy
        if accuracy is not None and abs(sum(flags) / len(flags) - accuracy) > _EPSILON:
            return False
    return True


def _at_least(gain: float | None, step: float | None) -> bool:
    return gain is not None and step is not None and gain >= step - _EPSILON


def _within(ratio: float | None, ceiling: float) -> bool:
    return ratio is not None and ratio <= ceiling + _EPSILON


def inside_band(delta: float | None, spread: NoiseSpread | None) -> bool:
    """A difference no larger than the largest the band's runs showed."""
    return delta is not None and spread is not None and abs(delta) <= spread.band + _EPSILON


def _inside_ratio(ratio: float | None, spread: NoiseSpread | None) -> bool:
    """A ratio to the band's mean between its runs' min / mean and max / mean."""
    if ratio is None or spread is None or spread.mean <= 0:
        return False
    low, high = min(spread.values) / spread.mean, max(spread.values) / spread.mean
    return low - _EPSILON <= ratio <= high + _EPSILON


def _beyond(delta: float | None, noise: NoiseBand | None, spread: NoiseSpread | None) -> bool:
    """A gain counts beyond the band; without a band every gain does."""
    if noise is None:
        return True
    return delta is not None and spread is not None and delta > spread.band + _EPSILON


def _saving_beyond(
    ratio: float | None, noise: NoiseBand | None, spread: NoiseSpread | None
) -> bool:
    """A saving (a ratio to the band's mean) counts below the band's min / mean; without a
    band every one does."""
    if noise is None:
        return True
    if ratio is None or spread is None or spread.mean <= 0:
        return False
    return ratio < min(spread.values) / spread.mean - _EPSILON


def within_noise(
    noise: NoiseBand,
    *,
    deltas: dict[str, float | None],
    delta_j: float,
    accuracy: float,
    tokens: float | None,
    seconds: float | None,
) -> tuple[list[NoiseMetric], list[str]]:
    """The headline metrics and the languages whose delta lies inside the band.

    ``tokens`` and ``seconds`` are ratios to the band's mean."""
    inside: dict[NoiseMetric, bool] = {
        "objective_j": inside_band(delta_j, noise.objective_j),
        "macro_verified_accuracy": inside_band(accuracy, noise.macro_verified_accuracy),
        "macro_effective_tokens": _inside_ratio(tokens, noise.macro_effective_tokens),
        "macro_p50_seconds": _inside_ratio(seconds, noise.macro_p50_seconds),
    }
    languages = [
        language
        for language, delta in deltas.items()
        if inside_band(delta, noise.languages.get(language))
    ]
    return [metric for metric, flag in inside.items() if flag], languages


def _regression_within_noise(
    reason: GateReason,
    *,
    within: list[NoiseMetric],
    languages: Collection[str],
    regressed: list[str],
    accuracy_within: bool,
) -> bool:
    """Whether a deciding regression lies within noise; ``languages`` are the regressed
    languages within it."""
    if reason is GateReason.LANGUAGE_REGRESSED:
        return all(language in languages for language in regressed)
    if reason is GateReason.ACCURACY_BELOW_BASELINE:
        return accuracy_within
    metric = _REGRESSION_METRIC.get(reason)
    return metric is not None and metric in within


def _language_beyond(
    language: str,
    delta: float | None,
    noise: NoiseBand | None,
    rates: dict[str, EpisodeRate],
) -> bool:
    """A language's gain counts: by the exact test when its rate was read, else beyond its
    spread in the band (every gain without a band)."""
    if language in rates:
        return rates[language].separates(1)
    return _beyond(delta, noise, None if noise is None else noise.languages.get(language))


def _track_reasons(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    track: GateTrack,
    target_language: str | None,
    deltas: dict[str, float | None],
    delta_j: float,
    accuracy: float | None,
    accuracy_step: float,
    accuracy_band: NoiseSpread | None,
    tokens: float | None,
    seconds: float | None,
    noise: NoiseBand | None = None,
    rates: dict[str, EpisodeRate] | None = None,
) -> list[GateReason]:
    """The track's own reasons, after the shared language-regression check.

    ``accuracy`` is the macro verified accuracy delta the gate decides on (over the
    deciding languages), ``accuracy_step`` its minimum gain and ``accuracy_band`` its
    spread in the band. With a band, each improvement criterion also needs its delta
    beyond the band; with ``rates`` (deciding languages read by the exact test) the macro
    criterion instead needs a deciding language that rose with its rate higher at p below
    the level, and the target language needs its own. ``tokens`` and ``seconds`` are the
    ratios decided on: to the band's mean with a band, else to the baseline.
    """
    rates = rates or {}
    if track == "objective":
        reasons = []
        if delta_j < MIN_OBJECTIVE_GAIN - _EPSILON or not _beyond(
            delta_j, noise, None if noise is None else noise.objective_j
        ):
            reasons.append(GateReason.OBJECTIVE_BELOW_THRESHOLD)
        if not _within(tokens, MAX_TOKEN_RATIO):
            reasons.append(GateReason.TOKENS_ABOVE_CEILING)
        return reasons
    if track == "accuracy":
        reasons = []
        target = None if target_language is None else deltas.get(target_language)
        macro_beyond = (
            any(
                (deltas.get(language) or 0.0) > _EPSILON and rate.separates(1)
                for language, rate in rates.items()
            )
            if rates
            else _beyond(accuracy, noise, accuracy_band)
        )
        improved = (_at_least(accuracy, accuracy_step) and macro_beyond) or (
            target_language is not None
            and _at_least(target, language_step(baseline, target_language))
            and _language_beyond(target_language, target, noise, rates)
        )
        if not improved:
            reasons.append(GateReason.ACCURACY_NOT_IMPROVED)
        if not _within(tokens, MAX_TOKEN_RATIO):
            reasons.append(GateReason.TOKENS_ABOVE_CEILING)
        return reasons
    reasons = []
    if accuracy is None or accuracy < -_EPSILON:
        reasons.append(GateReason.ACCURACY_BELOW_BASELINE)
    comparable = latency_comparable(baseline, candidate)
    tokens_band = None if noise is None else noise.macro_effective_tokens
    seconds_band = None if noise is None else noise.macro_p50_seconds
    if not (
        (_within(tokens, MAX_EFFICIENT_RATIO) and _saving_beyond(tokens, noise, tokens_band))
        or (
            comparable
            and _within(seconds, MAX_EFFICIENT_RATIO)
            and _saving_beyond(seconds, noise, seconds_band)
        )
    ):
        reasons.append(GateReason.EFFICIENCY_NOT_IMPROVED)
    if not comparable:
        reasons.append(GateReason.LATENCY_NOT_COMPARABLE)
    return reasons


def admit_track(baseline: Scorecard, track: GateTrack, target_language: str | None) -> None:
    """A target language belongs to the accuracy track and must be a baseline language."""
    if target_language is None:
        return
    if track != "accuracy":
        raise ValueError("a target language applies only to the accuracy track")
    if target_language not in baseline.languages:
        raise ValueError(f"{target_language} is not a baseline language")


def _paired_regressed(
    paired: PairedOutcomes | None, track: GateTrack, deciding: Sequence[GateReason]
) -> bool:
    """More deciding pass-to-fail than fail-to-pass flips on an otherwise accepting
    accuracy or objective gate."""
    return (
        paired is not None
        and track in ("accuracy", "objective")
        and not deciding
        and paired.deciding_pass_to_fail > paired.deciding_fail_to_pass
    )


def slice_scorecard(
    card: Scorecard, trajectories: Sequence[Trajectory], cases: Collection[str]
) -> Scorecard:
    """``card`` re-aggregated from its trajectories over ``cases`` only: its run, dataset
    and budgets digests, marked sliced, with the repeats those cases ran."""
    kept = [item for item in trajectories if item.case_id in cases]
    sliced = build_scorecard(
        kept,
        run=card.run,
        dataset_digest=card.dataset_digest,
        cases={item.case_id: item.kind for item in kept},
        sliced=True,
    )
    return sliced.model_copy(update={"budgets_digest": card.budgets_digest})


def _case_repeats(trajectories: Sequence[Trajectory], cases: Collection[str]) -> int:
    """The fewest repeats any of ``cases`` ran."""
    counts = Counter(item.case_id for item in trajectories)
    return min((counts[case] for case in cases), default=0)


def admit_slice(
    *,
    smoke: bool,
    track: GateTrack,
    target_language: str | None,
    min_cases: int,
    sides: Sequence[tuple[Scorecard, Sequence[Trajectory] | None]],
) -> None:
    """A slice gate decides on paired outcomes alone, from trajectories of both scorecards."""
    if smoke or track != "objective" or target_language is not None or min_cases != 1:
        raise ValueError(
            "a slice gate decides on paired outcomes only; --smoke, --track, "
            "--target-language and --min-cases do not apply"
        )
    for card, trajectories in sides:
        if trajectories is None:
            raise ValueError("a slice gate reads both runs' trajectories")
        if not trajectories_reproduce(card, trajectories):
            raise ValueError(
                f"the trajectories given for run {card.run.run_id} do not reproduce its scorecard"
            )


def _slice_mismatch(baseline: Scorecard, scored: Collection[str], cases: Collection[str]) -> bool:
    """No slice, a candidate case the baseline did not score, or another sliced baseline."""
    return (
        not cases
        or not set(cases) <= set(scored)
        or (baseline.sliced and set(scored) != set(cases))
    )


def _slice_gate(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    min_repeats: int,
    noise: NoiseBand | None,
    baseline_trajectories: Sequence[Trajectory],
    candidate_trajectories: Sequence[Trajectory],
) -> GateVerdict:
    """The slice screen (module docstring): paired outcomes of the candidate's cases."""
    cases = sorted(case_outcomes(candidate_trajectories))
    scored = sorted(case_outcomes(baseline_trajectories))
    mismatch = _slice_mismatch(baseline, scored, cases)
    before_repeats = _case_repeats(baseline_trajectories, scored if mismatch else cases)
    after_repeats = _case_repeats(candidate_trajectories, cases)
    checks = (
        (GateReason.DATASET_MISMATCH, baseline.dataset_digest != candidate.dataset_digest),
        (GateReason.BUDGETS_MISMATCH, baseline.budgets_digest != candidate.budgets_digest),
        (GateReason.REPEATS_BELOW_MINIMUM, min(before_repeats, after_repeats) < min_repeats),
        (GateReason.SLICE_MISMATCH, mismatch),
        (
            GateReason.NOISE_MISMATCH,
            noise is not None
            and (
                noise.dataset_digest != baseline.dataset_digest
                or noise.budgets_digest != baseline.budgets_digest
                or noise.repeats != before_repeats
            ),
        ),
    )
    reasons = [reason for reason, failed in checks if failed]
    before, after = baseline, candidate
    if not mismatch:
        before = slice_scorecard(baseline, baseline_trajectories, cases)
        after = slice_scorecard(candidate, candidate_trajectories, cases)
    decision = GateDecision.INCOMPARABLE
    paired: PairedOutcomes | None = None
    if not reasons:
        paired = paired_outcomes(
            [item for item in baseline_trajectories if item.case_id in cases],
            candidate_trajectories,
            deciding=list(after.languages),
            noise=noise,
        )
        if any(not case.within_noise for case in paired.pass_to_fail_cases):
            reasons.append(GateReason.SLICE_REGRESSED)
        if all(case.within_noise for case in paired.fail_to_pass_cases):
            reasons.append(GateReason.SLICE_NOT_IMPROVED)
        decision = GateDecision.REJECTED if reasons else GateDecision.ACCEPTED
    return GateVerdict(
        decision=decision,
        reasons=reasons,
        baseline_run_id=baseline.run.run_id,
        candidate_run_id=candidate.run.run_id,
        delta_j=after.objective_j - before.objective_j,
        delta_macro_verified_accuracy=after.macro_verified_accuracy
        - before.macro_verified_accuracy,
        token_ratio=token_ratio(before, after),
        seconds_ratio=seconds_ratio(before, after),
        language_deltas=language_deltas(before, after),
        identity_changes=identity_changes(baseline, candidate),
        single_case_languages=single_case_languages(baseline),
        noise=noise,
        paired=paired,
        slice=True,
        slice_cases=cases,
        slice_repeats=after_repeats,
        # A band of another dataset or repeat count names nothing about these cases.
        slice_unstable_cases=(
            []
            if GateReason.NOISE_MISMATCH in reasons
            else sorted(unstable_cases(noise) & set(cases))
        ),
    )


def gate(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    min_repeats: int = MIN_REPEATS,
    smoke: bool = False,
    track: GateTrack = "objective",
    target_language: str | None = None,
    noise: NoiseBand | None = None,
    min_cases: int = 1,
    baseline_trajectories: Sequence[Trajectory] | None = None,
    candidate_trajectories: Sequence[Trajectory] | None = None,
    slice: bool = False,
) -> GateVerdict:
    """ACCEPTED iff no language regressed and the track's criterion holds (module docstring).

    With ``smoke`` the track's improvement criterion is reported but does not reject.
    ``target_language`` names the accuracy track's target; it must be a baseline language
    (and, with ``min_cases``, a deciding one). ``noise`` reads every delta against a noise
    band; a regression inside it is INCONCLUSIVE rather than REJECTED. ``min_cases`` above
    1 lets only languages with that many baseline cases decide. Both runs' trajectories
    add the paired per-case outcomes and ``paired_regression``. ``slice`` makes a slice
    screen instead (module docstring): it needs both runs' trajectories and takes no track,
    target language, smoke or ``min_cases``.
    """
    if slice:
        admit_slice(
            smoke=smoke,
            track=track,
            target_language=target_language,
            min_cases=min_cases,
            sides=[(baseline, baseline_trajectories), (candidate, candidate_trajectories)],
        )
        return _slice_gate(
            baseline,
            candidate,
            min_repeats=min_repeats,
            noise=noise,
            baseline_trajectories=baseline_trajectories or [],
            candidate_trajectories=candidate_trajectories or [],
        )
    admit_track(baseline, track, target_language)
    admit_min_cases(baseline, min_cases, target_language)
    deciders = deciding_languages(baseline, min_cases)
    deltas = language_deltas(baseline, candidate)
    delta_j = candidate.objective_j - baseline.objective_j
    accuracy = candidate.macro_verified_accuracy - baseline.macro_verified_accuracy
    tokens = token_ratio(baseline, candidate)
    seconds = seconds_ratio(baseline, candidate)
    # With a band, the ratios decided on are to the mean of the band's runs.
    tokens_to_band = seconds_to_band = None
    if noise is not None:
        tokens_to_band = band_ratio(candidate.macro_effective_tokens, noise.macro_effective_tokens)
        seconds_to_band = band_ratio(candidate.macro_p50_seconds, noise.macro_p50_seconds)
    decided_tokens = tokens if noise is None else tokens_to_band
    decided_seconds = seconds if noise is None else seconds_to_band
    regressed = [
        language
        for language, delta in deltas.items()
        if language in deciders and (delta is None or delta < -_EPSILON)
    ]
    narrowed = min_cases > 1
    metrics = deciding_metrics(baseline, candidate, deciders) if narrowed else None
    # The macro accuracy delta, step and band decided on: over the deciding languages.
    decided_accuracy: float | None = accuracy
    accuracy_step = min_accuracy_gain(baseline)
    accuracy_band = None if noise is None else noise.macro_verified_accuracy
    if narrowed:
        decided_accuracy = None if metrics is None else metrics[0].delta
        accuracy_step = min_accuracy_gain(baseline, deciders)
        accuracy_band = None if noise is None else deciding_accuracy_spread(noise, deciders)
    reasons = incomparable_reasons(baseline, candidate, min_repeats)
    if noise is not None and noise_mismatch(noise, baseline, candidate):
        reasons.append(GateReason.NOISE_MISMATCH)
    decision = GateDecision.INCOMPARABLE
    confounded: list[str] = []
    within: list[NoiseMetric] = []
    languages_within: list[str] = []
    paired: PairedOutcomes | None = None
    rates: dict[str, EpisodeRate] = {}
    if not reasons:
        if candidate_trajectories is not None:
            rates = language_rates(noise, candidate_trajectories, deciders)
        if regressed:
            reasons.append(GateReason.LANGUAGE_REGRESSED)
            confounded = operationally_confounded(baseline, candidate, regressed)
        if confounded:
            reasons.append(GateReason.OPERATIONALLY_CONFOUNDED)
        reasons.extend(
            _track_reasons(
                baseline,
                candidate,
                track=track,
                target_language=target_language,
                deltas=deltas,
                delta_j=delta_j,
                accuracy=decided_accuracy,
                accuracy_step=accuracy_step,
                accuracy_band=accuracy_band,
                tokens=decided_tokens,
                seconds=decided_seconds,
                noise=noise,
                rates=rates,
            )
        )
        if noise is not None:
            within, languages_within = within_noise(
                noise,
                deltas=deltas,
                delta_j=delta_j,
                accuracy=accuracy,
                tokens=tokens_to_band,
                seconds=seconds_to_band,
            )
            # A language read by the exact test is within noise when the test does not
            # separate its rate from the band's.
            languages_within = sorted(
                {language for language in languages_within if language not in rates}
                | {
                    language
                    for language, rate in rates.items()
                    if not rate.separates(rate.direction)
                }
            )
        if baseline_trajectories is not None and candidate_trajectories is not None:
            paired = paired_outcomes(
                baseline_trajectories, candidate_trajectories, deciding=deciders, noise=noise
            )
        deciding = [
            reason
            for reason in reasons
            if reason not in _INFORMATIONAL and not (smoke and reason in _IMPROVEMENT)
        ]
        if _paired_regressed(paired, track, deciding):
            reasons.append(GateReason.PAIRED_REGRESSION)
            deciding.append(GateReason.PAIRED_REGRESSION)
        decision = GateDecision.REJECTED if deciding else GateDecision.ACCEPTED
        accuracy_within = (
            inside_band(decided_accuracy, accuracy_band)
            if narrowed
            else "macro_verified_accuracy" in within
        )
        # A regressed language read by the exact test is outside noise only when its rate
        # is lower with p below the level.
        regressions_within = [
            language
            for language in regressed
            if (
                not rates[language].separates(-1)
                if language in rates
                else language in languages_within
            )
        ]
        if (
            deciding
            and noise is not None
            and all(
                _regression_within_noise(
                    reason,
                    within=within,
                    languages=regressions_within,
                    regressed=regressed,
                    accuracy_within=accuracy_within,
                )
                for reason in deciding
            )
        ):
            decision = GateDecision.INCONCLUSIVE
            reasons.append(GateReason.WITHIN_NOISE)
    return GateVerdict(
        decision=decision,
        reasons=reasons,
        baseline_run_id=baseline.run.run_id,
        candidate_run_id=candidate.run.run_id,
        track=track,
        target_language=target_language,
        delta_j=delta_j,
        delta_macro_verified_accuracy=accuracy,
        token_ratio=tokens,
        seconds_ratio=seconds,
        token_ratio_to_band=tokens_to_band,
        seconds_ratio_to_band=seconds_to_band,
        language_deltas=deltas,
        language_rates=rates,
        regressed_languages=regressed,
        operationally_confounded_languages=confounded,
        identity_changes=identity_changes(baseline, candidate),
        smoke=smoke,
        single_case_languages=single_case_languages(baseline),
        noise=noise,
        within_noise=within,
        languages_within_noise=languages_within,
        min_cases=min_cases,
        deciding_languages=deciders if narrowed else [],
        reported_languages=(
            [language for language in sorted(baseline.languages) if language not in deciders]
            if narrowed
            else []
        ),
        deciding_macro_verified_accuracy=None if metrics is None else metrics[0],
        deciding_worst_language=None if metrics is None else metrics[1],
        objective_j_deciding=None if metrics is None else metrics[2],
        paired=paired,
    )


def chain_decision(decisions: Sequence[GateDecision]) -> GateDecision:
    """One decision over gates run in sequence: any REJECTED, else any INCOMPARABLE, else
    any INCONCLUSIVE, else ACCEPTED.

    No gate at all is INCOMPARABLE: nothing was compared.
    """
    if GateDecision.REJECTED in decisions:
        return GateDecision.REJECTED
    if not decisions or GateDecision.INCOMPARABLE in decisions:
        return GateDecision.INCOMPARABLE
    if GateDecision.INCONCLUSIVE in decisions:
        return GateDecision.INCONCLUSIVE
    return GateDecision.ACCEPTED
