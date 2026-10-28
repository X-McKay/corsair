"""Gym gate: deciding languages (``min_cases``) and paired per-case outcomes."""

from functools import partial

import pytest

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateVerdict,
    NoiseBand,
    PairedCase,
    PairedCounts,
    RunContext,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.gate import (
    deciding_languages,
    gate,
    min_accuracy_gain,
    paired_outcomes,
    trajectories_reproduce,
)
from corsair.evaluation.gym.noise import noise_band
from corsair.evaluation.gym.render import REASON_TEXT, render_gate
from corsair.evaluation.gym.scoring import build_scorecard, case_outcomes, objective_terms

# Python decides with three cases; java (two) and ruby (one) are reported only at 3.
CASES = {
    "py-a": "python.k/1",
    "py-b": "python.k/1",
    "py-c": "python.k/1",
    "jv-a": "java.k/1",
    "jv-b": "java.k/1",
    "rb-a": "ruby.k/1",
}
ALL = [True, True, True]
NONE = [False, False, False]
BASELINE = {
    "py-a": ALL,
    "py-b": ALL,
    "py-c": NONE,
    "jv-a": ALL,
    "jv-b": NONE,
    "rb-a": ALL,
}
IDENTITY = {"config": ["c" * 64]}


def _rows(verified: dict[str, list[bool]], run_id: str, tokens: float = 100.0) -> list[Trajectory]:
    return [
        Trajectory(
            run_id=f"{run_id}-{case}-{repeat}",
            case_id=case,
            repeat=repeat,
            kind=CASES[case],
            language=CASES[case].split(".")[0],
            status="pass" if flag else "fail",
            passed=flag,
            verified=flag,
            false_label=False,
            usage_known=True,
            effective_tokens=tokens,
            seconds=10.0,
            reward_verdict=1.0 if flag else 0.0,
            reward=1.0 if flag else 0.0,
        )
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]


def _side(
    verified: dict[str, list[bool]], run_id: str, tokens: float = 100.0
) -> tuple[Scorecard, list[Trajectory]]:
    rows = _rows(verified, run_id, tokens)
    card = build_scorecard(
        rows,
        run=RunContext(run_id=run_id, concurrency=2),
        dataset_digest="d" * 64,
        cases=CASES,
        sliced=False,
    )
    # One case missing on a side keeps the dataset whole for the gate's comparability check.
    card = card.model_copy(update={"sliced": False, "repeats": 3, "run_identity": IDENTITY})
    return card, rows


def _gate(
    baseline: dict[str, list[bool]],
    candidate: dict[str, list[bool]],
    tokens: float = 100.0,
    **options,
) -> GateVerdict:
    before, before_rows = _side(baseline, "base")
    after, after_rows = _side(candidate, "cand", tokens)
    return gate(
        before,
        after,
        baseline_trajectories=before_rows,
        candidate_trajectories=after_rows,
        **options,
    )


# Deciding languages


def test_min_cases_one_leaves_every_decision_and_field_unchanged():
    for candidate in (
        {**BASELINE, "rb-a": NONE},
        {**BASELINE, "py-c": ALL},
        {**BASELINE, "jv-b": ALL, "py-a": NONE},
        BASELINE,
    ):
        (before, _), (after, _) = _side(BASELINE, "base"), _side(candidate, "cand")
        for track in ("objective", "accuracy", "efficiency"):
            plain = gate(before, after, track=track)
            explicit = gate(before, after, track=track, min_cases=1)
            assert plain == explicit
            assert plain.min_cases == 1
            assert plain.deciding_languages == plain.reported_languages == []
            assert plain.deciding_macro_verified_accuracy is None
            assert plain.deciding_worst_language is None
            assert plain.objective_j_deciding is None
            assert plain.paired is None


def test_a_record_written_before_min_cases_decodes_with_every_language_deciding():
    (before, _), (after, _) = _side(BASELINE, "base"), _side(BASELINE, "cand")
    record = gate(before, after).model_dump(mode="json")
    for field in (
        "min_cases",
        "deciding_languages",
        "reported_languages",
        "deciding_macro_verified_accuracy",
        "deciding_worst_language",
        "objective_j_deciding",
        "paired",
    ):
        record.pop(field)
    old = GateVerdict.model_validate(record)
    assert old.min_cases == 1 and old.paired is None and old.deciding_languages == []
    assert render_gate(old, before, after) == render_gate(gate(before, after), before, after)


