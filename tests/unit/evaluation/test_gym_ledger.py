"""Gym ledger: append-only JSONL and deterministic LEDGER.md rendering."""

import shutil
from datetime import date
from pathlib import Path
from typing import Literal

import pytest

from corsair.contracts import (
    GateDecision,
    GateReason,
    GateVerdict,
    LedgerDecision,
    LedgerRow,
    RunContext,
    Scorecard,
    TierGate,
    Trajectory,
    VerifyRecord,
)
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.ledger import (
    append_ledger,
    build_ledger_row,
    ledger_header,
    read_ledger,
    render_ledger,
    render_ledger_file,
)
from corsair.evaluation.gym.scoring import (
    SCORECARD_FILE,
    build_scorecard,
    read_scorecard,
    write_scorecard,
)
from tests.unit.evaluation.test_gym_gate import ALL, BASELINE, CASES, NONE, _trajectory

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
        decision="rejected",
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
        "| exp-1 | prompt | `gym/loop@7231818` | — "
        "| REJECTED (language_regressed; regressed: ruby) | — / +0.020 | — / 0.950 | rejected "
        "| Ruby lost its only verified case. |"
    ) in text
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


def test_the_recorded_ledger_still_parses_and_renders_identically(tmp_path):
    ledger, markdown = tmp_path / "ledger.jsonl", tmp_path / "LEDGER.md"
    shutil.copy(ROOT / "evals/experiments/ledger.jsonl", ledger)
    shutil.copy(ROOT / "evals/experiments/LEDGER.md", markdown)
    original = markdown.read_text()

    rows = read_ledger(ledger)
    assert rows, "the recorded ledger holds at least the wave-1 reference rows"
    assert {row.id for row in rows} >= {"ref-w1-tier0", "ref-w1-tier1"}
    assert len({row.id for row in rows}) == len(rows)
    assert render_ledger_file(ledger, markdown) == original


def _h3(
    *,
    entry: Literal["baseline", "experiment"] = "experiment",
    decision: LedgerDecision | None = "accepted",
    merge_commit: str | None = None,
) -> LedgerRow:
    return build_ledger_row(
        None,
        row_id="h3",
        recorded_on=date(2026, 10, 27),
        wave=1,
        entry=entry,
        branch="gym/h3-scorecard-reasoning-markers",
        commit="f6455392",
        track="dx",
        decision=decision,
        merge_commit=merge_commit,
        lesson="Score-neutral | offline\nmarkers.",
    )


def test_an_experiment_without_a_scorecard_renders_dashes():
    row = _h3()
    assert row.scorecard is None and row.objective_j is None and row.tier is None
    text = render_ledger([row], "# Ledger\n")
    assert (
        "| h3 | dx | `gym/h3-scorecard-reasoning-markers@f645539` | — | — | — | — | accepted "
        "| Score-neutral \\| offline markers. |"
    ) in text
    assert "### Wave 1" in text


def test_a_merged_decision_names_its_merge_commit():
    with pytest.raises(ValueError, match="merged decision needs its merge commit"):
        _h3(decision="merged")
    with pytest.raises(ValueError, match="merged decision needs its merge commit"):
        _h3(merge_commit="7d637e28")
    row = _h3(decision="merged", merge_commit="7d637e28")
    assert "| merged `7d637e2` |" in render_ledger([row], "# Ledger\n")


def test_a_baseline_needs_a_scorecard_and_its_tier():
    with pytest.raises(ValueError, match="baseline row needs a scorecard and its tier"):
        _h3(entry="baseline", decision=None)


def test_the_candidate_identity_must_agree_across_sources():
    def row(branch: str | None = None, commit: str | None = None) -> LedgerRow:
        return build_ledger_row(
            _scorecard(),
            row_id="x",
            recorded_on=date(2026, 10, 26),
            wave=1,
            entry="experiment",
            tier="tier1",
            branch=branch,
            commit=commit,
        )

    assert (row(commit="7231818").branch, row(commit="7231818").commit) == (
        "gym/loop",
        "7231818abcdef",
    )
    with pytest.raises(ValueError, match="name different candidates"):
        row(branch="gym/other")
    with pytest.raises(ValueError, match="name different candidates"):
        row(commit="1234567")


