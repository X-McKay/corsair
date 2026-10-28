"""Gym noise band: resampled intervals, and the gate reading composite metrics by them."""

from functools import partial

import pytest
from pydantic import ValidationError

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateVerdict,
    NoiseBand,
    NoiseSpread,
    OperationalReason,
    ResampledInterval,
    RunContext,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.noise import (
    RESAMPLES,
    language_sets,
    noise_band,
    resampled_interval,
    resampled_runs,
)
from corsair.evaluation.gym.render import (
    BAND_REASON_TEXT,
    INTERVAL_REASON_TEXT,
    NO_INTERVALS_TEXT,
    OPERATIONAL_CASES_TEXT,
    RATE_GAIN_NOTE,
    RESAMPLE_TEXT,
    render_gate,
    render_noise,
)
from corsair.evaluation.gym.scoring import build_scorecard
from tests.unit.evaluation.test_gym_gate import ALL, BASELINE, NONE, _card
from tests.unit.evaluation.test_gym_paired import BASELINE as PAIRED
from tests.unit.evaluation.test_gym_paired import (
    CASES,
    IDENTITY,
    _rows,
    _side,
    without_intervals,
)

# Three cases of python, two of java, one of ruby (``test_gym_paired.CASES``).
ONE_IN_THREE = [True, False, False]


def _runs(
    *verified: dict[str, list[bool]],
) -> tuple[list[Scorecard], list[list[Trajectory]]]:
    sides = [_side(run, f"ref-{index}") for index, run in enumerate(verified)]
    return [card for card, _ in sides], [rows for _, rows in sides]


def _resampled(*verified: dict[str, list[bool]], **options) -> NoiseBand:
    cards, rows = _runs(*verified)
    return noise_band(cards, rows, **options)


# The band's intervals


def test_a_band_with_trajectories_records_an_interval_on_every_composite_metric():
    band = _resampled(PAIRED, {**PAIRED, "py-c": ONE_IN_THREE}, PAIRED)
    assert (band.resamples, band.seed) == (RESAMPLES, 0) == (2000, 0)
    assert band.resampled
    spreads: list[NoiseSpread | None] = [band.objective_j, band.macro_verified_accuracy]
    spreads += [band.macro_effective_tokens, band.macro_p50_seconds, *band.languages.values()]
    for spread in spreads:
        assert spread is not None and spread.interval is not None
        assert spread.interval.low <= spread.interval.high
    # One set per distinct case count: every language (1), java and python (2), python (3).
    assert [(item.min_cases, item.languages) for item in band.language_sets] == [
        (1, ["java", "python", "ruby"]),
        (2, ["java", "python"]),
        (3, ["python"]),
    ]
    every = band.language_set(["ruby", "python", "java"])
    assert every is not None and every.min_cases == 1
    assert band.language_set(["ruby"]) is None


def test_resampling_is_deterministic_under_a_seed():
    runs = (PAIRED, {**PAIRED, "py-c": ONE_IN_THREE, "jv-b": ONE_IN_THREE}, PAIRED)
    assert _resampled(*runs) == _resampled(*runs)
    other = _resampled(*runs, seed=7)
    assert other.seed == 7
    cards, rows = _runs(*runs)
    first = resampled_runs(cards[0], rows, resamples=50, seed=3)
    assert first == resampled_runs(cards[0], rows, resamples=50, seed=3)
    assert first != resampled_runs(cards[0], rows, resamples=50, seed=4)
    # Each synthetic run scores every case at the band's repeats, as a run does.
    assert {card.repeats for card in first} == {3}
    assert all(not card.sliced for card in first)


def _cpu_side(run_id: str, cpu: dict[str, float]) -> tuple[Scorecard, list[Trajectory]]:
    """``_side(PAIRED, run_id)`` whose episodes of each case took ``cpu[case]`` sandbox CPU
    seconds (python's three cases, otherwise one figure for every case)."""
    card, rows = _side(PAIRED, run_id)
    rows = [
        item.model_copy(update={"sandbox_cpu_seconds": cpu.get(item.case_id, cpu["*"])})
        for item in rows
    ]
    rescored = build_scorecard(rows, run=card.run, dataset_digest=card.dataset_digest, cases=CASES)
    figures = {
        "macro_sandbox_cpu_seconds": rescored.macro_sandbox_cpu_seconds,
        "sandbox_cpu_unknown": rescored.sandbox_cpu_unknown,
    }
    return card.model_copy(update=figures), rows