def test_only_languages_with_enough_baseline_cases_decide():
    (card, _) = _side(BASELINE, "base")
    assert deciding_languages(card, 1) == ["java", "python", "ruby"]
    assert deciding_languages(card, 2) == ["java", "python"]
    assert deciding_languages(card, 3) == ["python"]
    verdict = _gate(BASELINE, {**BASELINE, "rb-a": NONE, "jv-a": NONE}, min_cases=3)
    assert verdict.deciding_languages == ["python"]
    assert verdict.reported_languages == ["java", "ruby"]
    assert verdict.min_cases == 3
    # Ruby and java fell but do not decide: no language regressed.
    assert verdict.regressed_languages == []
    assert GateReason.LANGUAGE_REGRESSED not in verdict.reasons
    assert verdict.language_deltas["ruby"] == -1.0
    without = _gate(BASELINE, {**BASELINE, "rb-a": NONE, "jv-a": NONE})
    assert without.regressed_languages == ["java", "ruby"]
    assert GateReason.LANGUAGE_REGRESSED in without.reasons


def test_a_deciding_language_regression_still_rejects():
    verdict = _gate(BASELINE, {**BASELINE, "py-a": NONE, "rb-a": NONE}, min_cases=3)
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.regressed_languages == ["python"]
    assert GateReason.LANGUAGE_REGRESSED in verdict.reasons


def test_deciding_metrics_recompute_macro_worst_and_j_over_the_deciding_languages():
    candidate = {**BASELINE, "py-c": ALL, "rb-a": NONE}
    verdict = _gate(BASELINE, candidate, min_cases=2)
    (before, _), (after, _) = _side(BASELINE, "base"), _side(candidate, "cand")
    expected = {
        side: objective_terms({name: card.languages[name] for name in ("java", "python")})
        for side, card in (("baseline", before), ("candidate", after))
    }
    accuracy = verdict.deciding_macro_verified_accuracy
    worst = verdict.deciding_worst_language
    objective = verdict.objective_j_deciding
    assert accuracy is not None and worst is not None and objective is not None
    assert accuracy.baseline == pytest.approx((2 / 3 + 1 / 2) / 2)
    assert accuracy.candidate == pytest.approx((1 + 1 / 2) / 2)
    assert accuracy.delta == pytest.approx(accuracy.candidate - accuracy.baseline)
    assert (worst.baseline, worst.candidate) == (0.5, 0.5)
    assert objective.baseline == pytest.approx(expected["baseline"].objective_j)
    assert objective.candidate == pytest.approx(expected["candidate"].objective_j)
    # J itself is not redefined: delta_j still covers every language.
    assert verdict.delta_j == pytest.approx(after.objective_j - before.objective_j)


def test_objective_terms_over_every_language_reproduce_the_scorecard():
    card, _ = _side(BASELINE, "base")
    terms = objective_terms(card.languages)
    assert terms.objective_j == card.objective_j
    assert terms.macro_verified_accuracy == card.macro_verified_accuracy
    assert terms.worst_language_verified_accuracy == card.worst_language_verified_accuracy
    assert terms.macro_reward == card.macro_reward
    with pytest.raises(ValueError, match="at least one language"):
        objective_terms({})


def test_the_accuracy_track_decides_on_the_deciding_languages():
    card, _ = _side(BASELINE, "base")
    assert min_accuracy_gain(card) == pytest.approx(1 / 9)
    assert min_accuracy_gain(card, ["python"]) == pytest.approx(1 / 3)
    # A single-case gain is not an accuracy improvement once ruby only reports.
    ruby_only = {**BASELINE, "rb-a": NONE}
    gained = _gate(ruby_only, BASELINE, track="accuracy")
    assert gained.decision is GateDecision.ACCEPTED
    narrowed = _gate(ruby_only, BASELINE, track="accuracy", min_cases=3)
    assert narrowed.decision is GateDecision.REJECTED
    assert narrowed.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    python = _gate(BASELINE, {**BASELINE, "py-c": ALL}, track="accuracy", min_cases=3)
    assert python.decision is GateDecision.ACCEPTED
    targeted = _gate(
        BASELINE,
        {**BASELINE, "py-c": ALL},
        track="accuracy",
        target_language="python",
        min_cases=3,
    )
    assert targeted.decision is GateDecision.ACCEPTED


