"""Gym budgets: canonical digest, round trip and derivation from a scorecard's p95."""

import pytest

from corsair.contracts import KindBudget, RunContext, Trajectory
from corsair.contracts.gym import Budgets
from corsair.evaluation.gym.budgets import (
    budgets_digest,
    derive_budgets,
    load_budgets,
    write_budgets,
)
from corsair.evaluation.gym.scoring import build_scorecard


def _trajectory(case: str, kind: str, tokens: float | None, seconds: float | None) -> Trajectory:
    return Trajectory(
        run_id=f"run-{case}",
        case_id=case,
        repeat=0,
        kind=kind,
        language=kind.split(".")[0],
        status="pass",
        passed=True,
        verified=True,
        false_label=False,
        usage_known=tokens is not None,
        effective_tokens=tokens,
        seconds=seconds,
        reward_verdict=1.0,
        reward=1.0,
    )


def test_budgets_round_trip_with_a_formatting_independent_digest(tmp_path):
    budgets = Budgets({"python.k/1": KindBudget(effective_tokens=5000, seconds=60)})
    path = tmp_path / "budgets.json"
    written = write_budgets(path, budgets)
    assert load_budgets(path) == budgets
    assert written == budgets_digest(budgets)
    path.write_text('{"python.k/1":{"seconds":60,"effective_tokens":5000}}')
    assert budgets_digest(load_budgets(path)) == written


def test_budgets_are_derived_from_each_kind_p95_and_skip_unknown_kinds():
    rows = [_trajectory(f"p{i}", "python.k/1", 100.0 * i, 10.0 * i) for i in range(1, 21)]
    rows.append(_trajectory("r1", "ruby.k/1", None, None))
    cases = {row.case_id: row.kind for row in rows}
    card = build_scorecard(rows, run=RunContext(run_id="ref"), dataset_digest="d" * 64, cases=cases)
    budgets = derive_budgets(card)
    assert budgets.root == {"python.k/1": KindBudget(effective_tokens=1900.0, seconds=190.0)}


def test_a_scorecard_without_known_usage_derives_no_budgets():
    rows = [_trajectory("r1", "ruby.k/1", None, None)]
    card = build_scorecard(
        rows, run=RunContext(run_id="ref"), dataset_digest="d" * 64, cases={"r1": "ruby.k/1"}
    )
    with pytest.raises(ValueError, match="no kind"):
        derive_budgets(card)
