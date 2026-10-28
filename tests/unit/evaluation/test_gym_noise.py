"""Gym noise band: the record, its refusals, and the noise-aware gate decisions."""

import pytest
from pydantic import ValidationError

from corsair.contracts import (
    GateDecision,
    GateReason,
    NoiseBand,
    NoiseCase,
    NoiseSpread,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.gate import chain_decision, gate
from corsair.evaluation.gym.noise import (
    NoiseRefused,
    assign_bands,
    noise_band,
    noise_refusals,
    read_noise,
    spread,
    write_noise,
)
from corsair.evaluation.gym.render import REASON_TEXT, render_gate, render_noise
from tests.unit.evaluation.test_gym_gate import ALL, BASELINE, NONE, _card
from tests.unit.evaluation.test_gym_paired import BASELINE as PAIRED
from tests.unit.evaluation.test_gym_paired import _side, legacy_band

IDENTITY = {"config": ["c" * 64], "producer_prompt": ["p" * 64]}
# One target-side exception's worth of noise: ruby's only verified case flips.
NOISY = {**BASELINE, "rb-a": NONE}


def _run(verified: dict[str, list[bool]], run_id: str, **options) -> Scorecard:
    identity = options.pop("identity", IDENTITY)
    card = _card(verified, run_id=run_id, **options)
    return card.model_copy(update={"run_identity": identity})


def _band(*cards: Scorecard) -> NoiseBand:
    return noise_band(list(cards))


# The record


def test_a_spread_is_the_half_range_and_sample_deviation_of_its_values():
    values = spread([0.5, 0.25, 0.0])
    assert (values.mean, values.half_range, values.band) == (0.25, 0.25, 0.5)
    assert values.stdev == pytest.approx(0.25)
    assert values.max_ratio is None
    tokens = spread([100.0, 120.0], ratio=True)
    assert tokens.max_ratio == pytest.approx(1.2)
    assert spread([0.0, 1.0], ratio=True).max_ratio is None


def test_a_band_records_every_metric_per_run_with_its_identity():
    first, second = _run(BASELINE, "ref"), _run(NOISY, "again", tokens=120.0)
    band = _band(first, second)
    assert band.schema_version == "corsair.gym-noise/1"
    assert (band.runs, band.n_runs, band.repeats) == (["ref", "again"], 2, 3)
    assert (band.dataset_digest, band.run_identity) == (first.dataset_digest, IDENTITY)
    assert band.objective_j.values == [first.objective_j, second.objective_j]
    assert band.objective_j.band == pytest.approx(abs(first.objective_j - second.objective_j))
    assert band.macro_verified_accuracy.values == [0.5, 0.25]
    assert band.languages["ruby"].band == pytest.approx(0.5)
    assert band.languages["python"].band == 0.0
    assert band.macro_effective_tokens.max_ratio == pytest.approx(1.2)
    assert band.macro_p50_seconds is not None and band.macro_p50_seconds.band == 0.0


def test_a_band_round_trips_and_refuses_an_inconsistent_record(tmp_path):
    band = _band(_run(BASELINE, "ref"), _run(NOISY, "again"))
    path = tmp_path / "noise-tier1.json"
    write_noise(path, band)
    assert read_noise(path) == band
    with pytest.raises(ValidationError, match="follow its values"):
        NoiseSpread(values=[0.0, 1.0], mean=0.5, half_range=0.1, stdev=0.7071067811865476)
    record = band.model_dump()
    with pytest.raises(ValidationError, match="distinct runs"):
        NoiseBand.model_validate({**record, "runs": ["ref", "ref"]})
    with pytest.raises(ValidationError, match="one value per run"):
        NoiseBand.model_validate({**record, "n_runs": 3, "runs": ["ref", "again", "third"]})


# Refusals: the gate's INCOMPARABLE reasons, plus one configuration identity


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"digest": "e" * 64}, GateReason.DATASET_MISMATCH),
        ({"budgets": "b" * 64}, GateReason.BUDGETS_MISMATCH),
        ({"sliced": True}, GateReason.SLICED),
        ({"tokens": None}, GateReason.TOKENS_UNKNOWN),
        ({"identity": {"config": ["d" * 64]}}, GateReason.IDENTITY_MISMATCH),
        ({"identity": {}}, GateReason.IDENTITY_MISMATCH),
    ],
)
def test_runs_of_different_configurations_or_datasets_give_no_band(options, reason):
    cards = [_run(BASELINE, "ref"), _run(NOISY, "again", **options)]
    assert reason in noise_refusals(cards)
    with pytest.raises(NoiseRefused) as refused:
        noise_band(cards)
    assert reason in refused.value.reasons
    assert REASON_TEXT[reason] in str(refused.value)