def test_the_efficiency_floor_reads_the_deciding_languages():
    fell = {**BASELINE, "rb-a": NONE}
    plain = _gate(BASELINE, fell, track="efficiency")
    assert GateReason.ACCURACY_BELOW_BASELINE in plain.reasons
    narrowed = _gate(BASELINE, fell, track="efficiency", min_cases=3)
    assert GateReason.ACCURACY_BELOW_BASELINE not in narrowed.reasons
    python = _gate(BASELINE, {**BASELINE, "py-a": NONE}, track="efficiency", min_cases=3)
    assert GateReason.ACCURACY_BELOW_BASELINE in python.reasons


def test_min_cases_needs_a_deciding_language_and_a_deciding_target():
    (before, _), (after, _) = _side(BASELINE, "base"), _side(BASELINE, "cand")
    with pytest.raises(ValueError, match="no baseline language has 4 or more cases"):
        gate(before, after, min_cases=4)
    with pytest.raises(ValueError, match="ruby has fewer than 3 cases"):
        gate(before, after, track="accuracy", target_language="ruby", min_cases=3)
    with pytest.raises(ValueError, match="at least 1"):
        gate(before, after, min_cases=0)


def test_a_deciding_regression_inside_the_band_is_inconclusive():
    noisy = {**BASELINE, "py-a": NONE}
    band = noise_band([_side(BASELINE, "ref")[0], _side(noisy, "again")[0]])
    verdict = _gate(BASELINE, noisy, min_cases=3, noise=band)
    assert verdict.regressed_languages == ["python"]
    assert verdict.decision is GateDecision.INCONCLUSIVE
    assert GateReason.WITHIN_NOISE in verdict.reasons
    # Ruby falls outside its band (it never moved) but only reports at min_cases 3; the
    # accuracy floor reads python's band, the per-run mean of the deciding languages.
    cheaper = {**noisy, "rb-a": NONE}
    plain = _gate(BASELINE, cheaper, 80.0, track="efficiency", noise=band)
    assert plain.regressed_languages == ["python", "ruby"]
    assert plain.decision is GateDecision.REJECTED
    narrowed = _gate(BASELINE, cheaper, 80.0, track="efficiency", min_cases=3, noise=band)
    assert narrowed.reasons == [
        GateReason.LANGUAGE_REGRESSED,
        GateReason.ACCURACY_BELOW_BASELINE,
        GateReason.WITHIN_NOISE,
    ]
    assert narrowed.decision is GateDecision.INCONCLUSIVE


# Paired outcomes


def test_paired_outcomes_count_each_case_on_both_sides_by_its_majority():
    candidate = {
        **BASELINE,
        "py-a": [True, False, False],
        "py-c": [False, True, True],
        "jv-b": [True, True, False],
        "rb-a": NONE,
    }
    verdict = _gate(BASELINE, candidate, min_cases=3)
    paired = verdict.paired
    assert paired is not None
    assert (paired.pass_to_fail, paired.fail_to_pass) == (2, 2)
    assert (paired.stable_pass, paired.stable_fail) == (2, 0)
    assert paired.languages == {
        "java": PairedCounts(fail_to_pass=1, stable_pass=1),
        "python": PairedCounts(pass_to_fail=1, fail_to_pass=1, stable_pass=1),
        "ruby": PairedCounts(pass_to_fail=1),
    }
    assert paired.pass_to_fail_cases == [
        PairedCase(case_id="py-a", language="python"),
        PairedCase(case_id="rb-a", language="ruby", deciding=False),
    ]
    assert paired.fail_to_pass_cases == [
        PairedCase(case_id="jv-b", language="java", deciding=False),
        PairedCase(case_id="py-c", language="python"),
    ]
    assert (paired.deciding_pass_to_fail, paired.deciding_fail_to_pass) == (1, 1)
    assert paired.baseline_only == paired.candidate_only == []


def test_cases_missing_on_one_side_are_listed_and_never_paired():
    before = _rows(BASELINE, "base")
    after = _rows({case: flags for case, flags in BASELINE.items() if case != "py-a"}, "cand")
    paired = paired_outcomes(before, after, deciding=["python"])
    assert paired.baseline_only == ["py-a"]
    assert paired.candidate_only == []
    assert paired.pass_to_fail == 0
    assert (
        sum(
            counts.pass_to_fail + counts.fail_to_pass + counts.stable_pass + counts.stable_fail
            for counts in paired.languages.values()
        )
        == len(CASES) - 1
    )
    reverse = paired_outcomes(after, before, deciding=["python"])
    assert reverse.candidate_only == ["py-a"] and reverse.baseline_only == []


