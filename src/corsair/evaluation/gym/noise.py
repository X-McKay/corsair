"""The noise band: how far two or more runs of one configuration disagree, per metric.

Pure arithmetic over stored scorecards; nothing is rescored. Runs give a band only when
the gate could compare them (same dataset and budgets, unsliced, enough repeats, known
token usage) and they also recorded one configuration identity and one repeat count, so
their spread is that configuration's run-to-run noise. A gate given the band reads a
delta inside it as noise (``evaluation.gym.gate``).

Given each run's trajectories, the band also records every case scored in all runs: its
majority outcome and verified episodes per run, its episodes and verified episodes pooled
over the runs, and the probability that a run of the band's repeats at that pooled rate
gets a majority pass (``exact.majority_pass_probability``). The case is ``stable_pass``
when a majority fail has probability at most ``SIGNIFICANCE_LEVEL``, ``stable_fail``
when a majority pass has, and ``unstable`` otherwise. A run without trajectories
reproducing its scorecard leaves the cases unknown, with the reason and the run named;
nothing is guessed.

Operational episodes (``Trajectory.operational``: a heartbeat timeout, a lost worker, a
provider error) are a harness fault, not the configuration's behaviour, so the pooled
counts and the resampling leave them out; each case records how many it left out. A case
with no non-operational episode in some run pools the other runs'; one with none in any
run has no rate, is named in ``operational_cases`` and the band records no interval
rather than a guessed or zero rate. The per-run values (from the scorecards) and majority
outcomes are the runs as scored.

From the same trajectories the band records resampled intervals (``ResampledInterval``):
``RESAMPLES`` synthetic runs, each drawing for every case the band's repeats episodes with
replacement from that case's episodes pooled over the runs, scored by ``build_scorecard``
exactly as a run is. Cases and their episodes are treated as exchangeable within a case
and independent across cases: a synthetic run is what a run of the same configuration
could have scored if each case's episodes are draws at its pooled rate, so the interval
carries each case's majority coin-flip, which the half-range of a few runs understates.
The draws use ``random.Random(seed)``, so a band is reproducible from its runs and seed.

Macro sandbox CPU seconds (the driver's CPU time for the sandboxed runs) are recorded per
run with their spread and, on a resampled band, their interval: information only, which
no gate rule reads.
"""

import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import fmean