def test_too_few_or_unequal_repeats_give_no_band():
    short = {case: flags[:2] for case, flags in BASELINE.items()}
    assert noise_refusals([_run(BASELINE, "ref"), _run(short, "short")]) == [
        GateReason.REPEATS_BELOW_MINIMUM,
        GateReason.REPEATS_MISMATCH,
    ]
    longer = {case: [*flags, flags[0]] for case, flags in BASELINE.items()}
    assert noise_refusals([_run(BASELINE, "ref"), _run(longer, "long")]) == [
        GateReason.REPEATS_MISMATCH
    ]


def test_a_band_needs_two_distinct_runs():
    with pytest.raises(ValueError, match="at least two runs"):
        noise_band([_run(BASELINE, "ref")])
    with pytest.raises(ValueError, match="more than once"):
        noise_band([_run(BASELINE, "ref"), _run(NOISY, "ref")])


def test_bands_are_assigned_to_the_gates_of_their_dataset():
    tier1 = _band(_run(BASELINE, "ref"), _run(NOISY, "again"))
    other = tier1.model_copy(update={"dataset_digest": "e" * 64})
    datasets = {"tier0": "e" * 64, "tier1": "d" * 64}
    assert assign_bands({"t1.json": tier1}, datasets) == {"tier1": ("t1.json", tier1)}
    assert assign_bands({"t1.json": tier1, "t0.json": other}, datasets) == {
        "tier0": ("t0.json", other),
        "tier1": ("t1.json", tier1),
    }
    with pytest.raises(ValueError, match="matches no gated tier"):
        assign_bands({"t1.json": tier1}, {"tier0": "e" * 64})
    with pytest.raises(ValueError, match="more than one noise band"):
        assign_bands({"a.json": tier1, "b.json": tier1}, datasets)


# Decisions with a band


def _noise(tokens: float = 130.0) -> NoiseBand:
    """Two runs of one configuration: ruby flips once, J moves, and the second run spent
    ``tokens`` against the first's 100 (by default a mean of 115, ratios to it of 0.870 to
    1.130)."""
    return _band(_run(BASELINE, "ref"), _run(NOISY, "again", tokens=tokens))


def test_without_a_band_every_decision_is_unchanged():
    for baseline, candidate in [
        (BASELINE, NOISY),
        (NOISY, BASELINE),
        (BASELINE, {**BASELINE, "py-b": ALL}),
    ]:
        before, after = _card(baseline), _card(candidate, run_id="cand")
        plain, explicit = gate(before, after), gate(before, after, noise=None)
        assert plain == explicit
        assert plain.noise is None and plain.within_noise == plain.languages_within_noise == []
        assert plain.decision is not GateDecision.INCONCLUSIVE


def test_a_regression_inside_the_band_is_inconclusive():
    # 128 tokens: 1.28x the installed baseline, 1.113x the band's mean of 115 (above the
    # 1.10 ceiling, inside the band's 1.130).
    baseline, candidate = _card(BASELINE), _card(NOISY, run_id="cand", tokens=128.0)
    assert gate(baseline, candidate).decision is GateDecision.REJECTED
    verdict = gate(baseline, candidate, noise=_noise())
    assert verdict.token_ratio == pytest.approx(1.28)
    assert verdict.token_ratio_to_band == pytest.approx(128 / 115)
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert verdict.exit_code == 3
    assert verdict.reasons == [
        GateReason.LANGUAGE_REGRESSED,
        GateReason.OBJECTIVE_BELOW_THRESHOLD,
        GateReason.TOKENS_ABOVE_CEILING,
        GateReason.WITHIN_NOISE,
    ]
    assert verdict.within_noise == [
        "objective_j",
        "macro_verified_accuracy",
        "macro_effective_tokens",
        "macro_p50_seconds",
    ]
    assert verdict.languages_within_noise == ["python", "ruby"]
    assert verdict.noise == _noise()