def test_case_outcomes_and_reproduction_check_the_per_case_record():
    card, rows = _side(BASELINE, "base")
    assert case_outcomes(rows)["py-c"] == ("python", False)
    assert case_outcomes(rows)["py-a"] == ("python", True)
    assert trajectories_reproduce(card, rows)
    other = _rows({**BASELINE, "py-c": ALL}, "other")
    assert not trajectories_reproduce(card, other)
    assert not trajectories_reproduce(card, [item for item in rows if item.case_id != "rb-a"])


def _crossed(
    baseline: dict[str, list[bool]],
    candidate: dict[str, list[bool]],
    record: dict[str, list[bool]],
    **options,
) -> GateVerdict:
    """A gate whose candidate trajectories (``record``) are not the candidate scorecard's:
    the paired check reads the per-case record, not the language summaries."""
    (before, before_rows), (after, _) = _side(baseline, "base"), _side(candidate, "cand")
    return gate(
        before,
        after,
        baseline_trajectories=before_rows,
        candidate_trajectories=_rows(record, "cand"),
        **options,
    )


def test_more_deciding_cases_falling_than_rising_rejects_an_otherwise_accepting_gate():
    better = {**BASELINE, "py-c": ALL}
    fallen = {**BASELINE, "py-a": NONE, "py-b": NONE, "py-c": ALL}
    for track in ("objective", "accuracy"):
        verdict = _crossed(BASELINE, better, fallen, track=track, min_cases=3)
        assert verdict.paired is not None
        assert (verdict.paired.deciding_pass_to_fail, verdict.paired.deciding_fail_to_pass) == (
            2,
            1,
        )
        assert verdict.decision is GateDecision.REJECTED
        assert verdict.reasons[-1] is GateReason.PAIRED_REGRESSION
    # The efficiency track decides on cost, not on a paired count.
    efficiency = _crossed(BASELINE, better, fallen, track="efficiency", min_cases=3)
    assert GateReason.PAIRED_REGRESSION not in efficiency.reasons
    # A gate that already rejects gains no paired reason.
    rejected = _crossed(BASELINE, BASELINE, fallen, min_cases=3)
    assert rejected.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD]
    # Reported-only languages never count.
    reported = _crossed(BASELINE, better, {**better, "jv-a": NONE, "rb-a": NONE}, min_cases=3)
    assert reported.decision is GateDecision.ACCEPTED
    assert reported.paired is not None and reported.paired.pass_to_fail == 2


def test_a_single_case_flip_inside_a_whole_case_band_is_noise_never_a_regression():
    flipped = {**BASELINE, "rb-a": NONE}
    band: NoiseBand = noise_band([_side(BASELINE, "ref")[0], _side(flipped, "again")[0]])
    assert band.languages["ruby"].band == 1.0
    better = {**BASELINE, "py-c": ALL}
    record = {**BASELINE, "rb-a": NONE}
    plain = _crossed(BASELINE, better, record, track="accuracy")
    assert GateReason.PAIRED_REGRESSION in plain.reasons
    # Python (the target) rose beyond its band, so the gate would otherwise accept.
    with_band = _crossed(
        BASELINE, better, record, track="accuracy", target_language="python", noise=band
    )
    assert with_band.decision is GateDecision.ACCEPTED
    assert GateReason.PAIRED_REGRESSION not in with_band.reasons
    assert with_band.paired is not None
    assert with_band.paired.pass_to_fail_cases == [
        PairedCase(case_id="rb-a", language="ruby", within_noise=True, noise_reason="language_band")
    ]
    assert with_band.paired.deciding_pass_to_fail == 0


# Per-case stability from the band: a coin-flip case's flip is noise, a stable case's is not

# Three runs of one configuration in which python's accuracy never moves (its band is
# zero) while each of its cases loses its majority once: every python case is a coin-flip.
COIN_FLIPS = (
    BASELINE,
    {**BASELINE, "py-a": NONE, "py-c": ALL},
    {**BASELINE, "py-b": NONE, "py-c": ALL},
)


def _case_band(*runs: dict[str, list[bool]], cases: bool = True) -> NoiseBand:
    sides = [_side(verified, f"ref-{index}") for index, verified in enumerate(runs)]
    trajectories = [rows for _, rows in sides] if cases else None
    return noise_band([card for card, _ in sides], trajectories)


