"""Gym gate: ACCEPTED, REJECTED and INCOMPARABLE decisions and their exit codes."""

import pytest

from corsair.contracts import GateDecision, GateReason, RunContext, Scorecard, Trajectory
from corsair.evaluation.gym.gate import chain_decision, gate, min_accuracy_gain
from corsair.evaluation.gym.scoring import build_scorecard

CASES = {"py-a": "python.k/1", "py-b": "python.k/1", "rb-a": "ruby.k/1", "rb-b": "ruby.k/1"}


def _trajectory(
    case: str, repeat: int, verified: bool, tokens: float | None, seconds: float = 10.0
) -> Trajectory:
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
        seconds=seconds,
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
    seconds: float = 10.0,
    concurrency: int | None = 2,
) -> Scorecard:
    rows = [
        _trajectory(case, repeat, flag, tokens, seconds)
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]
    card = build_scorecard(
        rows,
        run=RunContext(run_id=run_id, concurrency=concurrency),
        dataset_digest=digest,
        cases=CASES,
        sliced=sliced,
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


@pytest.mark.parametrize(
    ("decisions", "expected"),
    [
        (["ACCEPTED", "ACCEPTED"], "ACCEPTED"),
        (["ACCEPTED"], "ACCEPTED"),
        (["REJECTED"], "REJECTED"),
        (["INCOMPARABLE", "REJECTED"], "REJECTED"),
        (["ACCEPTED", "INCOMPARABLE"], "INCOMPARABLE"),
        (["INCOMPARABLE", "ACCEPTED"], "INCOMPARABLE"),
        ([], "INCOMPARABLE"),
    ],
)
def test_a_chain_of_gates_rejects_on_any_rejection_and_accepts_only_when_all_accept(
    decisions, expected
):
    assert chain_decision([GateDecision(item) for item in decisions]) is GateDecision(expected)


# Tracks


def test_the_default_track_is_the_objective_rule():
    better = {**BASELINE, "py-b": ALL}
    verdict = gate(_card(BASELINE), _card(better, run_id="cand"))
    assert verdict.track == "objective"
    assert verdict == gate(_card(BASELINE), _card(better, run_id="cand"), track="objective")


def test_the_minimum_accuracy_gain_is_one_majority_flip_in_the_largest_language():
    # Two languages of two cases each: one case flipping moves its language by 1/2 and
    # macro accuracy by 1/(2 x 2).
    assert min_accuracy_gain(_card(BASELINE)) == pytest.approx(0.25)


def _flat_j(card: Scorecard, baseline: Scorecard) -> Scorecard:
    """The candidate with the baseline's J: the accuracy track must not read J."""
    return card.model_copy(update={"objective_j": baseline.objective_j})


def test_the_accuracy_track_accepts_a_verified_gain_that_j_does_not_show():
    baseline = _card(BASELINE)
    candidate = _flat_j(_card({**BASELINE, "py-b": ALL}, run_id="cand", tokens=107.0), baseline)
    objective = gate(baseline, candidate)
    assert objective.decision is GateDecision.REJECTED
    assert objective.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD]
    accuracy = gate(baseline, candidate, track="accuracy")
    assert accuracy.decision is GateDecision.ACCEPTED
    assert accuracy.reasons == []
    assert accuracy.track == "accuracy"
    assert accuracy.delta_j == pytest.approx(0.0)
    assert accuracy.delta_macro_verified_accuracy == pytest.approx(0.25)
    assert accuracy.token_ratio == pytest.approx(1.07)


def test_the_accuracy_track_rejects_no_gain_a_regression_or_too_many_tokens():
    baseline = _card(BASELINE)
    same = gate(baseline, _card(BASELINE, run_id="cand"), track="accuracy")
    assert same.decision is GateDecision.REJECTED
    assert same.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    traded = {"py-a": ALL, "py-b": ALL, "rb-a": NONE, "rb-b": NONE}
    regressed = gate(baseline, _card(traded, run_id="cand"), track="accuracy")
    assert regressed.decision is GateDecision.REJECTED
    assert regressed.reasons == [GateReason.LANGUAGE_REGRESSED, GateReason.ACCURACY_NOT_IMPROVED]
    better = {**BASELINE, "py-b": ALL}
    costly = gate(baseline, _card(better, run_id="cand", tokens=111.0), track="accuracy")
    assert costly.decision is GateDecision.REJECTED
    assert costly.reasons == [GateReason.TOKENS_ABOVE_CEILING]


def test_the_accuracy_track_records_its_target_language():
    baseline = _card(BASELINE)
    candidate = _card({**BASELINE, "py-b": ALL}, run_id="cand")
    verdict = gate(baseline, candidate, track="accuracy", target_language="python")
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.target_language == "python"
    same = gate(baseline, _card(BASELINE, run_id="cand"), track="accuracy", target_language="ruby")
    assert same.reasons == [GateReason.ACCURACY_NOT_IMPROVED]


