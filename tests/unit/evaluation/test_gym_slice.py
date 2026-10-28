"""Gym gate: signal-slice screens decided on paired per-case outcomes (``slice=True``)."""

from functools import partial

import pytest

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateVerdict,
    PairedCase,
    RunContext,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.gate import gate, slice_scorecard
from corsair.evaluation.gym.noise import noise_band
from corsair.evaluation.gym.render import REASON_TEXT, render_gate
from corsair.evaluation.gym.scoring import build_scorecard, case_outcomes
from tests.unit.evaluation.test_gym_paired import (
    ALL,
    BASELINE,
    CASES,
    IDENTITY,
    NONE,
    _rows,
    _side,
    legacy_band,
)

FIVE = [True] * 5
FIVE_NONE = [False] * 5
# The target py-c (a stable baseline failure) and two python sentinels that pass.
SLICE = ("py-a", "py-b", "py-c")


def _sliced(
    verified: dict[str, list[bool]], run_id: str, tokens: float | None = 100.0
) -> tuple[Scorecard, list[Trajectory]]:
    """A sliced run as ``gym run --case`` scores it: the full dataset's cases, some run."""
    rows = _rows(verified, run_id, 100.0 if tokens is None else tokens)
    if tokens is None:
        rows = [item.model_copy(update={"effective_tokens": None}) for item in rows]
    card = build_scorecard(
        rows, run=RunContext(run_id=run_id, concurrency=2), dataset_digest="d" * 64, cases=CASES
    )
    return card.model_copy(update={"run_identity": IDENTITY}), rows


def _screen(
    candidate: dict[str, list[bool]],
    baseline: dict[str, list[bool]] = BASELINE,
    *,
    sliced_baseline: bool = False,
    tokens: float | None = 100.0,
    **options,
) -> GateVerdict:
    before, before_rows = (_sliced if sliced_baseline else _side)(baseline, "base")
    after, after_rows = _sliced(candidate, "cand", tokens)
    return gate(
        before,
        after,
        slice=True,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
        **options,
    )


def test_a_target_that_went_fail_to_pass_with_its_sentinels_holding_passes_the_screen():
    verdict = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE})
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.reasons == []
    assert verdict.slice is True
    assert verdict.slice_cases == list(SLICE)
    assert verdict.slice_repeats == 5
    paired = verdict.paired
    assert paired is not None
    assert paired.fail_to_pass_cases == [PairedCase(case_id="py-c", language="python")]
    assert (paired.stable_pass, paired.pass_to_fail, paired.stable_fail) == (2, 0, 0)
    # The baseline is restricted to the slice: nothing outside it is paired or listed.
    assert paired.baseline_only == [] and paired.candidate_only == []


def test_a_slice_whose_target_stayed_failing_is_not_improved():
    verdict = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE_NONE})
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.reasons == [GateReason.SLICE_NOT_IMPROVED]
    assert verdict.paired is not None and verdict.paired.stable_fail == 1


def test_a_sentinel_that_went_pass_to_fail_regresses_the_slice():
    verdict = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE})
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.reasons == [GateReason.SLICE_REGRESSED]
    both = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE_NONE})
    assert both.reasons == [GateReason.SLICE_REGRESSED, GateReason.SLICE_NOT_IMPROVED]


def test_an_identically_sliced_baseline_gates_and_a_mismatched_slice_is_refused():
    same = _screen(
        {"py-a": FIVE, "py-b": FIVE, "py-c": FIVE},
        {"py-a": ALL, "py-b": ALL, "py-c": NONE},
        sliced_baseline=True,
    )
    assert same.decision is GateDecision.ACCEPTED
    assert same.slice_cases == list(SLICE)
    other = _screen(
        {"py-a": FIVE, "py-b": FIVE, "py-c": FIVE},
        {"py-a": ALL, "py-c": NONE},
        sliced_baseline=True,
    )
    assert other.decision is GateDecision.INCOMPARABLE
    assert other.reasons == [GateReason.SLICE_MISMATCH]
    assert other.paired is None