def test_a_resampled_band_records_an_information_interval_on_sandbox_cpu_seconds():
    sides = [_cpu_side("ref-0", {"*": 1.0}), _cpu_side("ref-1", {"*": 1.0, "py-a": 4.0})]
    band = noise_band([card for card, _ in sides], [rows for _, rows in sides])
    cpu = band.macro_sandbox_cpu_seconds
    assert cpu is not None and cpu.interval is not None
    # Python's mean moves by one case of three: (4 - 1) / 3 = 1, so the macro over three
    # languages by 1/3; the resampled runs draw py-a at 1 or 4 seconds per episode.
    assert cpu.values == pytest.approx([1.0, 4 / 3])
    assert 1.0 <= cpu.interval.low <= cpu.interval.high <= 4 / 3
    assert band.sandbox_cpu_unknown == [0, 0]
    # The record decodes without the interval as a band written before intervals would.
    assert without_intervals(band).macro_sandbox_cpu_seconds == cpu.model_copy(
        update={"interval": None}
    )


def test_a_case_verifying_every_episode_gives_a_degenerate_interval():
    # Every case verifies all or none of its episodes in every run: no draw can differ.
    band = _resampled(PAIRED, PAIRED)
    ruby = band.languages["ruby"].interval
    assert ruby == ResampledInterval(low=1.0, high=1.0, mean=1.0)
    python = band.languages["python"].interval
    assert python is not None
    assert python.low == python.high == pytest.approx(2 / 3)
    j = band.objective_j.interval
    assert j is not None and j.low == j.high == pytest.approx(band.objective_j.mean)


def test_a_coin_flip_case_widens_the_interval_where_the_half_range_sees_nothing():
    # py-c verifies one episode in three in every run: python's accuracy is 2/3 in each
    # run (half-range 0), but a run at that rate passes py-c's majority with probability
    # 7/27, so python reaches 1.0 in some synthetic runs.
    coin = {**PAIRED, "py-c": ONE_IN_THREE}
    band = _resampled(coin, coin, coin)
    python = band.languages["python"]
    assert python.half_range == 0.0
    assert python.interval is not None
    assert python.interval.low == pytest.approx(2 / 3)
    assert python.interval.high == pytest.approx(1.0)
    assert python.interval.mean == pytest.approx(2 / 3 + 7 / 81, abs=0.02)


def test_an_interval_spans_the_nearest_rank_percentiles():
    values = [float(value) for value in range(1, 201)]
    assert resampled_interval(values) == ResampledInterval(low=5.0, high=195.0, mean=100.5)
    assert resampled_interval([1.0, None]) is None
    assert resampled_interval([]) is None


def test_language_sets_follow_each_distinct_case_count():
    card, _ = _side(PAIRED, "ref")
    assert language_sets(card) == [["java", "python", "ruby"], ["java", "python"], ["python"]]


def test_a_band_without_trajectories_records_no_interval():
    cards, rows = _runs(PAIRED, PAIRED)
    for band in (noise_band(cards), noise_band(cards, [rows[0], None])):
        assert (band.resamples, band.seed, band.language_sets) == (None, None, [])
        assert not band.resampled
        assert band.objective_j.interval is None
        assert all(spread.interval is None for spread in band.languages.values())


