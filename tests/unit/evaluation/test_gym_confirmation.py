"""Gym gate: the confirmation stage of an INCONCLUSIVE gate (``corsair gym verify``).

The cases a confirmation re-runs come from the gate's paired flips; the re-run is gated
as a slice screen against the reference and the band's pooled episodes, and the tier's
decision follows from the screen's separated flips and the gate's other criteria.
"""

import pytest

from corsair.contracts import (
    Confirmation,
    GateDecision,
    GateReason,
    GateVerdict,
    NoiseBand,
    Scorecard,
    Trajectory,
    VerifyRecord,
)
from corsair.evaluation.gym.gate import confirmation_cases, confirmation_decision, gate
from corsair.evaluation.gym.noise import noise_band
from tests.unit.evaluation.test_gym_paired import ALL, BASELINE, NONE, _side, legacy_band
from tests.unit.evaluation.test_gym_slice import _sliced

T, F = True, False
FIVE, FIVE_NONE = [T] * 5, [F] * 5

# py-a verifies 3, 2 and 1 of 3 in the band's runs (pooled 6/9); every other case is
# the reference's every time.
REGRESSION_RUNS = (
    BASELINE,
    {**BASELINE, "py-a": [T, T, F]},
    {**BASELINE, "py-a": [T, F, F]},
)
# py-c fails its majority in every run of the band but verifies once in three (pooled 3/9).
THIRD = {**BASELINE, "py-c": [T, F, F]}
IMPROVEMENT_RUNS = (THIRD, {**THIRD, "py-a": [T, T, F]}, {**THIRD, "py-c": [F, T, F]})


def band(*runs: dict[str, list[bool]]) -> NoiseBand:
    sides = [_side(verified, f"ref-{index}") for index, verified in enumerate(runs)]
    return noise_band([card for card, _ in sides], [rows for _, rows in sides])


def full_gate(
    runs: tuple[dict[str, list[bool]], ...],
    candidate: dict[str, list[bool]],
    *,
    tokens: float = 100.0,
    **options,
) -> tuple[GateVerdict, Scorecard, list[Trajectory], NoiseBand]:
    """The tier1 gate of ``candidate`` against the band's first run, at ``min_cases`` 3."""
    noise = band(*runs)
    before, before_rows = _side(runs[0], "ref-0")
    after, after_rows = _side(candidate, "cand", tokens)
    verdict = gate(
        before,
        after,
        noise=noise,
        min_cases=3,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
        **options,
    )
    return verdict, before, before_rows, noise


def screen(
    baseline: Scorecard,
    baseline_rows: list[Trajectory],
    noise: NoiseBand,
    rerun: dict[str, list[bool]],
) -> GateVerdict:
    card, rows = _sliced(rerun, "confirm")
    return gate(
        baseline,
        card,
        slice=True,
        noise=noise,
        baseline_trajectories=baseline_rows,
        candidate_trajectories=rows,
    )


def test_an_inconclusive_gate_confirms_exactly_its_deciding_flips_within_noise():
    # py-a 0/3 against the pooled 6/9 (p = 2/11) is a regression within noise; java's
    # jv-b (3/3 against the pooled 3/9) flips within noise too, but at min_cases 3 java is
    # reported only and its case is never re-run.
    runs = tuple({**run, "jv-b": [T, F, F]} for run in REGRESSION_RUNS)
    candidate = {**runs[0], "py-a": NONE, "jv-b": ALL}
    verdict, _, before_rows, _ = full_gate(runs, candidate)
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert verdict.paired is not None
    (python,) = verdict.paired.pass_to_fail_cases
    (java,) = verdict.paired.fail_to_pass_cases
    assert (python.case_id, python.within_noise, python.deciding) == ("py-a", True, True)
    assert (java.case_id, java.within_noise, java.deciding) == ("jv-b", True, False)
    _, after_rows = _side(candidate, "cand")
    assert confirmation_cases(verdict, before_rows, after_rows) == ["py-a"]


def test_a_regressed_languages_flips_are_confirmed_even_outside_noise():
    verdict, _, before_rows, _ = full_gate(REGRESSION_RUNS, {**BASELINE, "py-a": NONE})
    assert verdict.paired is not None
    (flip,) = verdict.paired.pass_to_fail_cases
    outside = flip.model_copy(update={"within_noise": False, "noise_reason": None, "p_value": 0.01})
    paired = verdict.paired.model_copy(update={"pass_to_fail_cases": [outside]})
    regressed = verdict.model_copy(update={"paired": paired})
    assert confirmation_cases(regressed, before_rows, []) == ["py-a"]
    # A flip outside noise in a language that did not regress is not re-run.
    steady = regressed.model_copy(update={"regressed_languages": []})
    assert confirmation_cases(steady, before_rows, []) == []


def test_without_min_cases_the_paired_flips_are_read_from_the_trajectories():
    noise = band(*REGRESSION_RUNS)
    before, before_rows = _side(BASELINE, "ref-0")
    after, after_rows = _side({**BASELINE, "py-a": NONE}, "cand")
    verdict = gate(before, after, noise=noise)
    assert verdict.paired is None and verdict.decision is GateDecision.INCONCLUSIVE
    # Every language decides at min_cases 1, so every flip within noise is re-run.
    assert confirmation_cases(verdict, before_rows, after_rows) == ["py-a"]