def test_without_slice_a_sliced_scorecard_stays_incomparable_exactly_as_before():
    (before, before_rows) = _side(BASELINE, "base")
    after, after_rows = _sliced({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}, "cand")
    plain = gate(before, after)
    assert plain.decision is GateDecision.INCOMPARABLE
    assert plain.reasons == [GateReason.SLICED, GateReason.REPEATS_BELOW_MINIMUM]
    assert plain.slice is False and plain.slice_cases == [] and plain.slice_repeats is None
    paired = gate(
        before, after, baseline_trajectories=before_rows, candidate_trajectories=after_rows
    )
    assert paired == plain


def test_j_accuracy_tokens_and_languages_are_reported_for_the_slice_and_never_decide():
    costly = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}, tokens=1000.0)
    assert costly.decision is GateDecision.ACCEPTED
    assert costly.token_ratio == pytest.approx(10.0)
    # Over the slice only: python went from 2/3 to 3/3; the other languages are absent.
    assert costly.language_deltas == {"python": pytest.approx(1 / 3)}
    assert costly.delta_macro_verified_accuracy == pytest.approx(1 / 3)
    assert costly.regressed_languages == []
    unknown = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}, tokens=None)
    assert unknown.decision is GateDecision.ACCEPTED
    assert unknown.token_ratio is None


def test_a_slice_with_too_few_repeats_or_another_dataset_is_incomparable():
    short = _screen({"py-a": [True, True], "py-b": [True, True], "py-c": [True, True]})
    assert short.decision is GateDecision.INCOMPARABLE
    assert short.reasons == [GateReason.REPEATS_BELOW_MINIMUM]
    before, before_rows = _side(BASELINE, "base")
    after, after_rows = _sliced({"py-c": FIVE}, "cand")
    other = gate(
        before,
        after.model_copy(update={"dataset_digest": "e" * 64}),
        slice=True,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
    )
    assert other.decision is GateDecision.INCOMPARABLE
    assert other.reasons == [GateReason.DATASET_MISMATCH]


def test_a_single_case_language_flip_inside_a_whole_case_band_is_noise_in_a_slice():
    flipped = {**BASELINE, "rb-a": NONE}
    band = noise_band([_side(BASELINE, "ref")[0], _side(flipped, "again")[0]])
    assert band.languages["ruby"].band == 1.0
    candidate = {"py-c": FIVE, "rb-a": FIVE_NONE}
    plain = _screen(candidate)
    assert plain.reasons == [GateReason.SLICE_REGRESSED]
    with_band = _screen(candidate, noise=band)
    assert with_band.decision is GateDecision.ACCEPTED
    assert with_band.paired is not None
    assert with_band.paired.pass_to_fail_cases == [
        PairedCase(case_id="rb-a", language="ruby", within_noise=True, noise_reason="language_band")
    ]
    # A rise inside a whole-case band is no improvement either.
    risen = _screen({"py-a": FIVE, "rb-a": FIVE}, flipped, noise=band)
    assert risen.reasons == [GateReason.SLICE_NOT_IMPROVED]
    # The band must be the baseline's (dataset, budgets, repeats); the slice may run 5.
    other = band.model_copy(update={"repeats": 5})
    assert _screen(candidate, noise=other).reasons == [GateReason.NOISE_MISMATCH]


def _case_band(again: dict[str, list[bool]], *, cases: bool = True):
    """The band of the baseline configuration and one repeat run, with per-case stability."""
    (ref, ref_rows), (second, second_rows) = _side(BASELINE, "ref"), _side(again, "again")
    return noise_band([ref, second], [ref_rows, second_rows] if cases else None)


