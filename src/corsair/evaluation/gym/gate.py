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
its magnitude is at most the band (max - min across those runs); a token or seconds ratio
when it lies between 1 / max_ratio and max_ratio. An improvement criterion is then met only
beyond the band. When every deciding reason is a regression (``language_regressed``,
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
from pass to fail than from fail to pass. With a band, a flip in a language whose band is
a whole case (±1.0) is noise and never counts.
"""

from collections import Counter
from collections.abc import Collection, Sequence
from statistics import mean

from corsair.contracts import (
    DecidingMetric,
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
from corsair.evaluation.gym.scoring import case_outcomes, objective_terms

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


_PAIRING = {
    (True, True): "stable_pass",
    (True, False): "pass_to_fail",
    (False, True): "fail_to_pass",
    (False, False): "stable_fail",
}


def paired_outcomes(
    baseline: Sequence[Trajectory],
    candidate: Sequence[Trajectory],
    *,
    deciding: Collection[str],
    noise: NoiseBand | None = None,
) -> PairedOutcomes:
    """Every case scored on both sides by its baseline and candidate majority outcome.

    A flip in a language outside ``deciding`` is listed but never counted in
    ``deciding_pass_to_fail``/``deciding_fail_to_pass``; with ``noise`` neither is a flip in
    a language whose band is a whole case.
    """
    before, after = case_outcomes(baseline), case_outcomes(candidate)
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
        flip = PairedCase(
            case_id=case,
            language=language,
            deciding=language in deciding,
            within_noise=noise is not None and _whole_case(noise.languages.get(language)),
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
    """A ratio between the band's runs' smallest and largest ratio."""
    if ratio is None or spread is None or spread.max_ratio is None:
        return False
    return 1 / spread.max_ratio - _EPSILON <= ratio <= spread.max_ratio + _EPSILON


def _beyond(delta: float | None, noise: NoiseBand | None, spread: NoiseSpread | None) -> bool:
    """A gain counts beyond the band; without a band every gain does."""
    if noise is None:
        return True
    return delta is not None and spread is not None and delta > spread.band + _EPSILON


def _saving_beyond(
    ratio: float | None, noise: NoiseBand | None, spread: NoiseSpread | None
) -> bool:
    """A ratio saving counts below the band's smallest ratio; without a band every one does."""
    if noise is None:
        return True
    if ratio is None or spread is None or spread.max_ratio is None:
        return False
    return ratio < 1 / spread.max_ratio - _EPSILON


def within_noise(
    noise: NoiseBand,
    *,
    deltas: dict[str, float | None],
    delta_j: float,
    accuracy: float,
    tokens: float | None,
    seconds: float | None,
) -> tuple[list[NoiseMetric], list[str]]:
    """The headline metrics and the languages whose delta lies inside the band."""
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
    languages: list[str],
    regressed: list[str],
    accuracy_within: bool,
) -> bool:
    if reason is GateReason.LANGUAGE_REGRESSED:
        return all(language in languages for language in regressed)
    if reason is GateReason.ACCURACY_BELOW_BASELINE:
        return accuracy_within
    metric = _REGRESSION_METRIC.get(reason)
    return metric is not None and metric in within


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
) -> list[GateReason]:
    """The track's own reasons, after the shared language-regression check.

    ``accuracy`` is the macro verified accuracy delta the gate decides on (over the
    deciding languages), ``accuracy_step`` its minimum gain and ``accuracy_band`` its
    spread in the band. With a band, each improvement criterion also needs its delta
    beyond the band.
    """
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
        target_band = (
            None
            if noise is None or target_language is None
            else noise.languages.get(target_language)
        )
        improved = (
            _at_least(accuracy, accuracy_step) and _beyond(accuracy, noise, accuracy_band)
        ) or (
            target_language is not None
            and _at_least(target, language_step(baseline, target_language))
            and _beyond(target, noise, target_band)
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
) -> GateVerdict:
    """ACCEPTED iff no language regressed and the track's criterion holds (module docstring).

    With ``smoke`` the track's improvement criterion is reported but does not reject.
    ``target_language`` names the accuracy track's target; it must be a baseline language
    (and, with ``min_cases``, a deciding one). ``noise`` reads every delta against a noise
    band; a regression inside it is INCONCLUSIVE rather than REJECTED. ``min_cases`` above
    1 lets only languages with that many baseline cases decide. Both runs' trajectories
    add the paired per-case outcomes and ``paired_regression``.
    """
    admit_track(baseline, track, target_language)
    admit_min_cases(baseline, min_cases, target_language)
    deciders = deciding_languages(baseline, min_cases)
    deltas = language_deltas(baseline, candidate)
    delta_j = candidate.objective_j - baseline.objective_j
    accuracy = candidate.macro_verified_accuracy - baseline.macro_verified_accuracy
    tokens = token_ratio(baseline, candidate)
    seconds = seconds_ratio(baseline, candidate)
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
    if not reasons:
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
                tokens=tokens,
                seconds=seconds,
                noise=noise,
            )
        )
        if noise is not None:
            within, languages_within = within_noise(
                noise,
                deltas=deltas,
                delta_j=delta_j,
                accuracy=accuracy,
                tokens=tokens,
                seconds=seconds,
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
        if (
            deciding
            and noise is not None
            and all(
                _regression_within_noise(
                    reason,
                    within=within,
                    languages=languages_within,
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
        language_deltas=deltas,
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