def test_an_incoherent_interval_record_is_refused():
    band = _resampled(PAIRED, {**PAIRED, "py-c": ONE_IN_THREE})
    record = band.model_dump(mode="json")
    with pytest.raises(ValidationError, match="low end is at most its high end"):
        ResampledInterval(low=0.6, high=0.5, mean=0.55)
    with pytest.raises(ValidationError, match="resample count and seed together"):
        NoiseBand.model_validate({**record, "seed": None})
    missing = {**record, "objective_j": {**record["objective_j"], "interval": None}}
    with pytest.raises(ValidationError, match="interval on J, macro and every language"):
        NoiseBand.model_validate(missing)
    bare = without_intervals(band).model_dump(mode="json")
    with pytest.raises(ValidationError, match="without resamples records no interval"):
        NoiseBand.model_validate({**bare, "objective_j": record["objective_j"]})
    with pytest.raises(ValidationError, match="without resamples records no interval"):
        NoiseBand.model_validate({**bare, "language_sets": record["language_sets"]})
    # A skewed metric's mean may lie outside its percentiles.
    assert ResampledInterval(low=0.0, high=0.0, mean=0.01).mean == 0.01


def test_a_band_written_before_intervals_decodes_without_them():
    band = without_intervals(_resampled(PAIRED, {**PAIRED, "py-c": ONE_IN_THREE}))
    assert not band.resampled and band.language_sets == []
    assert band.cases is not None and band.pooled


# The gate's interval rules, on hand-built bands


def _quiet(**intervals: tuple[float, float]) -> NoiseBand:
    """Three identical runs of ``test_gym_gate.BASELINE`` (every spread zero) with
    resampled intervals set by hand: each named metric (``objective_j``,
    ``macro_verified_accuracy`` or a language) gets ``(low, high)``, every other one a
    degenerate interval at its mean."""
    cards = [
        _card(BASELINE, run_id=run).model_copy(update={"run_identity": IDENTITY})
        for run in ("one", "two", "three")
    ]
    record = noise_band(cards).model_dump(mode="json")

    def interval(name: str, spread: dict) -> dict:
        low, high = intervals.get(name, (spread["mean"], spread["mean"]))
        return {**spread, "interval": {"low": low, "high": high, "mean": spread["mean"]}}

    for name in ("objective_j", "macro_verified_accuracy", "macro_effective_tokens"):
        record[name] = interval(name, record[name])
    record["macro_p50_seconds"] = interval("macro_p50_seconds", record["macro_p50_seconds"])
    record["languages"] = {
        name: interval(name, spread) for name, spread in record["languages"].items()
    }
    worst = intervals.get("worst", (0.5, 0.5))
    record["language_sets"] = [
        {
            "min_cases": 2,
            "languages": ["python", "ruby"],
            "macro_verified_accuracy": record["macro_verified_accuracy"]["interval"],
            "worst_language_verified_accuracy": {"low": worst[0], "high": worst[1], "mean": 0.5},
        }
    ]
    return NoiseBand.model_validate({**record, "resamples": 2000, "seed": 0})


BETTER = {**BASELINE, "py-b": ALL}
# ruby loses its verified case: 0.0 against the band's 0.5; J 0.25 against 0.75.
FALLEN = {**BASELINE, "rb-a": NONE}


def test_an_objective_gain_must_rise_above_the_intervals_high_end():
    # J 0.75 to 1.0: beyond the half-range (zero) of three identical runs.
    baseline, candidate = _card(BASELINE), _card(BETTER, run_id="cand")
    assert gate(baseline, candidate, noise=without_intervals(_quiet())).decision is (
        GateDecision.ACCEPTED
    )
    inside = gate(baseline, candidate, noise=_quiet(objective_j=(0.5, 1.1)))
    assert inside.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD, GateReason.WITHIN_NOISE]
    assert inside.decision is GateDecision.INCONCLUSIVE
    assert inside.noise_rules["objective_j"] == "interval"
    assert "objective_j" in inside.within_noise
    beyond = gate(baseline, candidate, noise=_quiet(objective_j=(0.5, 0.95)))
    assert beyond.decision is GateDecision.ACCEPTED
    assert "objective_j" not in beyond.within_noise
    # The delta reported is still from the band's mean.
    assert beyond.delta_j_to_band == pytest.approx(0.25)


