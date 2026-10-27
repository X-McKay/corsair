"""Decide whether a candidate scorecard beats its baseline; exit codes 0, 1 and 2.

INCOMPARABLE is never a regression verdict: different datasets or budgets, a sliced run,
too few repeats or unknown token usage mean the two scorecards answer different questions.
Identity changes, operational stops and target-side exception episodes are reported beside
the decision and never change it: a different prompt, skill, image or model is what a
candidate is, an operational stop keeps its ERROR score, and a target-side exception
already scores 0 on its scorecard.

A smoke gate (``smoke=True``, for a tier where every language already verifies, so the
objective margin is noise) still reports ``objective_below_threshold`` but decides only on
language regressions, the token ceiling and the INCOMPARABLE conditions; its verdict says
``smoke`` so its ACCEPTED is never read as an acceptance.
"""

from collections.abc import Sequence

from corsair.contracts import GateDecision, GateReason, GateVerdict, RunIdentity, Scorecard

MIN_REPEATS = 3
MIN_OBJECTIVE_GAIN = 0.01
MAX_TOKEN_RATIO = 1.10
# Floating-point slack so a gain or ratio exactly at its threshold is decided as written.
_EPSILON = 1e-9


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


def gate(
    baseline: Scorecard,
    candidate: Scorecard,
    *,
    min_repeats: int = MIN_REPEATS,
    smoke: bool = False,
) -> GateVerdict:
    """ACCEPTED iff no language regressed, J gained at least 0.01 and tokens stayed within 1.10x.

    With ``smoke`` the objective margin is reported but does not reject.
    """
    deltas = language_deltas(baseline, candidate)
    delta_j = candidate.objective_j - baseline.objective_j
    ratio = token_ratio(baseline, candidate)
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
        if delta_j < MIN_OBJECTIVE_GAIN - _EPSILON:
            reasons.append(GateReason.OBJECTIVE_BELOW_THRESHOLD)
        if ratio is None or ratio > MAX_TOKEN_RATIO + _EPSILON:
            reasons.append(GateReason.TOKENS_ABOVE_CEILING)
        deciding = [
            reason
            for reason in reasons
            if not (smoke and reason is GateReason.OBJECTIVE_BELOW_THRESHOLD)
        ]
        decision = GateDecision.REJECTED if deciding else GateDecision.ACCEPTED
    return GateVerdict(
        decision=decision,
        reasons=reasons,
        baseline_run_id=baseline.run.run_id,
        candidate_run_id=candidate.run.run_id,
        delta_j=delta_j,
        token_ratio=ratio,
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