def legacy_band(band: NoiseBand) -> NoiseBand:
    """``band`` as written before pooled counts: no pooled fields, and each case classified
    by its per-run majority outcomes."""
    record = band.model_dump(mode="json")
    for case in record["cases"] or []:
        for field in ("episodes", "verified", "majority_pass_probability"):
            case.pop(field)
        flags = case["majority_verified"]
        case["stability"] = (
            "stable_pass" if all(flags) else "unstable" if any(flags) else "stable_fail"
        )
    return NoiseBand.model_validate(record)


# Bands without pooled counts (written before them) keep the earlier per-case rule.


def test_a_flip_on_a_case_the_band_classifies_unstable_is_noise_and_counts_neither_way():
    band = legacy_band(_case_band(*COIN_FLIPS))
    assert band.languages["python"].band == 0.0
    record = {**BASELINE, "py-a": NONE, "py-c": ALL}
    paired = paired_outcomes(
        _rows(BASELINE, "base"), _rows(record, "cand"), deciding=["python"], noise=band
    )
    assert paired.pass_to_fail_cases == [
        PairedCase(
            case_id="py-a", language="python", within_noise=True, noise_reason="unstable_case"
        )
    ]
    assert paired.fail_to_pass_cases == [
        PairedCase(
            case_id="py-c", language="python", within_noise=True, noise_reason="unstable_case"
        )
    ]
    assert (paired.deciding_pass_to_fail, paired.deciding_fail_to_pass) == (0, 0)
    # Without a band, or with one that recorded no cases, both flips count as before.
    for other in (None, _case_band(*COIN_FLIPS, cases=False)):
        plain = paired_outcomes(
            _rows(BASELINE, "base"), _rows(record, "cand"), deciding=["python"], noise=other
        )
        assert (plain.deciding_pass_to_fail, plain.deciding_fail_to_pass) == (1, 1)
        assert all(case.noise_reason is None for case in plain.pass_to_fail_cases)


def test_a_flip_on_a_stable_case_stays_a_flip_and_decides_the_paired_regression():
    band = legacy_band(_case_band(*COIN_FLIPS))
    better = {**BASELINE, "py-c": ALL}
    fallen = {**BASELINE, "py-a": NONE, "py-b": NONE, "py-c": ALL}
    options = {"track": "accuracy", "target_language": "python"}
    assert _crossed(BASELINE, better, fallen, **options).reasons == [GateReason.PAIRED_REGRESSION]
    # Every python flip is a coin-flip in the band: nothing deciding fell.
    noise = _crossed(BASELINE, better, fallen, noise=band, **options)
    assert noise.decision is GateDecision.ACCEPTED
    assert noise.paired is not None
    assert (noise.paired.deciding_pass_to_fail, noise.paired.deciding_fail_to_pass) == (0, 0)
    # jv-a passes in every band run: its fall is a real flip.
    stable = _crossed(BASELINE, better, {**fallen, "jv-a": NONE}, noise=band, **options)
    assert stable.reasons == [GateReason.PAIRED_REGRESSION]
    assert stable.paired is not None
    jv_a = next(case for case in stable.paired.pass_to_fail_cases if case.case_id == "jv-a")
    assert (jv_a.within_noise, jv_a.noise_reason) == (False, None)


def test_a_coin_flip_case_in_a_whole_case_language_is_named_by_its_case():
    flipped = {**BASELINE, "rb-a": NONE}
    record = {**BASELINE, "rb-a": NONE}
    for cases, reason in ((True, "unstable_case"), (False, "language_band")):
        band = _case_band(BASELINE, flipped, cases=cases)
        band = legacy_band(band) if cases else band
        paired = paired_outcomes(
            _rows(BASELINE, "base"), _rows(record, "cand"), deciding=["ruby"], noise=band
        )
        assert [(case.within_noise, case.noise_reason) for case in paired.pass_to_fail_cases] == [
            (True, reason)
        ]


def test_a_noise_reason_needs_a_flip_within_noise_and_old_records_decode():
    with pytest.raises(ValueError, match="within noise"):
        PairedCase(case_id="py-a", language="python", noise_reason="unstable_case")
    # A flip recorded within noise before reasons existed decodes without one.
    old = PairedCase.model_validate({"case_id": "rb-a", "language": "ruby", "within_noise": True})
    assert old.noise_reason is None


