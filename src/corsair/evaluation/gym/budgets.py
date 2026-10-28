"""Per-kind efficiency budgets: load, write, digest, and derive from a scorecard's p95."""

import json
from pathlib import Path

from corsair.contracts import KindBudget, Scorecard, digest
from corsair.contracts.gym import Budgets


def load_budgets(path: Path) -> Budgets:
    return Budgets.model_validate_json(path.read_bytes())


def budgets_digest(budgets: Budgets) -> str:
    """Digest of the canonical JSON value, so formatting never changes the identity."""
    return digest(budgets.model_dump(mode="json"))


def write_budgets(path: Path, budgets: Budgets) -> str:
    """Write the budgets file and return its digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(budgets.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return budgets_digest(budgets)


def derive_budgets(scorecard: Scorecard) -> Budgets:
    """Budgets from each kind's p95 effective tokens and p95 seconds.

    A kind whose p95 is unknown or zero gets no budget, so it earns no efficiency bonus,
    rather than a guessed one.
    """
    budgets: dict[str, KindBudget] = {}
    for kind, summary in sorted(scorecard.kinds.items()):
        tokens, seconds = summary.p95_effective_tokens, summary.p95_seconds
        if tokens and seconds:
            budgets[kind] = KindBudget(effective_tokens=tokens, seconds=seconds)
    if not budgets:
        raise ValueError("the scorecard has no kind with known p95 tokens and seconds")
    return Budgets(budgets)
