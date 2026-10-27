"""Gym Markdown views print code-owned text only and are deterministic."""

from corsair.contracts import GateReason, RunContext, Trajectory
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.render import (
    REASON_TEXT,
    TRACK_TEXT,
    render_gate,
    render_scorecard,
)
from corsair.evaluation.gym.scoring import build_scorecard

CASES = {"py-a": "python.k/1", "rb-a": "ruby.k/1"}


def _card(run_id: str, verified: bool):
    rows = [
        Trajectory(
            run_id=f"{case}-{repeat}",
            case_id=case,
            repeat=repeat,
            kind=kind,
            language=kind.split(".")[0],
            status="pass" if verified or case == "py-a" else "fail",
            passed=verified or case == "py-a",
            verified=verified or case == "py-a",
            false_label=False,
            failure_stop=None if verified or case == "py-a" else "audit_reject",
            usage_known=True,
            effective_tokens=100.0,
            seconds=12.5,
            reward_verdict=1.0,
            reward=1.0,
        )
        for case, kind in CASES.items()
        for repeat in range(3)
    ]
    return build_scorecard(
        rows, run=RunContext(run_id=run_id), dataset_digest="d" * 64, cases=CASES
    )


def test_every_gate_reason_has_fixed_text():
    assert set(REASON_TEXT) == set(GateReason)


def test_gate_table_is_deterministic_and_code_owned():
    baseline, candidate = _card("base", False), _card("cand", True)
    verdict = gate(baseline, candidate)
    text = render_gate(verdict, baseline, candidate)
    assert text == render_gate(verdict, baseline, candidate)
    assert "ACCEPTED" in text
    assert "| ruby |" in text
    assert "| Objective J |" in text


def test_the_gate_view_names_its_track_and_rule():
    baseline, candidate = _card("base", False), _card("cand", True)
    objective = render_gate(gate(baseline, candidate), baseline, candidate)
    assert objective.startswith("## Gate: ACCEPTED\n")
    assert TRACK_TEXT["objective"] in objective
    verdict = gate(baseline, candidate, track="accuracy", target_language="ruby")
    text = render_gate(verdict, baseline, candidate)
    assert text.startswith("## Gate (accuracy track): ACCEPTED\n")
    assert TRACK_TEXT["accuracy"] in text
    assert "Target language: ruby." in text
    assert "| Token ratio |  | 1.000 |  |" in text
    smoke = gate(baseline, baseline, track="efficiency", smoke=True)
    view = render_gate(smoke, baseline, baseline)
    assert view.startswith("## Gate (smoke, efficiency track): ACCEPTED\n")
    assert REASON_TEXT[GateReason.EFFICIENCY_NOT_IMPROVED] in view
    assert REASON_TEXT[GateReason.LATENCY_NOT_COMPARABLE] in view


def test_scorecard_summary_lists_languages_kinds_and_failure_stops():
    text = render_scorecard(_card("base", False))
    assert "| python |" in text
    assert "| ruby.k/1 |" in text
    assert "audit_reject 3" in text


def _marked(card, capped: int):
    """A copy of ``card`` whose python episodes carry reasoning markers."""
    rows = [
        Trajectory(
            run_id=f"py-a-{repeat}",
            case_id="py-a",
            repeat=repeat,
            kind="python.k/1",
            language="python",
            status="pass",
            passed=True,
            verified=True,
            false_label=False,
            usage_known=True,
            effective_tokens=100.0,
            seconds=12.5,
            reward_verdict=1.0,
            reward=1.0,
            output_tokens=1000,
            thought_tokens=900,
            thought_share=0.9,
            output_cap=12288,
            capped_calls=1 if repeat < capped else 0,
            reasoning_cap_exhausted=repeat < capped,
        )
        for repeat in range(3)
    ]
    return build_scorecard(
        rows, run=card.run, dataset_digest="d" * 64, cases={"py-a": "python.k/1"}
    )


def test_scorecard_shows_thought_share_and_capped_episodes():
    text = render_scorecard(_marked(_card("base", True), 2))
    header = next(line for line in text.splitlines() if line.startswith("| Language |"))
    assert "| Thought share | Capped eps | Reasoning capped | Failure stops |" in header
    assert (
        "| python | 1 | 3 | 1.000 | 1.000 | 1.000 | 100 | 12.5 | 12.5 | 0 | 0.900 | 2 | 2 |" in text
    )
    assert "- Capped-call episodes: 2; reasoning cap exhausted: 2" in text
    assert "- Macro thought share: 0.900" in text


def test_scorecard_prints_unknown_markers_as_unknown():
    text = render_scorecard(_card("base", True))
    assert (
        "| ruby | 1 | 3 | 1.000 | 1.000 | 1.000 | 100 | 12.5 | 12.5 | 0 "
        "| unknown | unknown | unknown | none |" in text
    )
    assert "- Capped-call episodes: unknown; reasoning cap exhausted: unknown" in text


def test_gate_table_shows_the_capped_episode_delta_per_language():
    baseline, candidate = _marked(_card("base", True), 3), _marked(_card("cand", True), 1)
    text = render_gate(gate(baseline, candidate), baseline, candidate)
    assert "| Baseline capped eps | Candidate capped eps | Capped delta |" in text
    assert "| python | 1.000 | 1.000 | +0.000 | no | 3 | 1 | -2 |" in text
    unknown = render_gate(
        gate(_card("b", True), _card("c", True)), _card("b", True), _card("c", True)
    )
    assert "| ruby | 1.000 | 1.000 | +0.000 | no | unknown | unknown | unknown |" in unknown