def test_the_paired_view_names_why_a_flip_is_noise_and_the_bands_classification():
    band = legacy_band(_case_band(*COIN_FLIPS))
    better = {**BASELINE, "py-c": ALL}
    fallen = {**BASELINE, "py-a": NONE, "py-c": ALL, "jv-a": NONE}
    verdict = _crossed(
        BASELINE, better, fallen, track="accuracy", target_language="python", noise=band
    )
    (before, _), (after, _) = _side(BASELINE, "base"), _side(better, "cand")
    text = render_gate(verdict, before, after)
    assert "- Pass to fail: `jv-a` (java), `py-a` (python, within noise: unstable case)" in text
    assert "- Fail to pass: `py-c` (python, within noise: unstable case)" in text
    assert (
        "- Noise band per-case stability (by per-run majority, no pooled counts): "
        "2 stable pass, 1 stable fail, 3 unstable."
    ) in text
    assert "The band carries no pooled per-case counts" in text
    assert "- Unstable in the band: `py-a`, `py-b`, `py-c`" in text
    assert "- Stable fail in the band: `jv-b`" in text
    language = _crossed(
        BASELINE,
        better,
        {**BASELINE, "rb-a": NONE, "py-c": ALL},
        track="accuracy",
        target_language="python",
        noise=_case_band(BASELINE, {**BASELINE, "rb-a": NONE}, cases=False),
    )
    view = render_gate(language, before, after)
    assert "`rb-a` (ruby, within noise: language band)" in view
    assert "- Noise band per-case stability: unknown (the band recorded none)." in view


# Bands with pooled counts: Fisher's exact test on episodes decides flips and languages


def test_with_pooled_counts_a_flip_is_noise_unless_the_exact_test_separates_it():
    # COIN_FLIPS pools 6 of 9 for each python case and 9 of 9 for jv-a.
    band = _case_band(*COIN_FLIPS)
    assert band.pooled
    record = {**BASELINE, "py-a": NONE, "py-c": ALL, "jv-a": NONE}
    paired = paired_outcomes(
        _rows(BASELINE, "base"),
        _rows(record, "cand"),
        deciding=["java", "python"],
        noise=band,
    )
    # py-a: 0/3 against 6/9, p = 2/11; py-c: 3/3 against 6/9, p = 112/220 (hypergeometric
    # terms 1, 27, 108, 84 / 220, of which 1, 27 and 84 are at most 84).
    py_a = PairedCase(
        case_id="py-a",
        language="python",
        within_noise=True,
        noise_reason="episode_rate",
        reference_verified=6,
        reference_episodes=9,
        candidate_verified=0,
        candidate_episodes=3,
        p_value=2 / 11,
    )
    # jv-a: 0/3 against 9/9, p = 1/220: separated, a real flip.
    jv_a = PairedCase(
        case_id="jv-a",
        language="java",
        reference_verified=9,
        reference_episodes=9,
        candidate_verified=0,
        candidate_episodes=3,
        p_value=1 / 220,
    )
    assert paired.pass_to_fail_cases == [jv_a, py_a]
    (py_c,) = paired.fail_to_pass_cases
    assert (py_c.within_noise, py_c.noise_reason) == (True, "episode_rate")
    assert py_c.p_value == pytest.approx(112 / 220)
    assert (paired.deciding_pass_to_fail, paired.deciding_fail_to_pass) == (1, 0)


def test_a_case_verifying_one_episode_in_three_flips_within_noise_with_pooled_counts():
    # Every reference run verifies py-c once in three: a majority fail in each run.
    third = {**BASELINE, "py-c": [True, False, False]}
    band = _case_band(third, third, third)
    for record, p_value in (
        # 2/3 against 3/9: p = 414/792; 3/3 against 3/9: p = 2/11.
        ({**third, "py-c": [True, True, False]}, 414 / 792),
        ({**third, "py-c": ALL}, 2 / 11),
    ):
        paired = paired_outcomes(
            _rows(third, "base"), _rows(record, "cand"), deciding=["python"], noise=band
        )
        (flip,) = paired.fail_to_pass_cases
        assert (flip.case_id, flip.noise_reason, flip.p_value) == (
            "py-c",
            "episode_rate",
            pytest.approx(p_value),
        )
        assert paired.deciding_fail_to_pass == 0
        # The earlier rule called py-c stable_fail and counted the flip.
        legacy = paired_outcomes(
            _rows(third, "base"),
            _rows(record, "cand"),
            deciding=["python"],
            noise=legacy_band(band),
        )
        assert legacy.deciding_fail_to_pass == 1


