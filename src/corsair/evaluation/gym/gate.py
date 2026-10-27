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
"""

from collections.abc import Sequence

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateTrack,
    GateVerdict,
    RunIdentity,
    Scorecard,
)

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
_INFORMATIONAL = frozenset({GateReason.OPERATIONALLY_CONFOUNDED, GateReason.LATENCY_NOT_COMPARABLE})


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


def min_accuracy_gain(card: Scorecard) -> float:
    """The smallest macro verified accuracy change one case's majority flip can make.

    Macro accuracy is the mean over languages of each language's fraction of cases whose
    majority of repeats verified, so one flip in language L moves it by
    1 / (languages x cases of L); the smallest such step is in the language with the most
    cases: 1 / (languages x max cases). With six languages and ten python cases that is
    1/60. Any rise with no language regressed is at least this step.
    """
    cases = [summary.cases for summary in card.languages.values() if summary.cases]
    if not cases:
        raise ValueError("a scorecard without cases has no accuracy step")
    return 1 / (len(card.languages) * max(cases))


def _at_least(gain: float | None, step: float | None) -> bool:
    return gain is not None and step is not None and gain >= step - _EPSILON


def _within(ratio: float | None, ceiling: float) -> bool:
    return ratio is not None and ratio <= ceiling + _EPSILON


def _track_reasons(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    track: GateTrack,
    target_language: str | None,
    deltas: dict[str, float | None],
    delta_j: float,
    accuracy: float,
    tokens: float | None,
    seconds: float | None,
) -> list[GateReason]:
    """The track's own reasons, after the shared language-regression check."""
    if track == "objective":
        reasons = []
        if delta_j < MIN_OBJECTIVE_GAIN - _EPSILON:
            reasons.append(GateReason.OBJECTIVE_BELOW_THRESHOLD)
        if not _within(tokens, MAX_TOKEN_RATIO):
            reasons.append(GateReason.TOKENS_ABOVE_CEILING)
        return reasons
    if track == "accuracy":
        reasons = []
        target = None if target_language is None else deltas.get(target_language)
        improved = _at_least(accuracy, min_accuracy_gain(baseline)) or (
            target_language is not None
            and _at_least(target, language_step(baseline, target_language))
        )
        if not improved:
            reasons.append(GateReason.ACCURACY_NOT_IMPROVED)
        if not _within(tokens, MAX_TOKEN_RATIO):
            reasons.append(GateReason.TOKENS_ABOVE_CEILING)
        return reasons
    reasons = []
    if accuracy < -_EPSILON:
        reasons.append(GateReason.ACCURACY_BELOW_BASELINE)
    comparable = latency_comparable(baseline, candidate)
    if not (
        _within(tokens, MAX_EFFICIENT_RATIO)
        or (comparable and _within(seconds, MAX_EFFICIENT_RATIO))
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


def gate(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    min_repeats: int = MIN_REPEATS,
    smoke: bool = False,
    track: GateTrack = "objective",
    target_language: str | None = None,
) -> GateVerdict:
    """ACCEPTED iff no language regressed and the track's criterion holds (module docstring).

    With ``smoke`` the track's improvement criterion is reported but does not reject.
    ``target_language`` names the accuracy track's target; it must be a baseline language.
    """
    admit_track(baseline, track, target_language)
    deltas = language_deltas(baseline, candidate)
    delta_j = candidate.objective_j - baseline.objective_j
    accuracy = candidate.macro_verified_accuracy - baseline.macro_verified_accuracy
    tokens = token_ratio(baseline, candidate)
    seconds = seconds_ratio(baseline, candidate)
    regressed = [
        language for language, delta in deltas.items() if delta is None or delta < -_EPSILON
    ]
    reasons = incomparable_reasons(baseline, candidate, min_repeats)
    decision = GateDecision.INCOMPARABLE
    confounded: list[str] = []
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
                accuracy=accuracy,
                tokens=tokens,
                seconds=seconds,
            )
        )
        deciding = [
            reason
            for reason in reasons
            if reason not in _INFORMATIONAL and not (smoke and reason in _IMPROVEMENT)
        ]
        decision = GateDecision.REJECTED if deciding else GateDecision.ACCEPTED
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
    )


def chain_decision(decisions: Sequence[GateDecision]) -> GateDecision:
    """One decision over gates run in sequence: any REJECTED, else any INCOMPARABLE, else ACCEPTED.

    No gate at all is INCOMPARABLE: nothing was compared.
    """
    if GateDecision.REJECTED in decisions:
        return GateDecision.REJECTED
    if not decisions or GateDecision.INCOMPARABLE in decisions:
        return GateDecision.INCOMPARABLE
    return GateDecision.ACCEPTED