def test_a_language_fall_is_outside_noise_only_below_the_intervals_low_end():
    baseline, candidate = _card(BASELINE), _card(FALLEN, run_id="cand")
    wide = {"objective_j": (0.2, 1.0)}
    assert gate(baseline, candidate, noise=without_intervals(_quiet(**wide))).decision is (
        GateDecision.REJECTED
    )
    inside = gate(baseline, candidate, noise=_quiet(ruby=(0.0, 1.0), **wide))
    assert inside.regressed_languages == ["ruby"]
    assert inside.reasons == [
        GateReason.LANGUAGE_REGRESSED,
        GateReason.OBJECTIVE_BELOW_THRESHOLD,
        GateReason.WITHIN_NOISE,
    ]
    assert inside.decision is GateDecision.INCONCLUSIVE
    assert inside.languages_within_noise == ["python", "ruby"]
    below = gate(baseline, candidate, noise=_quiet(ruby=(0.5, 1.0), **wide))
    assert below.decision is GateDecision.REJECTED
    assert below.languages_within_noise == ["python"]
    assert GateReason.WITHIN_NOISE not in below.reasons


def test_the_accuracy_steps_must_rise_above_the_intervals_high_end():
    # Macro 0.5 to 0.75 and python 0.5 to 1.0: each one step from the band's mean.
    baseline, candidate = _card(BASELINE), _card(BETTER, run_id="cand")
    for target in (None, "python"):
        verdict = gate(
            baseline,
            candidate,
            track="accuracy",
            target_language=target,
            noise=_quiet(macro_verified_accuracy=(0.25, 0.8), python=(0.0, 1.0)),
        )
        assert verdict.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
        assert verdict.decision is GateDecision.REJECTED
    macro = _quiet(macro_verified_accuracy=(0.25, 0.7), python=(0.0, 1.0))
    assert gate(baseline, candidate, track="accuracy", noise=macro).decision is (
        GateDecision.ACCEPTED
    )
    target = _quiet(macro_verified_accuracy=(0.25, 0.8), python=(0.0, 0.9))
    accepted = gate(baseline, candidate, track="accuracy", target_language="python", noise=target)
    assert accepted.decision is GateDecision.ACCEPTED
    assert accepted.language_noise_rules == {"python": "interval", "ruby": "interval"}


def test_the_efficiency_floor_falls_outside_noise_only_below_the_low_end():
    # 78 tokens against the band's 100: a saving beyond its (zero) spread. Macro 0.25
    # against the band's 0.5, with ruby's fall inside its interval.
    baseline = _card(BASELINE)
    candidate = _card(FALLEN, run_id="cand", tokens=78.0)
    inside = gate(
        baseline,
        candidate,
        track="efficiency",
        noise=_quiet(macro_verified_accuracy=(0.25, 0.75), ruby=(0.0, 1.0)),
    )
    assert inside.reasons == [
        GateReason.LANGUAGE_REGRESSED,
        GateReason.ACCURACY_BELOW_BASELINE,
        GateReason.WITHIN_NOISE,
    ]
    assert inside.decision is GateDecision.INCONCLUSIVE
    below = gate(
        baseline,
        candidate,
        track="efficiency",
        noise=_quiet(macro_verified_accuracy=(0.3, 0.75), ruby=(0.0, 1.0)),
    )
    assert below.decision is GateDecision.REJECTED


def _deciding_band(low: float, high: float) -> NoiseBand:
    """Three identical runs of ``test_gym_paired.BASELINE`` whose python-only set (three
    cases) has the macro interval ``(low, high)``; every other interval is degenerate."""
    cards = [_side(PAIRED, run)[0] for run in ("one", "two", "three")]
    record = noise_band(cards).model_dump(mode="json")
    for spread in [
        record["objective_j"],
        record["macro_verified_accuracy"],
        record["macro_effective_tokens"],
        record["macro_p50_seconds"],
        *record["languages"].values(),
    ]:
        spread["interval"] = {"low": spread["mean"], "high": spread["mean"], "mean": spread["mean"]}
    python = {"low": low, "high": high, "mean": 2 / 3}
    record["language_sets"] = [
        {
            "min_cases": 3,
            "languages": ["python"],
            "macro_verified_accuracy": python,
            "worst_language_verified_accuracy": python,
        }
    ]
    return NoiseBand.model_validate({**record, "resamples": 2000, "seed": 0})