def _gym_card(verified, *, run_id: str, branch: str | None = None) -> Scorecard:
    rows = [
        _trajectory(case, repeat, flag, 100.0)
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]
    run = RunContext(
        run_id=run_id, git_branch=branch, git_commit=None if branch is None else "b" * 40
    )
    return build_scorecard(rows, run=run, dataset_digest="d" * 64, cases=CASES)


def _tier_card(path: Path, verified, *, run_id: str, branch: str = "gym/h1-x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_scorecard(path, _gym_card(verified, run_id=run_id, branch=branch))
    return path


def _gated_row() -> LedgerRow:
    base = _gym_card(BASELINE, run_id="ref")
    better = gate(base, _gym_card({**BASELINE, "py-b": ALL}, run_id="t0"))
    worse = gate(base, _gym_card({**BASELINE, "rb-a": NONE}, run_id="t1"))
    return build_ledger_row(
        None,
        row_id="h1",
        recorded_on=date(2026, 10, 27),
        wave=1,
        entry="experiment",
        branch="gym/h1-x",
        commit="b" * 40,
        track="prompt",
        idea="Trim the producer packet",
        tier0=TierGate(reference="ref-w1-tier0", scorecard="t0.json", gate=better),
        tier1=TierGate(reference="ref-w1-tier1", scorecard="t1.json", gate=worse),
        decision="rejected",
    )


def test_a_two_tier_row_renders_both_gates_and_is_a_rejected_idea():
    text = render_ledger([_gated_row()], "# Ledger\n")
    assert (
        "| h1 | prompt | `gym/h1-x@bbbbbbb` | ACCEPTED "
        "| REJECTED (language_regressed, objective_below_threshold; regressed: ruby) "
        "| +0.250 / -0.500 | 1.000 / 1.000 | rejected |  |"
    ) in text
    assert (
        "| Trim the producer packet | 1 | tier0 ACCEPTED; tier1 REJECTED "
        "(language_regressed, objective_below_threshold; regressed: ruby) |"
    ) in text


# CLI


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


async def _append(ledger: Path, *argv: str) -> int:
    args = _arguments("gym", "ledger", "append", "--ledger", str(ledger), *argv)
    return await cli.execute(args, Terminal(args))


def _seeded_ledger(tmp_path: Path) -> Path:
    """A ledger with tier0 and tier1 baseline rows whose scorecards share one dataset."""
    ledger = tmp_path / "ledger.jsonl"
    for tier in ("tier0", "tier1"):
        card = _tier_card(
            tmp_path / f"ref-{tier}.json", BASELINE, run_id=f"ref-{tier}", branch="gym/loop"
        )
        row = build_ledger_row(
            read_scorecard(card),
            row_id=f"ref-{tier}",
            recorded_on=date(2026, 10, 26),
            wave=1,
            entry="baseline",
            tier=tier,
            scorecard_path=str(card),
        )
        append_ledger(ledger, row)
    return ledger


@pytest.mark.asyncio
async def test_append_records_a_scorecard_less_experiment(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    argv = ["--id", "h3", "--entry", "experiment", "--wave", "1", "--track", "dx"]
    argv += ["--branch", "gym/h3-scorecard-reasoning-markers", "--commit", "f6455392"]
    argv += ["--decision", "merged", "--merge-commit", "7d637e28", "--lesson", "score-neutral"]
    assert await _append(ledger, *argv) == 0
    (row,) = read_ledger(ledger)
    assert (row.branch, row.commit, row.decision, row.merge_commit) == (
        "gym/h3-scorecard-reasoning-markers",
        "f6455392",
        "merged",
        "7d637e28",
    )
    assert row.scorecard is None and row.tier0 is None and row.tier1 is None


@pytest.mark.asyncio
async def test_append_gates_both_tiers_against_the_latest_baselines(tmp_path):
    ledger = _seeded_ledger(tmp_path)
    run_dir = tmp_path / "runs/gym-tier0-x"
    _tier_card(run_dir / SCORECARD_FILE, {**BASELINE, "py-b": ALL}, run_id="t0")
    tier1 = _tier_card(tmp_path / "t1.json", {**BASELINE, "py-b": ALL}, run_id="t1")
    argv = ["--id", "h1", "--entry", "experiment", "--wave", "1", "--track", "prompt"]
    argv += ["--tier0", str(run_dir), "--tier1", str(tier1)]
    argv += ["--reference-tier1", str(tmp_path / "ref-tier1.json"), "--decision", "accepted"]
    assert await _append(ledger, *argv) == 0

    row = read_ledger(ledger)[-1]
    assert (row.branch, row.commit) == ("gym/h1-x", "b" * 40)
    assert row.tier0 is not None and row.tier1 is not None
    assert (row.tier0.reference, row.tier0.run_dir) == ("ref-tier0", str(run_dir))
    assert row.tier0.scorecard == str(run_dir / SCORECARD_FILE)
    assert (row.tier1.reference, row.tier1.run_dir) == (str(tmp_path / "ref-tier1.json"), None)
    assert row.tier0.gate.decision is GateDecision.ACCEPTED
    assert row.tier1.gate.language_deltas == {"python": 0.5, "ruby": 0.0}


@pytest.mark.asyncio
async def test_append_copies_a_verify_record(tmp_path):
    ledger = _seeded_ledger(tmp_path)
    base = read_scorecard(tmp_path / "ref-tier0.json")
    candidate = read_scorecard(
        _tier_card(tmp_path / "run/scorecard.json", {**BASELINE, "py-b": ALL}, run_id="t0")
    )
    record = VerifyRecord(
        branch="gym/h1-x",
        commit="b" * 40,
        tier0=TierGate(
            reference="ref-tier0",
            scorecard=str(tmp_path / "run/scorecard.json"),
            run_dir=str(tmp_path / "run"),
            gate=gate(base, candidate),
        ),
    )
    verdict = tmp_path / "verdict.json"
    verdict.write_text(record.model_dump_json())
    argv = ["--id", "h1", "--entry", "experiment", "--wave", "1", "--verdict", str(verdict)]
    assert await _append(ledger, *argv, "--decision", "accepted") == 0

    row = read_ledger(ledger)[-1]
    assert (row.branch, row.commit, row.tier0, row.tier1) == (
        "gym/h1-x",
        "b" * 40,
        record.tier0,
        None,
    )
    with pytest.raises(ValueError, match="--verdict already carries the tier gates"):
        await _append(
            ledger, "--id", "h2", "--entry", "experiment", "--verdict", str(verdict), "--tier0", "x"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["--id", "ref-tier0", "--entry", "experiment", "--branch", "b", "--commit", "1234567"],
            "ledger already records ref-tier0",
        ),
        (
            ["--id", "x", "--entry", "baseline", "--branch", "b", "--commit", "1234567"],
            "baseline row needs a scorecard and its tier",
        ),
        (
            [
                "--id",
                "x",
                "--entry",
                "experiment",
                "--branch",
                "b",
                "--commit",
                "1234567",
                "--decision",
                "merged",
            ],
            "merged decision needs its merge commit",
        ),
        (["--id", "x", "--entry", "experiment"], "git branch and commit"),
        (
            [
                "--id",
                "x",
                "--entry",
                "experiment",
                "--branch",
                "b",
                "--commit",
                "1234567",
                "--reference-tier0",
                "ref-tier0",
            ],
            "--reference-tier0 needs --tier0",
        ),
    ],
)
async def test_append_refuses_incoherent_rows_and_leaves_the_ledger(tmp_path, argv, message):
    ledger = _seeded_ledger(tmp_path)
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match=message):
        await _append(ledger, *argv)
    assert ledger.read_bytes() == before