def test_a_target_language_needs_the_accuracy_track_and_a_baseline_language():
    baseline, candidate = _card(BASELINE), _card(BASELINE, run_id="cand")
    with pytest.raises(ValueError, match="accuracy track"):
        gate(baseline, candidate, track="objective", target_language="python")
    with pytest.raises(ValueError, match="not a baseline language"):
        gate(baseline, candidate, track="accuracy", target_language="c")


def test_the_efficiency_track_accepts_ten_percent_fewer_tokens_or_seconds():
    baseline = _card(BASELINE)
    fewer = gate(baseline, _card(BASELINE, run_id="cand", tokens=90.0), track="efficiency")
    assert fewer.decision is GateDecision.ACCEPTED
    assert fewer.reasons == []
    assert fewer.token_ratio == pytest.approx(0.9)
    faster = gate(
        baseline, _card(BASELINE, run_id="cand", tokens=150.0, seconds=9.0), track="efficiency"
    )
    assert faster.decision is GateDecision.ACCEPTED
    assert faster.seconds_ratio == pytest.approx(0.9)
    short = gate(
        baseline, _card(BASELINE, run_id="cand", tokens=95.6, seconds=9.5), track="efficiency"
    )
    assert short.decision is GateDecision.REJECTED
    assert short.reasons == [GateReason.EFFICIENCY_NOT_IMPROVED]


def test_the_efficiency_track_rejects_a_regression_or_an_accuracy_loss():
    baseline = _card(BASELINE)
    traded = {"py-a": ALL, "py-b": ALL, "rb-a": NONE, "rb-b": NONE}
    regressed = gate(baseline, _card(traded, run_id="cand", tokens=50.0), track="efficiency")
    assert regressed.decision is GateDecision.REJECTED
    assert regressed.reasons == [GateReason.LANGUAGE_REGRESSED]
    lower = _card(BASELINE, run_id="cand", tokens=50.0)
    lower = lower.model_copy(update={"macro_verified_accuracy": 0.25})
    verdict = gate(baseline, lower, track="efficiency")
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.reasons == [GateReason.ACCURACY_BELOW_BASELINE]


@pytest.mark.parametrize(
    ("candidate", "baseline"),
    [
        ({"concurrency": 4}, {}),
        ({"concurrency": None}, {"concurrency": None}),
        ({"operational_episodes": 1}, {}),
        ({}, {"operational_episodes": None}),
    ],
)
def test_latency_counts_only_at_equal_concurrency_without_operational_episodes(candidate, baseline):
    def card(run_id: str, seconds: float, update: dict) -> Scorecard:
        built = _card(BASELINE, run_id=run_id, seconds=seconds, concurrency=2)
        if "concurrency" in update:
            run = built.run.model_copy(update={"concurrency": update["concurrency"]})
            built = built.model_copy(update={"run": run})
        if "operational_episodes" in update:
            built = built.model_copy(
                update={"operational_episodes": update["operational_episodes"]}
            )
        return built

    verdict = gate(card("base", 10.0, baseline), card("cand", 5.0, candidate), track="efficiency")
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.reasons == [
        GateReason.EFFICIENCY_NOT_IMPROVED,
        GateReason.LATENCY_NOT_COMPARABLE,
    ]
    assert verdict.seconds_ratio == pytest.approx(0.5)
    # Fewer tokens still accept; the uncounted latency is reported, never deciding.
    fewer = card("cand", 5.0, candidate).model_copy(update={"macro_effective_tokens": 80.0})
    accepted = gate(card("base", 10.0, baseline), fewer, track="efficiency")
    assert accepted.decision is GateDecision.ACCEPTED
    assert accepted.reasons == [GateReason.LATENCY_NOT_COMPARABLE]


@pytest.mark.parametrize("track", ["accuracy", "efficiency", "objective"])
def test_incomparable_conditions_hold_on_every_track(track):
    verdict = gate(_card(BASELINE), _card(BASELINE, run_id="cand", sliced=True), track=track)
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.reasons == [GateReason.SLICED]
    assert verdict.track == track


@pytest.mark.parametrize(
    ("track", "reason"),
    [
        ("accuracy", GateReason.ACCURACY_NOT_IMPROVED),
        ("efficiency", GateReason.EFFICIENCY_NOT_IMPROVED),
        ("objective", GateReason.OBJECTIVE_BELOW_THRESHOLD),
    ],
)
def test_a_smoke_gate_reports_but_never_rejects_on_the_track_criterion(track, reason):
    verdict = gate(_card(BASELINE), _card(BASELINE, run_id="cand"), smoke=True, track=track)
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.reasons == [reason]
    assert verdict.smoke is True
