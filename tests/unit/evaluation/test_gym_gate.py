"""Gym gate: ACCEPTED, REJECTED and INCOMPARABLE decisions and their exit codes."""

import pytest

from corsair.contracts import GateDecision, GateReason, RunContext, Scorecard, Trajectory
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.scoring import build_scorecard

CASES = {"py-a": "python.k/1", "py-b": "python.k/1", "rb-a": "ruby.k/1", "rb-b": "ruby.k/1"}


def _trajectory(case: str, repeat: int, verified: bool, tokens: float | None) -> Trajectory:
    return Trajectory(
        run_id=f"{case}-{repeat}",
        case_id=case,
        repeat=repeat,
        kind=CASES[case],
        language=CASES[case].split(".")[0],
        status="pass" if verified else "fail",
        passed=verified,
        verified=verified,
        false_label=False,
        usage_known=tokens is not None,
        effective_tokens=tokens,
        reward_verdict=1.0 if verified else 0.0,
        reward=1.0 if verified else 0.0,
    )


def _card(
    verified: dict[str, list[bool]],
    *,
    run_id: str = "run",
    tokens: float | None = 100.0,
    digest: str = "d" * 64,
    budgets=None,
    sliced: bool = False,
) -> Scorecard:
    rows = [
        _trajectory(case, repeat, flag, tokens)
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]
    card = build_scorecard(
        rows, run=RunContext(run_id=run_id), dataset_digest=digest, cases=CASES, sliced=sliced
    )
    return card if budgets is None else card.model_copy(update={"budgets_digest": budgets})


ALL = [True, True, True]
NONE = [False, False, False]
BASELINE = {"py-a": ALL, "py-b": NONE, "rb-a": ALL, "rb-b": NONE}


def test_an_improvement_without_regression_is_accepted():
    candidate = {**BASELINE, "py-b": ALL}
    verdict = gate(_card(BASELINE), _card(candidate, run_id="cand"))
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.exit_code == 0
    assert verdict.delta_j == pytest.approx(0.25)
    assert verdict.regressed_languages == []


def test_a_single_language_regression_is_rejected_even_when_j_improves():
    candidate = {"py-a": ALL, "py-b": ALL, "rb-a": [True, False, False], "rb-b": NONE}
    baseline = {"py-a": NONE, "py-b": NONE, "rb-a": ALL, "rb-b": NONE}
    verdict = gate(_card(baseline), _card(candidate, run_id="cand"))
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.exit_code == 1
    assert verdict.regressed_languages == ["ruby"]
    assert GateReason.LANGUAGE_REGRESSED in verdict.reasons


def test_one_flaky_repeat_does_not_regress_a_language():
    candidate = {**BASELINE, "py-b": ALL, "rb-a": [True, False, True]}
    verdict = gate(_card(BASELINE), _card(candidate, run_id="cand"))
    assert verdict.decision is GateDecision.ACCEPTED


def test_too_small_an_objective_gain_or_too_many_tokens_is_rejected():
    same = gate(_card(BASELINE), _card(BASELINE, run_id="cand"))
    assert same.decision is GateDecision.REJECTED
    assert same.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD]
    better = {**BASELINE, "py-b": ALL}
    costly = gate(_card(BASELINE), _card(better, run_id="cand", tokens=111.0))
    assert costly.decision is GateDecision.REJECTED
    assert costly.reasons == [GateReason.TOKENS_ABOVE_CEILING]
    assert costly.token_ratio == pytest.approx(1.11)
    allowed = gate(_card(BASELINE), _card(better, run_id="cand", tokens=110.0))
    assert allowed.decision is GateDecision.ACCEPTED


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        ({"digest": "e" * 64}, GateReason.DATASET_MISMATCH),
        ({"budgets": "b" * 64}, GateReason.BUDGETS_MISMATCH),
        ({"sliced": True}, GateReason.SLICED),
        ({"tokens": None}, GateReason.TOKENS_UNKNOWN),
    ],
)
def test_mismatched_or_sliced_runs_are_incomparable(candidate, reason):
    verdict = gate(_card(BASELINE), _card({**BASELINE, "py-b": ALL}, run_id="cand", **candidate))
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.exit_code == 2
    assert reason in verdict.reasons


def test_fewer_repeats_than_the_minimum_are_incomparable():
    short = {case: [flag[0]] * 2 for case, flag in BASELINE.items()}
    verdict = gate(_card(BASELINE), _card(short, run_id="cand"))
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.reasons == [GateReason.REPEATS_BELOW_MINIMUM]
    assert gate(_card(BASELINE), _card(short, run_id="cand"), min_repeats=2).decision is (
        GateDecision.REJECTED
    )