def test_a_flip_in_a_whole_case_language_is_read_by_its_episodes_with_pooled_counts():
    # Ruby's single case flipped between the band's runs (a whole-case language band). With
    # pooled counts the flip is read by its episodes, not by the language band: 0/3 against
    # the pooled 6/9 gives p = 2/11, noise by episode rate.
    band = _case_band(BASELINE, {**BASELINE, "rb-a": NONE}, BASELINE)
    assert band.languages["ruby"].band == 1.0
    paired = paired_outcomes(
        _rows(BASELINE, "base"),
        _rows({**BASELINE, "rb-a": NONE}, "cand"),
        deciding=["ruby"],
        noise=band,
    )
    (flip,) = paired.pass_to_fail_cases
    assert (flip.noise_reason, flip.p_value) == ("episode_rate", pytest.approx(2 / 11))


def test_a_paired_case_records_all_of_its_episode_counts_or_none():
    with pytest.raises(ValueError, match="all of its episode counts"):
        PairedCase(case_id="py-a", language="python", reference_verified=3)
    with pytest.raises(ValueError, match="only by episode rate"):
        PairedCase(
            case_id="py-a",
            language="python",
            within_noise=True,
            noise_reason="unstable_case",
            reference_verified=6,
            reference_episodes=9,
            candidate_verified=0,
            candidate_episodes=3,
            p_value=2 / 11,
        )


# Three runs of the baseline configuration in which python never moves (9/9 for py-a and
# py-b, 0/9 for py-c: 18 of 27 pooled) while ruby flips once, so J has a spread.
STEADY = (BASELINE, {**BASELINE, "rb-a": NONE}, BASELINE)


def test_with_pooled_counts_a_deciding_language_regresses_only_when_the_test_separates_it():
    band = _case_band(*STEADY)
    # python 3/9 against 18/27: p = 0.122, not separated.
    fell = _gate(BASELINE, {**BASELINE, "py-a": NONE}, min_cases=3, noise=band)
    assert fell.regressed_languages == ["python"]
    rate = fell.language_rates["python"]
    assert (rate.reference_verified, rate.reference_episodes) == (18, 27)
    assert (rate.candidate_verified, rate.candidate_episodes) == (3, 9)
    assert rate.p_value == pytest.approx(0.12209495993766098)
    assert "python" in fell.languages_within_noise
    assert fell.decision is GateDecision.INCONCLUSIVE
    assert fell.reasons[0] is GateReason.LANGUAGE_REGRESSED
    assert fell.reasons[-1] is GateReason.WITHIN_NOISE
    # The band's python spread is zero: read by its spread, the same fall is a regression.
    legacy = _gate(BASELINE, {**BASELINE, "py-a": NONE}, min_cases=3, noise=legacy_band(band))
    assert legacy.language_rates == {}
    assert legacy.decision is GateDecision.REJECTED
    # python 0/9 against 18/27: p = 0.00103, separated: a regression outside noise.
    both = _gate(BASELINE, {**BASELINE, "py-a": NONE, "py-b": NONE}, min_cases=3, noise=band)
    assert both.language_rates["python"].p_value == pytest.approx(0.0010328936914031463)
    assert "python" not in both.languages_within_noise
    assert both.decision is GateDecision.REJECTED
    # Without the candidate's trajectories the language is read by its spread.
    (before, _), (after, _) = _side(BASELINE, "base"), _side({**BASELINE, "py-a": NONE}, "cand")
    assert gate(before, after, min_cases=3, noise=band).language_rates == {}


def test_with_pooled_counts_the_accuracy_criterion_needs_a_separated_rise():
    low = {**BASELINE, "py-b": NONE}
    band = _case_band(low, {**low, "rb-a": NONE}, low)
    targeted = partial(_gate, track="accuracy", target_language="python", min_cases=3)
    # python 6/9 against 9/27: p = 0.122; one case's majority rose, beyond a zero spread.
    one = {**low, "py-b": ALL}
    assert targeted(low, one, noise=legacy_band(band)).decision is GateDecision.ACCEPTED
    verdict = targeted(low, one, noise=band)
    assert verdict.language_rates["python"].p_value == pytest.approx(0.12209495993766098)
    assert verdict.reasons == [GateReason.ACCURACY_NOT_IMPROVED]
    # python 9/9 against 9/27: p = 0.00103, separated.
    two = {**low, "py-b": ALL, "py-c": ALL}
    assert targeted(low, two, noise=band).decision is GateDecision.ACCEPTED
    macro = _gate(low, two, noise=band, min_cases=3, track="accuracy")
    assert macro.decision is GateDecision.ACCEPTED


