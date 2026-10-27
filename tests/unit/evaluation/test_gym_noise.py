"""Gym noise band: the record, its refusals, and the noise-aware gate decisions."""

import pytest
from pydantic import ValidationError

from corsair.contracts import GateDecision, GateReason, NoiseBand, NoiseSpread, Scorecard
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


def _noise() -> NoiseBand:
    """Two runs of one configuration: ruby flips once, J moves, tokens differ 1.2x."""
    return _band(_run(BASELINE, "ref"), _run(NOISY, "again", tokens=120.0))


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
    baseline, candidate = _card(BASELINE), _card(NOISY, run_id="cand", tokens=120.0)
    assert gate(baseline, candidate).decision is GateDecision.REJECTED
    verdict = gate(baseline, candidate, noise=_noise())
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
    verdict = gate(_card(BASELINE), _card(NOISY, run_id="cand", tokens=125.0), noise=_noise())
    assert verdict.decision is GateDecision.REJECTED
    assert "macro_effective_tokens" not in verdict.within_noise


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
    noise = _noise()
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
        _card(BASELINE, run_id="cand", tokens=80.0),
        track="efficiency",
        noise=noise,
    )
    assert beyond.decision is GateDecision.ACCEPTED
    lower = gate(
        _card(BASELINE),
        _card(NOISY, run_id="cand", tokens=80.0),
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
    baseline, candidate = _card(BASELINE), _card(NOISY, run_id="cand", tokens=120.0)
    verdict = gate(baseline, candidate, noise=_noise())
    text = render_gate(verdict, baseline, candidate)
    assert text.startswith("## Gate: INCONCLUSIVE\n")
    assert REASON_TEXT[GateReason.WITHIN_NOISE] in text
    assert "Noise band from 2 runs: `ref`, `again`." in text
    assert "| Metric | Delta | Noise band | Within noise |" in text
    assert "| Token ratio | 1.200 | 0.833 to 1.200 | yes |" in text
    assert "| ruby verified accuracy | -0.500 | ±0.500 | yes |" in text
    assert "Within noise: objective_j, macro_verified_accuracy" in text
    plain = render_gate(gate(baseline, candidate), baseline, candidate)
    assert "Noise band" not in plain and "Within noise" not in plain


def test_the_noise_view_lists_every_metric_per_run():
    text = render_noise(_noise())
    assert text.startswith("## Noise band: 2 runs\n")
    assert "| Metric | `ref` | `again` | Mean | Half-range | Stdev | Gate band |" in text
    assert "| ruby verified accuracy | 0.500 | 0.000 | 0.250 | 0.250 | 0.354 | ±0.500 |" in text
    assert "| Macro effective tokens | 100 | 120 | 110 | 10 | 14 | 0.833x to 1.200x |" in text
