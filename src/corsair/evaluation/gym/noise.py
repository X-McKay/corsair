"""The noise band: how far two or more runs of one configuration disagree, per metric.

Pure arithmetic over stored scorecards; nothing is rescored. Runs give a band only when
the gate could compare them (same dataset and budgets, unsliced, enough repeats, known
token usage) and they also recorded one configuration identity and one repeat count, so
their spread is that configuration's run-to-run noise. A gate given the band reads a
delta inside it as noise (``evaluation.gym.gate``).
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from corsair.contracts import GateReason, NoiseBand, Scorecard
from corsair.evaluation.gym.gate import MIN_REPEATS, incomparable_reasons, spread
from corsair.evaluation.gym.render import REASON_TEXT


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


def noise_band(cards: Sequence[Scorecard]) -> NoiseBand:
    """The band of two or more distinct runs of one configuration; refused otherwise."""
    if len(cards) < 2:
        raise ValueError("a noise band needs at least two runs")
    runs = [card.run.run_id for card in cards]
    if len(set(runs)) != len(runs):
        raise ValueError("a run given more than once adds no independent measurement")
    reasons = noise_refusals(cards)
    if reasons:
        raise NoiseRefused(reasons)
    first = cards[0]
    seconds = [card.macro_p50_seconds for card in cards]
    languages = sorted(set().union(*(card.languages for card in cards)))
    return NoiseBand(
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
        languages={
            language: spread([_verified(card, language) for card in cards])
            for language in languages
        },
    )


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