def test_the_view_prints_each_flips_episodes_and_the_language_rates():
    band = _case_band(*STEADY)
    candidate = {**BASELINE, "py-a": NONE}
    verdict = _gate(BASELINE, candidate, min_cases=3, noise=band)
    (before, _), (after, _) = _side(BASELINE, "base"), _side(candidate, "cand")
    text = render_gate(verdict, before, after)
    assert "The band carries pooled per-case counts" in text
    # py-a: 0/3 against 9/9, p = 1/220, a real flip; python as a whole is not separated.
    assert "- Pass to fail: `py-a` (python, 0/3 vs 9/9 episodes, p 0.005)" in text
    assert "| Language | Reference episodes | Candidate episodes | p | Within noise |" in text
    assert "| python | 18/27 (0.667) | 3/9 (0.333) | 0.122 | yes |" in text
    # The spread stays as information; the within-noise cell names the rule it read.
    assert "| python verified accuracy | -0.333 | ±0.000 | yes (episode rate) |" in text
    assert "- Noise band per-case stability (by pooled episodes):" in text


def test_an_incomparable_gate_reads_no_paired_outcomes():
    (before, rows), (after, after_rows) = _side(BASELINE, "base"), _side(BASELINE, "cand")
    verdict = gate(
        before,
        after.model_copy(update={"dataset_digest": "e" * 64}),
        baseline_trajectories=rows,
        candidate_trajectories=after_rows,
        min_cases=3,
    )
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.paired is None


# The view


def test_the_view_labels_reported_languages_and_prints_the_paired_table():
    candidate = {**BASELINE, "py-c": ALL, "rb-a": NONE, "jv-b": ALL}
    (before, _), (after, _) = _side(BASELINE, "base"), _side(candidate, "cand")
    verdict = _gate(BASELINE, candidate, min_cases=3)
    text = render_gate(verdict, before, after)
    assert text == render_gate(verdict, before, after)
    assert "Deciding languages (at least 3 cases): python; reported only: java, ruby." in text
    assert "| ruby | 1.000 | 0.000 | -1.000 | reported only (single case) |" in text
    assert "| java | 0.500 | 1.000 | +0.500 | reported only (2 cases) |" in text
    assert "| python | 0.667 | 1.000 | +0.333 | no |" in text
    assert "| Deciding macro verified accuracy | 0.667 | 1.000 | +0.333 |" in text
    assert "| Deciding worst language verified accuracy | 0.667 | 1.000 | +0.333 |" in text
    assert "| Deciding objective J (informational) |" in text
    header = "| Language | Pass to fail | Fail to pass | Stable pass | Stable fail | Decides |"
    assert header in text
    assert "| python | 0 | 1 | 2 | 0 | yes |" in text
    assert "| ruby | 1 | 0 | 0 | 0 | reported only (single case) |" in text
    assert "| All cases | 1 | 2 | 3 | 0 |  |" in text
    assert "- Pass to fail: `rb-a` (ruby, reported only)" in text
    assert "- Fail to pass: `jv-b` (java, reported only), `py-c` (python)" in text
    assert "- Deciding flips outside noise: 0 pass to fail, 1 fail to pass" in text
    unknown = gate(before, after, min_cases=3)
    assert "Paired per-case outcomes: unknown (no trajectories were read)." in render_gate(
        unknown, before, after
    )
    plain = render_gate(gate(before, after), before, after)
    assert "Paired" not in plain and "Deciding" not in plain and "reported only" not in plain


def test_the_view_names_the_paired_regression_and_the_deciding_band():
    assert REASON_TEXT[GateReason.PAIRED_REGRESSION].startswith("More cases of the deciding")
    noisy = {**BASELINE, "py-a": NONE}
    band = noise_band([_side(BASELINE, "ref")[0], _side(noisy, "again")[0]])
    (before, _), (after, _) = _side(BASELINE, "base"), _side(noisy, "cand")
    verdict = _gate(BASELINE, noisy, min_cases=3, noise=band)
    text = render_gate(verdict, before, after)
    assert "| Deciding macro verified accuracy | -0.333 | ±0.333 | yes |" in text