def test_with_min_cases_the_deciding_macro_reads_its_language_sets_interval():
    # Python (the one deciding language at 3) from 2/3 to 1.0: one step.
    baseline, candidate = _side(PAIRED, "base")[0], _side({**PAIRED, "py-c": ALL}, "cand")[0]
    accuracy = partial(gate, baseline, candidate, track="accuracy", min_cases=3)
    inside = accuracy(noise=_deciding_band(0.3, 1.0))
    assert inside.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    assert inside.noise_rules["deciding_macro_verified_accuracy"] == "interval"
    assert inside.noise_rules["deciding_worst_language"] == "interval"
    beyond = accuracy(noise=_deciding_band(0.3, 0.9))
    assert beyond.decision is GateDecision.ACCEPTED
    # A band without the deciding set's interval reads it by the half-range.
    record = _deciding_band(0.3, 0.9).model_dump(mode="json")
    record["language_sets"] = []
    unset = accuracy(noise=NoiseBand.model_validate(record))
    assert unset.noise_rules["deciding_macro_verified_accuracy"] == "half_range"


def test_the_verdict_records_which_rule_read_each_metric_and_old_records_decode():
    baseline, candidate = _card(BASELINE), _card(BETTER, run_id="cand")
    intervals = gate(baseline, candidate, noise=_quiet())
    assert intervals.noise_rules == {
        "objective_j": "interval",
        "macro_verified_accuracy": "interval",
        "worst_language_verified_accuracy": "interval",
        "macro_effective_tokens": "band_ratio",
        "macro_p50_seconds": "band_ratio",
    }
    half = gate(baseline, candidate, noise=without_intervals(_quiet()))
    assert half.noise_rules["objective_j"] == "half_range"
    assert half.language_noise_rules == {"python": "half_range", "ruby": "half_range"}
    plain = gate(baseline, candidate)
    assert plain.noise_rules == plain.language_noise_rules == {}
    record = intervals.model_dump(mode="json")
    for field in ("noise_rules", "language_noise_rules"):
        record.pop(field)
    old = GateVerdict.model_validate(record)
    assert old.noise_rules == old.language_noise_rules == {}


def test_a_language_read_by_its_episodes_records_the_episode_rate_rule():
    band = _resampled(PAIRED, PAIRED, PAIRED)
    (before, before_rows), (after, after_rows) = _side(PAIRED, "base"), _side(PAIRED, "cand")
    verdict = gate(
        before,
        after,
        noise=band,
        min_cases=3,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
    )
    assert verdict.language_noise_rules == {
        "java": "interval",
        "python": "episode_rate",
        "ruby": "interval",
    }
    # On the accuracy track the macro gain is then read by the languages' episodes, and
    # its reason sentence says so beside the (informational) interval.
    accuracy = gate(
        before,
        after,
        noise=band,
        min_cases=3,
        track="accuracy",
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
    )
    assert accuracy.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    text = render_gate(accuracy, before, after)
    assert (
        "deciding macro verified accuracy 0.667 (band mean 0.667, resampled interval 0.667 "
        f"to 0.667, {RATE_GAIN_NOTE})"
    ) in text


# The views


def test_the_gate_view_prints_the_intervals_the_candidates_values_and_the_rule():
    baseline, candidate = _card(BASELINE), _card(BETTER, run_id="cand")
    verdict = gate(baseline, candidate, noise=_quiet(objective_j=(0.5, 1.1)))
    text = render_gate(verdict, baseline, candidate)
    assert "The band carries resampled intervals:" in text
    assert "Resampled from 2000 synthetic runs, seed 0." in text
    header = (
        "| Metric | Candidate | Delta (band mean) | Resampled interval | Half-range band | Rule "
        "| Within noise |"
    )
    assert header in text
    assert "| Objective J | 1.000 | +0.250 | 0.500 to 1.100 | ±0.000 | interval | yes |" in text
    assert (
        "| Macro verified accuracy | 0.750 | +0.250 | 0.500 to 0.500 | ±0.000 | interval | no |"
    ) in text
    assert (
        "| Worst language verified accuracy (reported) | 0.500 | +0.000 | 0.500 to 0.500 "
        "| ±0.000 | interval | yes |"
    ) in text
    assert "| Token ratio to band mean | 1.000 |  | 1.000 to 1.000 (information) |" in text
    assert "| python verified accuracy | 1.000 | +0.500 | 0.500 to 0.500 | ±0.000 |" in text
    figures = (
        "Candidate against the band: J 1.000 (band mean 0.750, resampled interval 0.500 to 1.100)."
    )
    objective = INTERVAL_REASON_TEXT[GateReason.OBJECTIVE_BELOW_THRESHOLD]
    assert f"- {objective} {figures}" in text
    assert f"- {INTERVAL_REASON_TEXT[GateReason.WITHIN_NOISE]} {figures}" in text
    assert BAND_REASON_TEXT[GateReason.OBJECTIVE_BELOW_THRESHOLD] not in text
    assert NO_INTERVALS_TEXT not in text


