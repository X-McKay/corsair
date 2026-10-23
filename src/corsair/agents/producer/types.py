"""Producer-specific output and control-flow types."""

from __future__ import annotations

from dataclasses import dataclass

from corsair.domain.verification import Evaluation, Verdict


class BudgetExhausted(Exception):
    """The operator-owned submission budget is spent; the last gate decides the terminal verdict."""


class NegativeThresholdReached(Exception):
    """Enough distinct clean negatives were observed to stop exploration early."""


@dataclass(frozen=True)
class ProducerRun:
    verdict: Verdict
    evaluations: tuple[Evaluation, ...]
    requests: int | None
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int | None
    bash_calls: int
    duration_s: float
    final_text: str | None
    error: str | None
    cleanup_confirmed: bool | None
    early_stop: str | None = None
    observations: tuple[dict, ...] = ()
