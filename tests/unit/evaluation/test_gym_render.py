"""Gym Markdown views print code-owned text only and are deterministic."""

from corsair.contracts import GateReason, RunContext, Trajectory
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.render import REASON_TEXT, render_gate, render_scorecard
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


def test_scorecard_summary_lists_languages_kinds_and_failure_stops():
    text = render_scorecard(_card("base", False))
    assert "| python |" in text
    assert "| ruby.k/1 |" in text
    assert "audit_reject 3" in text