def test_a_slice_verdict_names_the_slice_cases_the_band_classifies_unstable():
    # A band without pooled counts: py-a lost its majority in the band's second run, a
    # coin-flip sentinel by the earlier per-run rule.
    band = legacy_band(_case_band({**BASELINE, "py-a": [True, False, False]}))
    verdict = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}, noise=band)
    assert verdict.decision is GateDecision.ACCEPTED
    assert verdict.slice_unstable_cases == ["py-a"]
    # The coin-flip sentinel falling is noise, never a slice regression.
    fallen = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE}, noise=band)
    assert fallen.decision is GateDecision.ACCEPTED
    assert fallen.paired is not None
    assert fallen.paired.pass_to_fail_cases == [
        PairedCase(
            case_id="py-a", language="python", within_noise=True, noise_reason="unstable_case"
        )
    ]
    # A stable sentinel falling still regresses the slice.
    stable = _screen({"py-a": FIVE, "py-b": FIVE_NONE, "py-c": FIVE}, noise=band)
    assert stable.reasons == [GateReason.SLICE_REGRESSED]
    # A coin-flip target rising is no improvement.
    target = legacy_band(_case_band({**BASELINE, "py-c": [True, True, False]}))
    risen = _screen({"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}, noise=target)
    assert risen.reasons == [GateReason.SLICE_NOT_IMPROVED]
    assert risen.slice_unstable_cases == ["py-c"]
    # No band, or a band that recorded no cases: nothing named, decisions as before.
    for other in (None, _case_band({**BASELINE, "py-a": [True, False, False]}, cases=False)):
        plain = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE}, noise=other)
        assert plain.slice_unstable_cases == []
        assert plain.reasons == [GateReason.SLICE_REGRESSED]


def test_with_pooled_counts_a_slice_reads_each_flip_by_fishers_exact_test():
    # The band pools py-a at 4/6 (unstable), py-b at 6/6 and py-c at 0/6.
    band = _case_band({**BASELINE, "py-a": [True, False, False]})
    assert band.pooled
    # py-a 0/5 against 4/6: p = 20/330 (terms 15, 100, 150, 60, 5 / 330), not separated;
    # py-c 5/5 against 0/6: p = 1/462, separated.
    fallen = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE}, noise=band)
    assert fallen.decision is GateDecision.ACCEPTED
    assert fallen.paired is not None
    (py_a,) = fallen.paired.pass_to_fail_cases
    assert (py_a.noise_reason, py_a.p_value) == ("episode_rate", pytest.approx(20 / 330))
    assert (py_a.candidate_verified, py_a.candidate_episodes) == (0, 5)
    assert (py_a.reference_verified, py_a.reference_episodes) == (4, 6)
    (py_c,) = fallen.paired.fail_to_pass_cases
    assert (py_c.within_noise, py_c.p_value) == (False, pytest.approx(1 / 462))
    assert fallen.slice_unstable_cases == ["py-a"]
    # py-b 0/5 against 6/6: p = 1/462, a slice regression outside noise.
    stable = _screen({"py-a": FIVE, "py-b": FIVE_NONE, "py-c": FIVE}, noise=band)
    assert stable.reasons == [GateReason.SLICE_REGRESSED]
    # A target verifying 3 of 5 against 0/6: k 3, C(11,3) = 165; P(0..3) = 20, 75, 60,
    # 10 / 165 (C(5,x) C(6,3-x)); only P(3) is at most 10, so p = 10/165 (about 0.061):
    # its majority rose, but the test does not separate it.
    partial = _screen(
        {"py-a": FIVE, "py-b": FIVE, "py-c": [True, True, True, False, False]}, noise=band
    )
    assert partial.reasons == [GateReason.SLICE_NOT_IMPROVED]
    assert partial.paired is not None
    assert partial.paired.fail_to_pass_cases[0].p_value == pytest.approx(10 / 165)