def test_the_reason_sentences_name_each_regressed_language_and_the_accuracy_decided_on():
    baseline, candidate = _card(BASELINE), _card(FALLEN, run_id="cand", tokens=78.0)
    noise = _quiet(macro_verified_accuracy=(0.25, 0.75), ruby=(0.0, 1.0))
    verdict = gate(baseline, candidate, track="efficiency", noise=noise)
    text = render_gate(verdict, baseline, candidate)
    ruby = "ruby 0.000 (band mean 0.500, resampled interval 0.000 to 1.000)"
    macro = "macro verified accuracy 0.250 (band mean 0.500, resampled interval 0.250 to 0.750)"
    regressed = INTERVAL_REASON_TEXT[GateReason.LANGUAGE_REGRESSED]
    assert f"- {regressed} Candidate against the band: {ruby}." in text
    floor = INTERVAL_REASON_TEXT[GateReason.ACCURACY_BELOW_BASELINE]
    assert f"- {floor} Candidate against the band: {macro}." in text
    within = INTERVAL_REASON_TEXT[GateReason.WITHIN_NOISE]
    assert f"- {within} Candidate against the band: {macro}; {ruby}." in text
    accuracy = gate(
        baseline,
        _card(BETTER, run_id="cand"),
        track="accuracy",
        target_language="python",
        noise=_quiet(macro_verified_accuracy=(0.25, 0.8), python=(0.0, 1.0)),
    )
    view = render_gate(accuracy, baseline, _card(BETTER, run_id="cand"))
    assert (
        "Candidate against the band: macro verified accuracy 0.750 (band mean 0.500, "
        "resampled interval 0.250 to 0.800); python 1.000 (band mean 0.500, resampled "
        "interval 0.000 to 1.000)."
    ) in view


def test_a_gate_view_against_a_band_without_intervals_says_so():
    baseline, candidate = _card(BASELINE), _card(FALLEN, run_id="cand")
    verdict = gate(baseline, candidate, noise=without_intervals(_quiet()))
    text = render_gate(verdict, baseline, candidate)
    assert NO_INTERVALS_TEXT in text
    assert "| Metric | Delta | Noise band | Within noise |" in text
    assert "Resampled interval" not in text
    for reason in verdict.reasons:
        if reason in BAND_REASON_TEXT:
            assert f"- {BAND_REASON_TEXT[reason]}" in text


def test_the_noise_view_prints_each_interval_and_the_language_sets():
    band = _resampled(PAIRED, PAIRED)
    text = render_noise(band)
    assert (
        "| Metric | `ref-0` | `ref-1` | Mean | Half-range | Stdev | Gate band | Resampled "
        "interval | Resampled mean |"
    ) in text
    assert "| ruby verified accuracy | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | ±0.000 | " in text
    assert "| 1.000 to 1.000 | 1.000 |" in text
    assert f"Resampled intervals: 2000 synthetic runs, seed 0. {RESAMPLE_TEXT}" in text
    assert "| python (at least 3 cases) | 0.667 to 0.667 | 0.667 | 0.667 to 0.667 | 0.667 |" in text
    old = render_noise(without_intervals(band))
    assert NO_INTERVALS_TEXT in old
    assert "Resampled interval" not in old


# Operational episodes: a harness fault, left out of the pooled counts and the resampling