def test_a_regression_outside_the_band_stays_rejected():
    candidate = _card({**NOISY, "py-a": NONE}, run_id="cand")
    verdict = gate(_card(BASELINE), candidate, noise=_noise())
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.regressed_languages == ["python", "ruby"]
    # ruby's fall is noise, python's is not: one regression outside the band rejects.
    assert verdict.languages_within_noise == ["ruby"]
    assert GateReason.WITHIN_NOISE not in verdict.reasons


def test_tokens_above_the_band_reject_even_when_the_rest_is_noise():
    verdict = gate(_card(BASELINE), _card(NOISY, run_id="cand", tokens=135.0), noise=_noise())
    assert verdict.decision is GateDecision.REJECTED
    assert "macro_effective_tokens" not in verdict.within_noise


def test_the_token_ceiling_reads_the_ratio_to_the_bands_mean():
    # 112 tokens: 1.12x the installed baseline of 100 but 0.974x the band's mean of 115.
    candidate = _card(BASELINE, run_id="cand", tokens=112.0)
    assert gate(_card(BASELINE), candidate).reasons == [
        GateReason.OBJECTIVE_BELOW_THRESHOLD,
        GateReason.TOKENS_ABOVE_CEILING,
    ]
    verdict = gate(_card(BASELINE), candidate, noise=_noise())
    assert GateReason.TOKENS_ABOVE_CEILING not in verdict.reasons
    assert (verdict.token_ratio, verdict.token_ratio_to_band) == (
        pytest.approx(1.12),
        pytest.approx(112 / 115),
    )
    # p50 seconds: every run took 10 s, so the band's mean is 10 and the ratio 1.
    assert verdict.seconds_ratio == verdict.seconds_ratio_to_band == pytest.approx(1.0)
    # Without a band there is no band ratio.
    assert gate(_card(BASELINE), candidate).token_ratio_to_band is None


def test_an_objective_improvement_inside_the_band_is_not_accepted():
    baseline, candidate = _card(NOISY), _card(BASELINE, run_id="cand")
    assert gate(baseline, candidate).decision is GateDecision.ACCEPTED
    verdict = gate(baseline, candidate, noise=_noise())
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert verdict.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD, GateReason.WITHIN_NOISE]


def test_an_improvement_beyond_the_band_is_accepted():
    quiet = _band(_run(BASELINE, "ref"), _run(BASELINE, "again", tokens=105.0))
    better = _card({**BASELINE, "py-b": ALL}, run_id="cand")
    verdict = gate(_card(BASELINE), better, noise=quiet)
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.within_noise == ["macro_effective_tokens", "macro_p50_seconds"]
    accuracy = gate(_card(BASELINE), better, track="accuracy", noise=quiet)
    assert accuracy.decision is GateDecision.ACCEPTED


def test_an_accuracy_gain_inside_the_band_does_not_meet_the_accuracy_criterion():
    better = _card({**BASELINE, "py-b": ALL}, run_id="cand")
    assert gate(_card(BASELINE), better, track="accuracy").decision is GateDecision.ACCEPTED
    verdict = gate(_card(BASELINE), better, track="accuracy", noise=_noise())
    # Not a regression: the improvement criterion is unmet, as without a band.
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    target = gate(
        _card(BASELINE),
        _card({**BASELINE, "rb-b": ALL}, run_id="cand"),
        track="accuracy",
        target_language="ruby",
        noise=_noise(),
    )
    assert GateReason.ACCURACY_NOT_IMPROVED in target.reasons