def test_the_slice_view_names_its_unstable_cases_or_says_they_are_unknown():
    candidate = {"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}
    before, before_rows = _side(BASELINE, "base")
    after, after_rows = _sliced(candidate, "cand")
    views = (
        slice_scorecard(before, before_rows, list(SLICE)),
        slice_scorecard(after, after_rows, list(SLICE)),
    )
    band = _case_band({**BASELINE, "py-a": [True, False, False]})
    text = render_gate(_screen(candidate, noise=band), *views)
    assert (
        "Unstable in the noise band (a flip there counts neither way; a sentinel there "
        "guards nothing): `py-a`."
    ) in text
    steady = render_gate(_screen(candidate, noise=_case_band(BASELINE)), *views)
    assert "Unstable in the noise band (a flip there counts neither way" in steady
    assert "guards nothing): none." in steady
    unknown = _case_band({**BASELINE, "py-a": [True, False, False]}, cases=False)
    view = render_gate(_screen(candidate, noise=unknown), *views)
    assert "Unstable in the noise band: unknown (the band recorded no per-case stability)." in view
    assert "Unstable in the noise band" not in render_gate(_screen(candidate), *views)


def test_a_slice_gate_refuses_options_that_do_not_apply_and_foreign_trajectories():
    before, before_rows = _side(BASELINE, "base")
    after, after_rows = _sliced({"py-c": FIVE}, "cand")
    with pytest.raises(ValueError, match="reads both runs' trajectories"):
        gate(before, after, slice=True)
    screen = partial(
        gate,
        before,
        after,
        slice=True,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
    )
    for refused in (
        lambda: screen(smoke=True),
        lambda: screen(track="accuracy"),
        lambda: screen(track="accuracy", target_language="python"),
        lambda: screen(min_cases=3),
    ):
        with pytest.raises(ValueError, match="--smoke, --track, --target-language and --min-cases"):
            refused()
    foreign = _rows({"py-c": FIVE_NONE}, "x")
    with pytest.raises(ValueError, match="do not reproduce"):
        gate(
            before,
            after,
            slice=True,
            baseline_trajectories=before_rows,
            candidate_trajectories=foreign,
        )


def test_the_slice_scorecard_aggregates_only_the_slice_cases():
    card, rows = _side(BASELINE, "base")
    sliced = slice_scorecard(card, rows, SLICE)
    assert set(sliced.languages) == {"python"}
    assert sliced.languages["python"].cases == 3
    assert sliced.repeats == 3
    assert sliced.sliced is True
    assert (sliced.dataset_digest, sliced.budgets_digest, sliced.run) == (
        card.dataset_digest,
        card.budgets_digest,
        card.run,
    )
    assert set(case_outcomes([item for item in rows if item.case_id in SLICE])) == set(SLICE)


# The view


def test_the_view_says_slice_screen_and_prints_the_slice_and_its_paired_table():
    candidate = {"py-a": FIVE, "py-b": FIVE, "py-c": FIVE}
    verdict = _screen(candidate)
    before, before_rows = _side(BASELINE, "base")
    after, after_rows = _sliced(candidate, "cand")
    text = render_gate(
        verdict,
        slice_scorecard(before, before_rows, verdict.slice_cases),
        slice_scorecard(after, after_rows, verdict.slice_cases),
    )
    assert text.startswith("## Gate (slice): ACCEPTED\n")
    assert "a slice screen, not an acceptance" in text
    assert "Slice: 3 cases × 5 repeats: `py-a`, `py-b`, `py-c`." in text
    assert "Objective track" not in text
    assert "| python | 0.667 | 1.000 | +0.333 | not decided (slice) |" in text
    assert "| python | 0 | 1 | 2 | 0 | yes |" in text
    assert "- Fail to pass: `py-c` (python)" in text
    assert "| Repeats | 3 | 5 |  |" in text
    rejected = _screen({"py-a": FIVE_NONE, "py-b": FIVE, "py-c": FIVE_NONE})
    view = render_gate(rejected, before, after)
    assert view.startswith("## Gate (slice): REJECTED\n")
    assert f"- {REASON_TEXT[GateReason.SLICE_REGRESSED]}" in view
    assert f"- {REASON_TEXT[GateReason.SLICE_NOT_IMPROVED]}" in view


def test_a_verdict_recorded_before_slices_decodes_as_a_full_gate_and_renders_unchanged():
    (before, _), (after, _) = _side(BASELINE, "base"), _side(BASELINE, "cand")
    record = gate(before, after).model_dump(mode="json")
    for field in ("slice", "slice_cases", "slice_repeats"):
        record.pop(field)
    old = GateVerdict.model_validate(record)
    assert old.slice is False and old.slice_cases == [] and old.slice_repeats is None
    assert render_gate(old, before, after) == render_gate(gate(before, after), before, after)
    assert "slice" not in render_gate(old, before, after).lower()