from corsair.contracts import (
    GateReason,
    LanguageSetInterval,
    NoiseBand,
    NoiseCase,
    NoiseSpread,
    ResampledInterval,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.exact import majority_pass_probability
from corsair.evaluation.gym.gate import (
    MIN_REPEATS,
    incomparable_reasons,
    spread,
    trajectories_reproduce,
)
from corsair.evaluation.gym.render import REASON_TEXT
from corsair.evaluation.gym.scoring import (
    build_scorecard,
    case_outcomes,
    objective_terms,
    percentile,
)

# Synthetic runs per band, and the percentiles an interval spans.
RESAMPLES = 2000
INTERVAL_LOW, INTERVAL_HIGH = 2.5, 97.5


class NoiseRefused(ValueError):
    """Runs that give no band; ``reasons`` are code-owned gate reasons."""

    def __init__(self, reasons: Sequence[GateReason]) -> None:
        self.reasons = list(reasons)
        details = " ".join(f"{reason.value}: {REASON_TEXT[reason]}" for reason in self.reasons)
        super().__init__(f"the runs give no noise band; {details}")


def noise_refusals(cards: Sequence[Scorecard], min_repeats: int = MIN_REPEATS) -> list[GateReason]:
    """Why ``cards`` are not runs of one configuration on one dataset, in reason order."""
    first = cards[0]
    reasons: set[GateReason] = set()
    for card in cards:
        reasons.update(incomparable_reasons(first, card, min_repeats))
        if not card.run_identity or card.run_identity != first.run_identity:
            reasons.add(GateReason.IDENTITY_MISMATCH)
        if card.repeats != first.repeats:
            reasons.add(GateReason.REPEATS_MISMATCH)
    return [reason for reason in GateReason if reason in reasons]


def noise_band(
    cards: Sequence[Scorecard],
    trajectories: Sequence[Sequence[Trajectory] | None] | None = None,
    *,
    seed: int = 0,
    resamples: int = RESAMPLES,
) -> NoiseBand:
    """The band of two or more distinct runs of one configuration; refused otherwise.

    ``trajectories`` follow ``cards``; each run's must reproduce its scorecard for the
    band to classify cases and resample intervals (``resamples`` synthetic runs drawn with
    ``seed``), and without them every run is named as missing its own.
    """
    if len(cards) < 2:
        raise ValueError("a noise band needs at least two runs")
    runs = [card.run.run_id for card in cards]
    if len(set(runs)) != len(runs):
        raise ValueError("a run given more than once adds no independent measurement")
    reasons = noise_refusals(cards)
    if reasons:
        raise NoiseRefused(reasons)
    if trajectories is not None and len(trajectories) != len(cards):
        raise ValueError("a noise band reads one trajectory record per run")
    first = cards[0]
    seconds = [card.macro_p50_seconds for card in cards]
    cpu = [card.macro_sandbox_cpu_seconds for card in cards]
    languages = sorted(set().union(*(card.languages for card in cards)))
    records = list(trajectories) if trajectories is not None else [None] * len(cards)
    missing = [
        card.run.run_id
        for card, rows in zip(cards, records, strict=True)
        if rows is None or not trajectories_reproduce(card, rows)
    ]
    cases, unpooled = _noise_cases([rows or [] for rows in records], first.repeats)
    band = NoiseBand(
        dataset_digest=first.dataset_digest,
        budgets_digest=first.budgets_digest,
        repeats=first.repeats,
        run_identity=first.run_identity,
        n_runs=len(cards),
        runs=runs,
        objective_j=spread([card.objective_j for card in cards]),
        macro_verified_accuracy=spread([card.macro_verified_accuracy for card in cards]),
        # Known on every card: unknown token usage was refused above.
        macro_effective_tokens=spread(
            [card.macro_effective_tokens or 0.0 for card in cards], ratio=True
        ),
        macro_p50_seconds=(
            None
            if any(value is None for value in seconds)
            else spread([value or 0.0 for value in seconds], ratio=True)
        ),
        # Information only; no gate rule reads it.
        macro_sandbox_cpu_seconds=(
            None
            if any(value is None for value in cpu)
            else spread([value or 0.0 for value in cpu], ratio=True)
        ),
        sandbox_cpu_unknown=[card.sandbox_cpu_unknown for card in cards],
        languages={
            language: spread([_verified(card, language) for card in cards])
            for language in languages
        },
        cases=None if missing else cases,
        cases_unknown="trajectories_missing" if missing else None,
        cases_unknown_runs=missing,
        operational_episodes=[card.operational_episodes for card in cards],
        operational_cases=[] if missing else unpooled,
    )
    if missing or band.operational_cases:
        return band
    synthetic = resampled_runs(
        first, [rows or [] for rows in records], resamples=resamples, seed=seed
    )
    return with_intervals(band, first, synthetic, seed=seed)


def resampled_runs(
    card: Scorecard, runs: Sequence[Sequence[Trajectory]], *, resamples: int, seed: int
) -> list[Scorecard]:
    """``resamples`` synthetic runs: per case (in case order), ``card.repeats`` episodes
    drawn with replacement from the case's non-operational episodes pooled over ``runs``,
    scored by ``build_scorecard``. Every case needs one such episode."""
    if resamples < 1:
        raise ValueError("a noise band draws at least one synthetic run")
    pools: dict[str, list[Trajectory]] = defaultdict(list)
    for rows in runs:
        for item in rows:
            pools.setdefault(item.case_id, [])
            if not item.operational:
                pools[item.case_id].append(item)
    empty = sorted(case for case, rows in pools.items() if not rows)
    if empty:
        raise ValueError(f"no non-operational episode to draw for {', '.join(empty)}")
    cases = {case: rows[0].kind for case, rows in sorted(pools.items())}
    draw = random.Random(seed)
    return [
        build_scorecard(
            [item for case in cases for item in draw.choices(pools[case], k=card.repeats)],
            run=card.run,
            dataset_digest=card.dataset_digest,
            cases=cases,
        )
        for _ in range(resamples)
    ]


def resampled_interval(values: Sequence[float | None]) -> ResampledInterval | None:
    """The 2.5th to 97.5th percentile and mean of ``values``; unknown when any is."""
    known = [value for value in values if value is not None]
    if not known or len(known) != len(values):
        return None
    low, high = percentile(known, INTERVAL_LOW), percentile(known, INTERVAL_HIGH)
    if low is None or high is None:
        return None
    return ResampledInterval(low=low, high=high, mean=fmean(known))


def language_sets(card: Scorecard) -> list[list[str]]:
    """Per distinct case count c of ``card``'s languages, the languages with at least c
    cases: the set ``--min-cases c`` decides on, from every language down to the largest."""
    counts = sorted({summary.cases for summary in card.languages.values() if summary.cases})
    return [
        sorted(name for name, summary in card.languages.items() if summary.cases >= count)
        for count in counts
    ]


def with_intervals(
    band: NoiseBand, card: Scorecard, synthetic: Sequence[Scorecard], *, seed: int
) -> NoiseBand:
    """``band`` with each metric's resampled interval over the ``synthetic`` runs."""

    def interval(spread: NoiseSpread, metric: Callable[[Scorecard], float | None]):
        return spread.model_copy(
            update={"interval": resampled_interval([metric(run) for run in synthetic])}
        )

    sets = []
    for names in language_sets(card):
        terms = [
            objective_terms({name: run.languages[name] for name in names}) for run in synthetic
        ]
        macro = resampled_interval([item.macro_verified_accuracy for item in terms])
        worst = resampled_interval([item.worst_language_verified_accuracy for item in terms])
        if macro is not None and worst is not None:
            sets.append(
                LanguageSetInterval(
                    min_cases=min(card.languages[name].cases for name in names),
                    languages=names,
                    macro_verified_accuracy=macro,
                    worst_language_verified_accuracy=worst,
                )
            )
    seconds, cpu = band.macro_p50_seconds, band.macro_sandbox_cpu_seconds
    resampled = band.model_copy(
        update={
            "objective_j": interval(band.objective_j, lambda run: run.objective_j),
            "macro_verified_accuracy": interval(
                band.macro_verified_accuracy, lambda run: run.macro_verified_accuracy
            ),
            "macro_effective_tokens": interval(
                band.macro_effective_tokens, lambda run: run.macro_effective_tokens
            ),
            "macro_p50_seconds": (
                None if seconds is None else interval(seconds, lambda run: run.macro_p50_seconds)
            ),
            "macro_sandbox_cpu_seconds": (
                None if cpu is None else interval(cpu, lambda run: run.macro_sandbox_cpu_seconds)
            ),
            "languages": {
                language: interval(spread, lambda run, name=language: _verified(run, name))
                for language, spread in band.languages.items()
            },
            "language_sets": sets,
            "resamples": len(synthetic),
            "seed": seed,
        }
    )
    # A copy skips validation; the record is checked as it will be read.
    return NoiseBand.model_validate(resampled.model_dump())


def _noise_cases(
    runs: Sequence[Sequence[Trajectory]], repeats: int
) -> tuple[list[NoiseCase], list[str]]:
    """Every case scored in all ``runs``: its majority outcome and verified count per run,
    its non-operational episodes pooled and the majority-pass probability of a run of
    ``repeats`` at that rate; and, apart, the cases with no non-operational episode."""
    outcomes = [case_outcomes(rows) for rows in runs]
    kept = [[item for item in rows if not item.operational] for rows in runs]
    verified = [Counter(item.case_id for item in rows if item.verified) for rows in kept]
    episodes = [Counter(item.case_id for item in rows) for rows in kept]
    operational = Counter(item.case_id for rows in runs for item in rows if item.operational)
    shared = set(outcomes[0]).intersection(*outcomes[1:]) if outcomes else set()
    cases, unpooled = [], []
    for case in sorted(shared):
        pooled_verified = sum(counts[case] for counts in verified)
        pooled_episodes = sum(counts[case] for counts in episodes)
        if not pooled_episodes:
            unpooled.append(case)
            continue
        probability = majority_pass_probability(pooled_verified, pooled_episodes, repeats)
        cases.append(
            NoiseCase(
                case_id=case,
                language=outcomes[0][case][0],
                majority_verified=[run[case][1] for run in outcomes],
                verified_episodes=[counts[case] for counts in verified],
                stability=NoiseCase.pooled_stability(probability),
                episodes=pooled_episodes,
                verified=pooled_verified,
                majority_pass_probability=probability,
                operational_excluded=operational[case],
            )
        )
    return cases, unpooled


def _verified(card: Scorecard, language: str) -> float:
    """A language's majority verified accuracy; one dataset gives every run its languages."""
    summary = card.languages.get(language)
    return 0.0 if summary is None else summary.verified_accuracy or 0.0


def write_noise(path: Path, band: NoiseBand) -> None:
    """Write the band; an existing file holding another band is a reference, never replaced."""
    text = json.dumps(band.model_dump(mode="json"), indent=2) + "\n"
    if path.exists() and path.read_text() != text:
        raise ValueError(
            f"{path} already holds a different noise band; remove it or pass another --out"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def read_noise(path: Path) -> NoiseBand:
    return NoiseBand.model_validate_json(path.read_bytes())


def assign_bands(
    bands: Mapping[str, NoiseBand], datasets: Mapping[str, str]
) -> dict[str, tuple[str, NoiseBand]]:
    """Each gated tier's band: the one band (keyed by its path) scored on its dataset.

    A band that matches no tier, or a tier two bands match, is refused, so no band is
    silently ignored.
    """
    assigned: dict[str, tuple[str, NoiseBand]] = {}
    for path, band in bands.items():
        tiers = [tier for tier, digest in datasets.items() if digest == band.dataset_digest]
        if not tiers:
            raise ValueError(f"noise band {path} matches no gated tier's dataset")
        for tier in tiers:
            if tier in assigned:
                raise ValueError(f"more than one noise band matches {tier}'s dataset")
            assigned[tier] = (path, band)
    return dict(sorted(assigned.items()))