def test_the_efficiency_track_needs_a_saving_beyond_the_token_band():
    # Runs of 100 and 80 tokens: a mean of 90, ratios to it of 0.889 to 1.111. 85 tokens
    # are 0.85x the installed baseline but 0.944x the band's mean; 78 are 0.867x of it.
    noise = _noise(80.0)
    inside = gate(_card(BASELINE), _card(BASELINE, run_id="cand", tokens=85.0), track="efficiency")
    assert inside.decision is GateDecision.ACCEPTED
    banded = gate(
        _card(BASELINE),
        _card(BASELINE, run_id="cand", tokens=85.0),
        track="efficiency",
        noise=noise,
    )
    assert banded.decision is GateDecision.REJECTED
    assert GateReason.EFFICIENCY_NOT_IMPROVED in banded.reasons
    beyond = gate(
        _card(BASELINE),
        _card(BASELINE, run_id="cand", tokens=78.0),
        track="efficiency",
        noise=noise,
    )
    assert beyond.decision is GateDecision.ACCEPTED
    lower = gate(
        _card(BASELINE),
        _card(NOISY, run_id="cand", tokens=78.0),
        track="efficiency",
        noise=noise,
    )
    assert lower.decision is GateDecision.INCONCLUSIVE
    assert GateReason.ACCURACY_BELOW_BASELINE in lower.reasons


@pytest.mark.parametrize(
    "update",
    [{"dataset_digest": "e" * 64}, {"budgets_digest": "b" * 64}, {"repeats": 5}],
)
def test_a_band_of_another_dataset_budgets_or_repeats_is_incomparable(update):
    noise = _noise().model_copy(update=update)
    verdict = gate(_card(BASELINE), _card(NOISY, run_id="cand"), noise=noise)
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.reasons == [GateReason.NOISE_MISMATCH]
    assert verdict.exit_code == 2


def test_a_chain_with_an_inconclusive_gate_is_inconclusive_unless_worse():
    inconclusive, accepted = GateDecision.INCONCLUSIVE, GateDecision.ACCEPTED
    assert chain_decision([accepted, inconclusive]) is inconclusive
    assert chain_decision([inconclusive, GateDecision.REJECTED]) is GateDecision.REJECTED
    assert chain_decision([inconclusive, GateDecision.INCOMPARABLE]) is (GateDecision.INCOMPARABLE)


# Single-case languages and the views


def _three_cases(verified: dict[str, list[bool]], run_id: str = "run") -> Scorecard:
    # Ruby keeps one case; the dataset's fourth case is not part of this scorecard.
    return _card(verified, run_id=run_id).model_copy(update={"sliced": False, "repeats": 3})


def test_single_case_languages_are_reported_without_changing_the_decision():
    cases = {"py-a": ALL, "py-b": NONE, "rb-a": ALL}
    baseline, candidate = _three_cases(cases), _three_cases({**cases, "rb-a": NONE}, "cand")
    verdict = gate(baseline, candidate)
    assert verdict.single_case_languages == ["ruby"]
    assert verdict.decision is GateDecision.REJECTED
    assert gate(_card(BASELINE), _card(NOISY, run_id="cand")).single_case_languages == []
    text = render_gate(verdict, baseline, candidate)
    assert "| ruby | 1.000 | 0.000 | -1.000 | yes (single case) |" in text
    assert "Single-case languages: ruby." in text


def test_the_gate_view_prints_the_band_and_what_lies_within_it():
    baseline, candidate = _card(BASELINE), _card(NOISY, run_id="cand", tokens=128.0)
    verdict = gate(baseline, candidate, noise=_noise())
    text = render_gate(verdict, baseline, candidate)
    assert text.startswith("## Gate: INCONCLUSIVE\n")
    assert REASON_TEXT[GateReason.WITHIN_NOISE] in text
    assert "Noise band from 2 runs: `ref`, `again`." in text
    assert "The band carries no pooled per-case counts" in text
    assert "| Metric | Delta | Noise band | Within noise |" in text
    assert "| Token ratio to band mean | 1.113 | 0.870 to 1.130 | yes |" in text
    assert "| Token ratio (installed reference) |  | 1.280 |  |" in text
    assert "| Token ratio (band mean) |  | 1.113 |  |" in text
    assert "| ruby verified accuracy | -0.500 | ±0.500 | yes |" in text
    assert "Within noise: objective_j, macro_verified_accuracy" in text
    plain = render_gate(gate(baseline, candidate), baseline, candidate)
    assert "Noise band" not in plain and "Within noise" not in plain
    assert "band mean" not in plain


def test_the_noise_view_lists_every_metric_per_run():
    text = render_noise(_noise())
    assert text.startswith("## Noise band: 2 runs\n")
    assert "| Metric | `ref` | `again` | Mean | Half-range | Stdev | Gate band |" in text
    assert "| ruby verified accuracy | 0.500 | 0.000 | 0.250 | 0.250 | 0.354 | ±0.500 |" in text
    assert "| Macro effective tokens | 100 | 130 | 115 | 15 | 21 | 0.870x to 1.130x |" in text


