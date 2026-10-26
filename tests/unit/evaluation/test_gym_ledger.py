"""Gym ledger: append-only JSONL and deterministic LEDGER.md rendering."""

from datetime import date
from pathlib import Path

import pytest

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateVerdict,
    RunContext,
    Scorecard,
    Trajectory,
)
from corsair.evaluation.gym.ledger import (
    append_ledger,
    build_ledger_row,
    ledger_header,
    read_ledger,
    render_ledger,
    render_ledger_file,
)
from corsair.evaluation.gym.scoring import build_scorecard

ROOT = Path(__file__).resolve().parents[3]


def _scorecard() -> Scorecard:
    row = Trajectory(
        run_id="r",
        case_id="case",
        repeat=0,
        kind="python.k/1",
        language="python",
        status="pass",
        passed=True,
        verified=True,
        false_label=False,
        usage_known=True,
        effective_tokens=1200.0,
        seconds=40.0,
        reward_verdict=1.0,
        reward=1.0,
    )
    run = RunContext(run_id="gym-ref", git_branch="gym/loop", git_commit="7231818abcdef")
    return build_scorecard([row], run=run, dataset_digest="d" * 64, cases={"case": "python.k/1"})


def _rejected() -> GateVerdict:
    return GateVerdict(
        decision=GateDecision.REJECTED,
        reasons=[GateReason.LANGUAGE_REGRESSED],
        baseline_run_id="gym-ref",
        candidate_run_id="gym-exp",
        delta_j=0.02,
        token_ratio=0.95,
        language_deltas={"ruby": -0.5},
        regressed_languages=["ruby"],
    )


def _rows():
    card = _scorecard()
    baseline = build_ledger_row(
        card,
        row_id="ref-1",
        recorded_on=date(2026, 10, 26),
        wave=1,
        entry="baseline",
        tier="tier1",
        scorecard_path="evals/baselines/candidates/gym-20261026-7231818/scorecard.json",
    )
    experiment = build_ledger_row(
        card,
        row_id="exp-1",
        recorded_on=date(2026, 10, 26),
        wave=1,
        entry="experiment",
        tier="tier1",
        track="prompt",
        idea="Shorter producer packet | trimmed",
        gate=_rejected(),
        lesson="Ruby lost its only verified case.",
    )
    return baseline, experiment


def test_append_is_append_only_and_refuses_a_repeated_id(tmp_path):
    path = tmp_path / "ledger.jsonl"
    baseline, experiment = _rows()
    append_ledger(path, baseline)
    first = path.read_bytes()
    append_ledger(path, experiment)
    assert path.read_bytes().startswith(first)
    assert read_ledger(path) == [baseline, experiment]
    before = path.read_bytes()
    with pytest.raises(ValueError, match="already records"):
        append_ledger(path, experiment)
    assert path.read_bytes() == before


def test_render_keeps_the_header_prose_and_is_deterministic(tmp_path):
    original = (ROOT / "evals/experiments/LEDGER.md").read_text()
    markdown = tmp_path / "LEDGER.md"
    markdown.write_text(original)
    ledger = tmp_path / "ledger.jsonl"
    for row in _rows():
        append_ledger(ledger, row)
    text = render_ledger_file(ledger, markdown)
    assert text.startswith(ledger_header(original))
    assert render_ledger_file(ledger, markdown) == text
    assert render_ledger(read_ledger(ledger), ledger_header(text)) == text
    assert "| ref-1 | `7231818` | tier1 | 1 |" in text
    assert (
        "| exp-1 | prompt | `gym/loop` | REJECTED | ΔJ +0.020; tokens ×0.950; regressed: ruby |"
        in (text)
    )
    assert "| Shorter producer packet \\| trimmed | 1 | Ruby lost its only verified case. |" in text


def test_a_row_needs_the_runs_git_identity():
    card = _scorecard().model_copy(update={"run": RunContext(run_id="gym-ref")})
    with pytest.raises(ValueError, match="git branch and commit"):
        build_ledger_row(
            card,
            row_id="x",
            recorded_on=date(2026, 10, 26),
            wave=0,
            entry="baseline",
            tier="tier0",
        )