def _operational_side(
    verified: dict[str, list[bool]], run_id: str, operational: set[str]
) -> tuple[Scorecard, list[Trajectory]]:
    """``_side`` with every episode of the ``operational`` cases lost to a heartbeat
    timeout: scored as a failure, flagged operational."""
    rows = [
        item.model_copy(
            update={
                "verified": False,
                "passed": False,
                "status": "fail",
                "reward": -0.5,
                "operational": True,
                "operational_reason": OperationalReason.HEARTBEAT_TIMEOUT,
            }
        )
        if item.case_id in operational
        else item
        for item in _rows(verified, run_id)
    ]
    card = build_scorecard(
        rows, run=RunContext(run_id=run_id, concurrency=2), dataset_digest="d" * 64, cases=CASES
    )
    return card.model_copy(update={"repeats": 3, "run_identity": IDENTITY}), rows


def _operational_runs(*operational: set[str]) -> tuple[list[Scorecard], list[list[Trajectory]]]:
    sides = [
        _operational_side(PAIRED, f"ref-{index}", cases) for index, cases in enumerate(operational)
    ]
    return [card for card, _ in sides], [rows for _, rows in sides]


def test_operational_episodes_are_left_out_of_the_pooled_counts_and_the_resampling():
    cards, rows = _operational_runs(set(), {"py-a"})
    band = noise_band(cards, rows)
    assert band.operational_episodes == [0, 3]
    assert band.operational_cases == []
    case = next(case for case in band.cases or [] if case.case_id == "py-a")
    # Scored as a majority fail in the second run, but its pooled rate is 3 of 3.
    assert case.majority_verified == [True, False]
    assert (case.verified, case.episodes, case.operational_excluded) == (3, 3, 3)
    assert case.stability == "stable_pass"
    # The run values keep the fault; the interval does not draw it.
    assert band.languages["python"].values == pytest.approx([2 / 3, 1 / 3])
    python = band.languages["python"].interval
    assert python is not None and python.low == python.high == pytest.approx(2 / 3)
    synthetic = resampled_runs(cards[0], rows, resamples=20, seed=0)
    assert all(run.operational_episodes == 0 for run in synthetic)
    text = render_noise(band)
    assert "- Operational episodes per run: `ref-0` 0, `ref-1` 3;" in text
    assert "| `py-a` | python | 3 | 0 | 3/3 (1.000) | 1.000 | stable pass | 3 |" in text


def test_a_case_operational_in_every_run_has_no_rate_and_the_band_no_interval():
    cards, rows = _operational_runs({"rb-a"}, {"rb-a"})
    band = noise_band(cards, rows)
    assert band.operational_cases == ["rb-a"]
    assert "rb-a" not in {case.case_id for case in band.cases or []}
    assert (band.resamples, band.language_sets) == (None, [])
    with pytest.raises(ValueError, match="no non-operational episode to draw for rb-a"):
        resampled_runs(cards[0], rows, resamples=1, seed=0)
    text = render_noise(band)
    assert f"- {OPERATIONAL_CASES_TEXT}: `rb-a`" in text
    assert NO_INTERVALS_TEXT in text


def test_operational_records_are_coherent_and_older_bands_decode():
    cards, rows = _operational_runs(set(), {"py-a"})
    record = noise_band(cards, rows).model_dump(mode="json")
    with pytest.raises(ValidationError, match="operational episodes of every run"):
        NoiseBand.model_validate({**record, "operational_episodes": [0]})
    with pytest.raises(ValidationError, match="operational-only case has no pooled record"):
        NoiseBand.model_validate({**record, "operational_cases": ["py-a"]})
    with pytest.raises(ValidationError, match="operational-only case records no interval"):
        NoiseBand.model_validate({**record, "operational_cases": ["zz-a"]})
    record.pop("operational_episodes")
    record.pop("operational_cases")
    for case in record["cases"]:
        case.pop("operational_excluded")
    old = NoiseBand.model_validate(record)
    assert old.operational_episodes == [] and old.operational_cases == []
    assert all(case.operational_excluded == 0 for case in old.cases or [])
    assert "Operational episodes per run" not in render_noise(old)