def test_a_confirmation_that_separates_the_regression_rejects():
    verdict, before, before_rows, noise = full_gate(REGRESSION_RUNS, {**BASELINE, "py-a": NONE})
    # 0/5 against the pooled 6/9: p = 62/2002, separated.
    rerun = screen(before, before_rows, noise, {"py-a": FIVE_NONE})
    (flip,) = rerun.paired.pass_to_fail_cases if rerun.paired else []
    assert (flip.within_noise, flip.p_value) == (False, pytest.approx(62 / 2002))
    assert confirmation_decision(verdict, rerun) == (
        GateDecision.REJECTED,
        "regression_separated",
    )


def test_a_regression_still_within_noise_needs_the_objective_gain_to_accept():
    verdict, before, before_rows, noise = full_gate(REGRESSION_RUNS, {**BASELINE, "py-a": NONE})
    assert GateReason.OBJECTIVE_BELOW_THRESHOLD in verdict.reasons
    # 1/5 against 6/9 is noise again, and J's gain was never met on the objective track.
    rerun = screen(before, before_rows, noise, {"py-a": [T, F, F, F, F]})
    assert confirmation_decision(verdict, rerun) == (
        GateDecision.INCONCLUSIVE,
        "improvement_not_separated",
    )


def test_a_regression_within_noise_on_a_met_efficiency_criterion_accepts():
    verdict, before, before_rows, noise = full_gate(
        REGRESSION_RUNS, {**BASELINE, "py-a": NONE}, tokens=80.0, track="efficiency"
    )
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert GateReason.EFFICIENCY_NOT_IMPROVED not in verdict.reasons
    rerun = screen(before, before_rows, noise, {"py-a": [T, F, F, F, F]})
    assert confirmation_decision(verdict, rerun) == (
        GateDecision.ACCEPTED,
        "no_regression_separated",
    )
    # The re-run's majority passing again is no flip at all.
    again = screen(before, before_rows, noise, {"py-a": FIVE})
    assert confirmation_decision(verdict, again)[0] is GateDecision.ACCEPTED


def test_a_confirmation_that_separates_an_improvement_meets_the_objective_criterion():
    verdict, before, before_rows, noise = full_gate(IMPROVEMENT_RUNS, {**THIRD, "py-c": ALL})
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert verdict.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD, GateReason.WITHIN_NOISE]
    _, after_rows = _side({**THIRD, "py-c": ALL}, "cand")
    assert confirmation_cases(verdict, before_rows, after_rows) == ["py-c"]
    # 5/5 against the pooled 3/9: p = 62/2002, separated.
    rerun = screen(before, before_rows, noise, {"py-c": FIVE})
    assert confirmation_decision(verdict, rerun) == (
        GateDecision.ACCEPTED,
        "improvement_separated",
    )
    weak = screen(before, before_rows, noise, {"py-c": [T, T, T, F, F]})
    assert confirmation_decision(verdict, weak) == (
        GateDecision.INCONCLUSIVE,
        "improvement_not_separated",
    )


def test_tokens_within_noise_and_an_incomparable_screen_stay_inconclusive():
    verdict, before, before_rows, noise = full_gate(
        REGRESSION_RUNS, {**BASELINE, "py-a": NONE}, tokens=80.0, track="efficiency"
    )
    tokens = verdict.model_copy(
        update={"reasons": [GateReason.TOKENS_ABOVE_CEILING, GateReason.WITHIN_NOISE]}
    )
    rerun = screen(before, before_rows, noise, {"py-a": [T, F, F, F, F]})
    assert confirmation_decision(tokens, rerun) == (
        GateDecision.INCONCLUSIVE,
        "tokens_within_noise",
    )
    short = screen(before, before_rows, noise, {"py-a": [F, F]})
    assert short.decision is GateDecision.INCOMPARABLE
    assert confirmation_decision(verdict, short) == (
        GateDecision.INCONCLUSIVE,
        "screen_incomparable",
    )
    # A separated regression still rejects whatever else the gate left within noise.
    separated = screen(before, before_rows, noise, {"py-a": FIVE_NONE})
    assert confirmation_decision(tokens, separated)[0] is GateDecision.REJECTED


def test_a_confirmation_records_its_run_or_why_it_was_skipped():
    verdict, before, before_rows, noise = full_gate(REGRESSION_RUNS, {**BASELINE, "py-a": NONE})
    rerun = screen(before, before_rows, noise, {"py-a": FIVE_NONE})
    ran = Confirmation(
        cases=["py-a"],
        repeats=5,
        run_dir="runs/confirm",
        scorecard="runs/confirm/scorecard.json",
        screen=rerun,
        decision=GateDecision.REJECTED,
        basis="regression_separated",
    )
    record = VerifyRecord(decision=GateDecision.REJECTED, confirmation={"tier1": ran})
    assert VerifyRecord.model_validate_json(record.model_dump_json()) == record
    skipped = Confirmation(skipped="band_not_pooled")
    assert (skipped.decision, skipped.cases, skipped.screen) == (
        GateDecision.INCONCLUSIVE,
        [],
        None,
    )
    with pytest.raises(ValueError, match="records no run"):
        Confirmation(skipped="no_cases", run_dir="runs/x")
    with pytest.raises(ValueError, match="leaves the tier INCONCLUSIVE"):
        Confirmation(skipped="no_cases", decision=GateDecision.ACCEPTED)
    with pytest.raises(ValueError, match="records its cases, run, screen and basis"):
        Confirmation(cases=["py-a"], repeats=5, decision=GateDecision.ACCEPTED)
    # A record written before confirmations decodes with none.
    legacy = record.model_dump(mode="json")
    legacy.pop("confirmation")
    assert VerifyRecord.model_validate(legacy).confirmation == {}
    assert verdict.noise is not None and not legacy_band(verdict.noise).pooled