# Per-case stability: each case's majority outcome per run, from the runs' trajectories


def _case_runs() -> tuple[list[Scorecard], list[list[Trajectory]]]:
    """Two runs of one configuration: py-a falls to a majority fail once, rb-a loses one
    of its three verified repeats but keeps its majority."""
    again = {**PAIRED, "py-a": [True, False, False], "rb-a": [True, True, False]}
    (first, first_rows), (second, second_rows) = _side(PAIRED, "ref"), _side(again, "again")
    return [first, second], [first_rows, second_rows]


def test_a_band_classifies_each_case_by_its_majority_outcome_in_every_run():
    cards, rows = _case_runs()
    band = noise_band(cards, rows)
    assert band.cases_unknown is None and band.cases_unknown_runs == []
    assert band.cases is not None
    by_case = {case.case_id: case for case in band.cases}
    assert [case.case_id for case in band.cases] == sorted(PAIRED)
    # py-a pools 4 of 6: a 3-repeat majority pass with probability 20/27.
    assert by_case["py-a"] == NoiseCase(
        case_id="py-a",
        language="python",
        majority_verified=[True, False],
        verified_episodes=[3, 1],
        stability="unstable",
        episodes=6,
        verified=4,
        majority_pass_probability=20 / 27,
    )
    # rb-a kept its majority in both runs but pools 5 of 6: a majority fail with
    # probability 1 - 200/216 = 0.074, above 0.05, so it is not stable.
    assert by_case["rb-a"].stability == "unstable"
    assert by_case["rb-a"].verified_episodes == [3, 2]
    assert by_case["rb-a"].majority_pass_probability == pytest.approx(200 / 216)
    assert by_case["py-b"].stability == "stable_pass"
    assert (by_case["py-b"].verified, by_case["py-b"].episodes) == (6, 6)
    assert by_case["py-c"].stability == "stable_fail"
    assert by_case["py-c"].majority_verified == [False, False]
    assert band.pooled
    assert {case.case_id for case in band.cases if case.stability == "stable_fail"} == {
        "py-c",
        "jv-b",
    }
    # The per-language spreads are unchanged by reading the trajectories.
    assert band.languages == noise_band(cards).languages


def test_a_band_missing_a_runs_trajectories_records_no_cases_and_names_the_run():
    cards, rows = _case_runs()
    for trajectories in ([rows[0], None], [rows[0], rows[0]]):
        # Absent, or not the trajectories of that scorecard: never guessed.
        band = noise_band(cards, trajectories)
        assert band.cases is None
        assert band.cases_unknown == "trajectories_missing"
        assert band.cases_unknown_runs == ["again"]
    unread = noise_band(cards)
    assert unread.cases is None and unread.cases_unknown_runs == ["ref", "again"]


def test_a_band_written_before_per_case_stability_still_decodes_without_cases():
    cards, rows = _case_runs()
    record = noise_band(cards, rows).model_dump(mode="json")
    for field in ("cases", "cases_unknown", "cases_unknown_runs"):
        record.pop(field)
    old = NoiseBand.model_validate(record)
    assert old.schema_version == "corsair.gym-noise/1"
    assert (old.cases, old.cases_unknown, old.cases_unknown_runs) == (None, None, [])
    assert "Per-case stability: not recorded" in render_noise(old)


def test_a_case_verifying_one_episode_in_three_in_every_run_is_unstable():
    # The per-run majority failed in each run, so the earlier rule called it stable_fail;
    # pooled, 3 of 9 passes a 3-repeat majority with probability 7/27 (about 0.26).
    third = {**PAIRED, "py-c": [True, False, False]}
    sides = [_side(third, f"ref-{index}") for index in range(3)]
    band = noise_band([card for card, _ in sides], [rows for _, rows in sides])
    case = next(case for case in band.cases or [] if case.case_id == "py-c")
    assert case.majority_verified == [False, False, False]
    assert (case.verified, case.episodes) == (3, 9)
    assert case.majority_pass_probability == pytest.approx(7 / 27)
    assert case.stability == "unstable"
    assert legacy_band(band).cases is not None
    assert next(
        case for case in legacy_band(band).cases or [] if case.case_id == "py-c"
    ).stability == ("stable_fail")


def test_a_band_written_before_pooled_counts_decodes_and_says_it_carries_none():
    cards, rows = _case_runs()
    old = legacy_band(noise_band(cards, rows))
    assert not old.pooled
    assert all(case.episodes is None for case in old.cases or [])
    assert by_id(old)["rb-a"].stability == "stable_pass"
    text = render_noise(old)
    assert "The band carries no pooled counts (it was written before them)" in text
    assert "Pooled verified" not in text


def by_id(band: NoiseBand) -> dict[str, NoiseCase]:
    return {case.case_id: case for case in band.cases or []}


def test_an_incoherent_case_record_is_refused():
    cards, rows = _case_runs()
    record = noise_band(cards, rows).model_dump(mode="json")
    case = record["cases"][0]
    with pytest.raises(ValidationError, match="follows its majority-pass probability"):
        NoiseCase.model_validate({**case, "stability": "unstable"})
    with pytest.raises(ValidationError, match="all of its pooled counts or none"):
        NoiseCase.model_validate({**case, "episodes": None})
    with pytest.raises(ValidationError, match="pools its verified episodes"):
        NoiseCase.model_validate({**case, "verified": case["verified"] - 1})
    legacy = {key: value for key, value in case.items() if key not in _POOLED}
    with pytest.raises(ValidationError, match="follows its majority outcomes"):
        NoiseCase.model_validate({**legacy, "stability": "unstable"})
    with pytest.raises(ValidationError, match="every case or of none"):
        NoiseBand.model_validate({**record, "cases": [legacy, *record["cases"][1:]]})
    with pytest.raises(ValidationError, match="one majority outcome and one count per run"):
        NoiseCase.model_validate({**case, "verified_episodes": [3, 3, 3]})
    with pytest.raises(ValidationError, match="one entry per run"):
        NoiseBand.model_validate({**record, "cases": [{**case, **_three_runs(case)}]})
    with pytest.raises(ValidationError, match="either its cases or why they are unknown"):
        NoiseBand.model_validate({**record, "cases_unknown": "trajectories_missing"})
    with pytest.raises(ValidationError, match="each case once"):
        NoiseBand.model_validate({**record, "cases": [case, case]})


_POOLED = ("episodes", "verified", "majority_pass_probability")


def _three_runs(case: dict) -> dict:
    """A coherent case record of three runs, for a band of two (without pooled counts)."""
    return {
        "majority_verified": [*case["majority_verified"], True],
        "verified_episodes": [*case["verified_episodes"], 3],
        "stability": "stable_pass" if all(case["majority_verified"]) else "unstable",
        **dict.fromkeys(_POOLED),
    }


def test_the_noise_view_counts_the_classification_and_names_unstable_and_failing_cases():
    cards, rows = _case_runs()
    text = render_noise(noise_band(cards, rows))
    assert "Per-case stability: 2 stable pass, 2 stable fail, 2 unstable." in text
    assert "Each case's episodes are pooled over the runs." in text
    assert "- Unstable: `py-a`, `rb-a`" in text
    assert "- Stable fail: `jv-b`, `py-c`" in text
    header = (
        "| Case | Language | `ref` verified | `again` verified | Pooled verified "
        "| Majority-pass probability | Stability |"
    )
    assert header in text
    assert "| `py-a` | python | 3 | 1 | 4/6 (0.667) | 0.741 | unstable |" in text
    assert "| `rb-a` | ruby | 3 | 2 | 5/6 (0.833) | 0.926 | unstable |" in text
    assert "| `py-c` | python | 0 | 0 | 0/6 (0.000) | 0.000 | stable fail |" in text
    legacy = render_noise(legacy_band(noise_band(cards, rows)))
    assert "Per-case stability: 3 stable pass, 2 stable fail, 1 unstable." in legacy
    assert "- Unstable (a flip counts neither way): `py-a`" in legacy
    missing = render_noise(noise_band(cards, [rows[0], None]))
    assert "Per-case stability: unknown; no trajectories reproducing run `again`;" in missing
