"""Offline ``corsair gym`` handlers: argument admission, exit codes and code-owned views.

``gym run`` needs Temporal and Docker and is covered by tests/integration/test_gym_runner.py;
every other subcommand reads saved files only.
"""

import json
import shutil
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import GateDecision, NoiseBand, RunContext, Scorecard, VerifyRecord
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.budgets import load_budgets
from corsair.evaluation.gym.ledger import read_ledger
from corsair.evaluation.gym.noise import noise_band, read_noise, write_noise
from corsair.evaluation.gym.scoring import (
    SCORECARD_FILE,
    TRAJECTORIES_FILE,
    build_scorecard,
    read_scorecard,
    read_trajectories,
    write_scorecard,
    write_trajectories,
)
from corsair.settings import Settings
from tests.unit.evaluation.test_gym_capture import CASE, _evals_root, _gym_run
from tests.unit.evaluation.test_gym_gate import ALL, BASELINE, CASES, NONE, _trajectory

ROOT = Path(__file__).resolve().parents[2]


def _arguments(*argv: str, format: str = "json") -> cli.CliArguments:
    return cli.parser().parse_args(["--format", format, *argv], namespace=cli.CliArguments())


async def _run(args: cli.CliArguments) -> int:
    return await cli.execute(args, Terminal(args))


def _card(
    path: Path, verified: dict[str, list[bool]], *, run_id: str, sliced: bool = False
) -> Path:
    rows = [
        _trajectory(case, repeat, flag, 100.0)
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]
    run = RunContext(run_id=run_id, git_branch="gym/loop", git_commit="a" * 40)
    card = build_scorecard(rows, run=run, dataset_digest="d" * 64, cases=CASES, sliced=sliced)
    write_scorecard(path, card)
    return path


def _settings_file(tmp_path: Path) -> Path:
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    path = tmp_path / "settings.json"
    path.write_text(settings.model_dump_json())
    return path


# Arguments


def test_gym_run_defaults_and_filters():
    args = _arguments("gym", "run", "tier0")
    assert (args.gym_command, args.tier, args.repeats, args.concurrency) == ("run", "tier0", 1, 2)
    assert args.cases is None and args.languages is None and args.temporal_address is None
    sliced = _arguments(
        "gym", "run", "tier1", "--case", "case01", "--case", "case02", "--lang", "python,c"
    )
    assert sliced.cases == ["case01", "case02"]
    assert sliced.languages == ["python,c"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["gym"], "the following arguments are required: gym_command"),
        (["gym", "gate", "--baseline", "a.json"], "the following arguments are required"),
        (["gym", "run", "tier0", "--repeats", "9"], "argument --repeats: invalid choice"),
        (["gym", "replay", "run-dir"], "the following arguments are required: --case"),
        (["gym", "ledger"], "the following arguments are required: ledger_command"),
        (
            ["gym", "gate", "--baseline", "a", "--candidate", "b", "--track", "speed"],
            "argument --track: invalid choice",
        ),
        (["gym", "verify", "--track", "latency"], "argument --track: invalid choice"),
    ],
)
def test_malformed_gym_commands_exit_with_usage(capsys, arguments, message):
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(arguments)
    assert error.value.code == 2
    assert message in capsys.readouterr().err


# gate


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate", "sliced", "code", "decision"),
    [
        ({**BASELINE, "py-b": ALL}, False, 0, "ACCEPTED"),
        ({**BASELINE, "rb-a": NONE}, False, 1, "REJECTED"),
        ({**BASELINE, "py-b": ALL}, True, 2, "INCOMPARABLE"),
    ],
)
async def test_gate_exits_with_the_verdict_code(
    tmp_path, capsys, candidate, sliced, code, decision
):
    baseline = _card(tmp_path / "base.json", BASELINE, run_id="base")
    proposed = _card(tmp_path / "cand.json", candidate, run_id="cand", sliced=sliced)
    args = _arguments("gym", "gate", "--baseline", str(baseline), "--candidate", str(proposed))

    assert await _run(args) == code
    assert json.loads(capsys.readouterr().out)["decision"] == decision


@pytest.mark.asyncio
async def test_gate_markdown_is_the_rendered_view(tmp_path, capsys):
    baseline = _card(tmp_path / "base.json", BASELINE, run_id="base")
    args = _arguments(
        "gym", "gate", "--baseline", str(baseline), "--candidate", str(baseline), format="markdown"
    )

    assert await _run(args) == 1
    out = capsys.readouterr().out
    assert out.startswith("## Gate: REJECTED")
    assert "The objective J gained less than the required margin." in out


@pytest.mark.asyncio
async def test_gate_decides_on_the_requested_track(tmp_path, capsys):
    baseline = _card(tmp_path / "base.json", BASELINE, run_id="base")
    better = _card(tmp_path / "cand.json", {**BASELINE, "py-b": ALL}, run_id="cand")
    pair = ["gym", "gate", "--baseline", str(baseline)]

    same = _arguments(*pair, "--candidate", str(baseline), "--track", "accuracy")
    assert await _run(same) == 1
    verdict = json.loads(capsys.readouterr().out)
    assert (verdict["track"], verdict["reasons"]) == ("accuracy", ["accuracy_not_improved"])
    targeted = [*pair, "--candidate", str(better), "--track", "accuracy"]
    assert await _run(_arguments(*targeted, "--target-language", "python")) == 0
    verdict = json.loads(capsys.readouterr().out)
    assert (verdict["track"], verdict["target_language"]) == ("accuracy", "python")
    efficiency = [*pair, "--candidate", str(baseline), "--track", "efficiency"]
    assert await _run(_arguments(*efficiency, format="markdown")) == 1
    assert capsys.readouterr().out.startswith("## Gate (efficiency track): REJECTED")
    assert await _run(_arguments(*pair, "--candidate", str(better))) == 0
    assert json.loads(capsys.readouterr().out)["track"] == "objective"
    with pytest.raises(ValueError, match="only to the accuracy track"):
        await _run(_arguments(*pair, "--candidate", str(better), "--target-language", "python"))


# budgets, export and ledger


@pytest.mark.asyncio
async def test_budgets_are_written_from_a_scorecard_with_their_digest(tmp_path, capsys):
    rows = [
        _trajectory("py-a", 0, True, 100.0).model_copy(update={"seconds": 10.0}),
        _trajectory("rb-a", 0, True, 200.0).model_copy(update={"seconds": 20.0}),
    ]
    card = build_scorecard(rows, run=RunContext(run_id="r"), dataset_digest="d" * 64, cases=CASES)
    source = tmp_path / "card.json"
    write_scorecard(source, card)
    out = tmp_path / "budgets.json"

    assert await _run(_arguments("gym", "budgets", "--from", str(source), "--out", str(out))) == 0
    receipt = json.loads(capsys.readouterr().out)
    budgets = load_budgets(out)
    assert budgets.root["python.k/1"].effective_tokens == 100.0
    assert len(receipt["digest"]) == 64


@pytest.mark.asyncio
async def test_export_groups_across_run_directories(tmp_path, capsys):
    for name, verified in (("run-a", True), ("run-b", False)):
        write_trajectories(
            tmp_path / name / TRAJECTORIES_FILE, [_trajectory("py-a", 0, verified, 100.0)]
        )
    out = tmp_path / "export.jsonl"
    args = _arguments(
        "gym",
        "export-grpo",
        "--runs",
        str(tmp_path / "run-a"),
        str(tmp_path / "run-b"),
        "--out",
        str(out),
    )

    assert await _run(args) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 2
    assert len(out.read_text().splitlines()) == 2


@pytest.mark.asyncio
async def test_ledger_append_records_a_gated_row_and_render_rewrites_the_tables(tmp_path):
    ledger, markdown = tmp_path / "ledger.jsonl", tmp_path / "LEDGER.md"
    shutil.copy(ROOT / "evals/experiments/LEDGER.md", markdown)
    baseline = _card(tmp_path / "base.json", BASELINE, run_id="base")
    candidate = _card(tmp_path / "cand.json", {**BASELINE, "py-b": ALL}, run_id="cand")
    common = ["--ledger", str(ledger)]

    reference = ["--scorecard", str(baseline), "--id", "ref-1", "--entry", "baseline"]
    reference += ["--tier", "tier1"]
    assert await _run(_arguments("gym", "ledger", "append", *reference, *common)) == 0
    experiment = ["--scorecard", str(candidate), "--id", "exp-1", "--entry", "experiment"]
    experiment += ["--tier", "tier1", "--wave", "1", "--track", "accuracy"]
    experiment += ["--baseline", str(baseline), "--lesson", "fixed python"]
    assert await _run(_arguments("gym", "ledger", "append", *experiment, *common)) == 0
    with pytest.raises(ValueError, match="already records ref-1"):
        await _run(_arguments("gym", "ledger", "append", *reference, *common))
    render = ["gym", "ledger", "render", *common, "--markdown", str(markdown)]
    assert await _run(_arguments(*render)) == 0

    rows = read_ledger(ledger)
    assert [row.id for row in rows] == ["ref-1", "exp-1"]
    assert rows[1].gate is not None and rows[1].gate.decision.value == "ACCEPTED"
    text = markdown.read_text()
    assert "| ref-1 |" in text and "| exp-1 | accuracy |" in text


# score, replay and capture over a saved gym run


def _saved_run(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root, dataset_path, dataset = _evals_root(tmp_path)
    settings = _settings_file(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    run_dir = _gym_run(tmp_path, store, root, dataset)
    return root, dataset_path, settings, run_dir


@pytest.mark.asyncio
async def test_score_writes_trajectories_and_a_scorecard_beside_the_report(tmp_path, capsys):
    _, dataset_path, settings, run_dir = _saved_run(tmp_path)
    args = _arguments(
        "gym",
        "score",
        str(run_dir / "report.json"),
        "--dataset",
        str(dataset_path),
        "--settings",
        str(settings),
    )

    assert await _run(args) == 0
    captured = capsys.readouterr()
    card = Scorecard.model_validate(json.loads(captured.out))
    assert card == read_scorecard(run_dir / SCORECARD_FILE)
    assert card.run.run_id == "report"
    assert "run context is unknown" in captured.err
    assert not (run_dir / gym.RUN_FILE).exists()
    assert [item.case_id for item in read_trajectories(run_dir / TRAJECTORIES_FILE)] == [CASE] * 2


IMPORTED = "gym-tier0-20261027t010807-479fc5"
IMPORTED_RUN = RunContext(
    run_id=IMPORTED,
    git_branch="gym/loop",
    git_commit="0697ff08" + "0" * 32,
    temporal_namespace="corsair-gym",
    task_queue="gym-gym-loop-0697ff0",
    concurrency=2,
    image_ids={"corsair-python:00cb018": "sha256:" + "1" * 64},
)


def _score_args(run_dir: Path, dataset_path: Path, settings: Path, *extra: str) -> cli.CliArguments:
    report = str(run_dir / "report.json")
    return _arguments(
        "gym", "score", report, "--dataset", str(dataset_path), "--settings", str(settings), *extra
    )


@pytest.mark.asyncio
async def test_score_recovers_an_imported_runs_context_from_its_old_scorecard(tmp_path, capsys):
    _, dataset_path, settings, imported = _saved_run(tmp_path)
    # An imported run: report and scorecard under <gym root>/runs/, no run.json.
    run_dir = tmp_path / "gym/runs" / IMPORTED
    shutil.copytree(imported, run_dir)
    old = _card(run_dir / SCORECARD_FILE, BASELINE, run_id=IMPORTED)
    write_scorecard(old, read_scorecard(old).model_copy(update={"run": IMPORTED_RUN}))
    out = tmp_path / "rescored"
    flags = ("--run-id", "ignored", "--git-commit", "b" * 40)

    assert await _run(_score_args(run_dir, dataset_path, settings, "--out", str(out), *flags)) == 0
    captured = capsys.readouterr()
    card = Scorecard.model_validate(json.loads(captured.out))
    assert card.run == IMPORTED_RUN
    assert read_scorecard(out / SCORECARD_FILE).run == IMPORTED_RUN
    assert "unknown" not in captured.err
    # run.json is written beside the report so the next score, replay or runs finds it.
    record = json.loads((run_dir / gym.RUN_FILE).read_text())
    assert record["run"] == IMPORTED_RUN.model_dump(mode="json")
    assert record["recovered_from"] == SCORECARD_FILE
    assert record["store"] == str(tmp_path / "artifacts")
    assert record["git"] == {"branch": "gym/loop", "commit": IMPORTED_RUN.git_commit}
    assert record["tier"] == "tier0"

    # The next score reads run.json even when the old scorecard is gone.
    (run_dir / SCORECARD_FILE).unlink()
    assert await _run(_score_args(run_dir, dataset_path, settings)) == 0
    assert read_scorecard(run_dir / SCORECARD_FILE).run == IMPORTED_RUN
    capsys.readouterr()

    assert await _run(_arguments("gym", "runs", "--root", str(tmp_path / "gym"))) == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert (row["run_id"], row["git_commit"], row["tier"]) == (
        IMPORTED,
        IMPORTED_RUN.git_commit,
        "tier0",
    )


@pytest.mark.asyncio
async def test_score_prefers_run_json_then_explicit_flags(tmp_path, capsys):
    _, dataset_path, settings, run_dir = _saved_run(tmp_path)
    flags = ("--run-id", "gym-x", "--git-commit", "b" * 40, "--git-branch", "gym/x")

    assert await _run(_score_args(run_dir, dataset_path, settings, *flags)) == 0
    captured = capsys.readouterr()
    assert Scorecard.model_validate(json.loads(captured.out)).run == RunContext(
        run_id="gym-x", git_branch="gym/x", git_commit="b" * 40
    )
    assert "unknown" not in captured.err
    # Explicit flags are the operator's claim, not a recovered record: no run.json.
    assert not (run_dir / gym.RUN_FILE).exists()

    (run_dir / gym.RUN_FILE).write_text(json.dumps({"run": IMPORTED_RUN.model_dump(mode="json")}))
    assert await _run(_score_args(run_dir, dataset_path, settings, *flags)) == 0
    assert Scorecard.model_validate(json.loads(capsys.readouterr().out)).run == IMPORTED_RUN

    # A run.json written before it recorded the context falls through to the scorecard.
    (run_dir / gym.RUN_FILE).write_text(json.dumps({"tier": "tier0"}))
    assert await _run(_score_args(run_dir, dataset_path, settings)) == 0
    assert Scorecard.model_validate(json.loads(capsys.readouterr().out)).run == IMPORTED_RUN
    assert json.loads((run_dir / gym.RUN_FILE).read_text()) == {"tier": "tier0"}


async def _score(run_dir: Path, dataset_path: Path, settings: Path) -> None:
    args = _arguments(
        "gym",
        "score",
        str(run_dir / "report.json"),
        "--dataset",
        str(dataset_path),
        "--settings",
        str(settings),
    )
    assert await _run(args) == 0


@pytest.mark.asyncio
async def test_replay_shows_rounds_calls_and_statements_never_payload_text(tmp_path, capsys):
    _, dataset_path, settings, run_dir = _saved_run(tmp_path)
    await _score(run_dir, dataset_path, settings)
    capsys.readouterr()
    replay = ["gym", "replay", str(run_dir), "--case", CASE, "--settings", str(settings)]

    assert await _run(_arguments(*replay)) == 0
    view = json.loads(capsys.readouterr().out)
    assert [repeat["result"] for repeat in view["repeats"]] == ["present", "present"]
    first = view["repeats"][0]
    assert first["rounds"][0]["audit_decision"] == "REJECT"
    assert "exploit_payload" not in first["rounds"][0]
    assert first["statements"]

    assert await _run(_arguments(*replay, format="markdown")) == 0
    text = capsys.readouterr().out
    assert text.startswith(f"## Replay `{CASE}`")
    assert "| Session | Round | Stop |" in text
    for model_text in ("../private/secret.txt", "hello.txt", "reviewed", "hypothesis"):
        assert model_text not in text
    with pytest.raises(ValueError, match="no trajectory"):
        await _run(
            _arguments(
                "gym", "replay", str(run_dir), "--case", "absent", "--settings", str(settings)
            )
        )


@pytest.mark.asyncio
async def test_capture_finds_the_manifest_by_digest_and_writes_under_the_checkout(
    tmp_path, capsys, monkeypatch
):
    root, _, settings, run_dir = _saved_run(tmp_path)
    monkeypatch.setattr(gym, "checkout_root", lambda: tmp_path)
    args = _arguments("gym", "capture", str(run_dir), "--case", CASE, "--settings", str(settings))

    assert await _run(args) == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured["case_id"] == CASE
    assert all(
        Path(path).is_relative_to(tmp_path / "tests/replay/kernel")
        for path in captured["kernel_cases"]
    )
    assert Path(captured["auditor_dataset"]).is_relative_to(root / "datasets")


def test_a_report_without_a_matching_manifest_needs_an_explicit_dataset(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"rows": [], "summary": {}, "dataset_digest": "0" * 64}))
    with pytest.raises(ValueError, match="pass --dataset"):
        gym.dataset_for_report(report, ROOT)
    tier0 = json.loads((ROOT / "evals/datasets/gym-tier0.json").read_text())
    from corsair.contracts import Dataset, digest

    report.write_text(
        json.dumps(
            {
                "rows": [],
                "summary": {},
                "dataset_digest": digest(Dataset.model_validate(tier0)),
            }
        )
    )
    assert gym.dataset_for_report(report, ROOT) == ROOT / "evals/datasets/gym-tier0.json"


# runs


def _stored_run(
    gym_root: Path, run_id: str, verified: dict[str, list[bool]], record: dict | None = None
) -> Path:
    run_dir = gym_root / "runs" / run_id
    _card(run_dir / SCORECARD_FILE, verified, run_id=run_id)
    if record is not None:
        (run_dir / gym.RUN_FILE).write_text(json.dumps(record))
    return run_dir


@pytest.mark.asyncio
async def test_runs_lists_stored_runs_newest_first_with_their_headline_figures(tmp_path, capsys):
    root = tmp_path / "gym"
    _stored_run(root, "gym-tier0-20261027t010807-479fc5", BASELINE)
    _stored_run(
        root,
        "custom",
        {**BASELINE, "py-b": ALL},
        {"tier": "tier1", "started_at": "2026-10-28T00:00:00+00:00", "git": {"dirty": True}},
    )
    older_layout = root / "gym-tier1-20261026t000000-abcdef"
    _card(older_layout / SCORECARD_FILE, BASELINE, run_id="gym-tier1-20261026t000000-abcdef")
    args = ["gym", "runs", "--root", str(root)]

    assert await _run(_arguments(*args)) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [(row["run_id"], row["tier"]) for row in rows] == [
        ("custom", "tier1"),
        ("gym-tier0-20261027t010807-479fc5", "tier0"),
        ("gym-tier1-20261026t000000-abcdef", "tier1"),
    ]
    assert rows[0]["worst_language"] == "ruby"
    assert rows[0]["git_dirty"] is True and rows[1]["git_dirty"] is None
    assert rows[1]["started_at"] == "2026-10-27T01:08:07+00:00"

    assert await _run(_arguments(*args, "--tier", "tier1", "--limit", "1")) == 0
    assert [row["run_id"] for row in json.loads(capsys.readouterr().out)] == ["custom"]

    assert await _run(_arguments(*args, format="markdown")) == 0
    text = capsys.readouterr().out
    assert "| Run | Commit | Tier | Repeats | Sliced | J |" in text
    assert "| `custom` | aaaaaaa+dirty | tier1 | 3 | no |" in text

    assert await _run(_arguments("gym", "runs", "--root", str(tmp_path / "empty"))) == 0
    assert json.loads(capsys.readouterr().out) == []


# verify


def _fake_runs(monkeypatch, tmp_path: Path, cards: dict[str, dict[str, list[bool]]]) -> list[str]:
    """Replace the runner: each tier returns a stored scorecard; the tiers run are recorded."""
    ran: list[str] = []

    async def run_gym(options, *, root, compose_activities, observe, held=None):
        del root, compose_activities, observe, held
        tier = gym.tier_name(options.dataset)
        ran.append(tier)
        run_dir = tmp_path / "runs" / tier
        card = read_scorecard(_card(run_dir / SCORECARD_FILE, cards[tier], run_id=f"cand-{tier}"))
        return gym.GymRun(run_dir, card, [], "127.0.0.1:1", True, 1.0)

    monkeypatch.setattr(gym, "run_gym", run_gym)
    return ran


def _reference(tmp_path: Path) -> Path:
    reference = tmp_path / "reference"
    for tier in ("tier0", "tier1"):
        _card(reference / f"{tier}.json", BASELINE, run_id=f"ref-{tier}")
    return reference


@pytest.mark.asyncio
async def test_verify_stops_at_a_tier0_rejection_without_running_tier1(
    tmp_path, capsys, monkeypatch
):
    ran = _fake_runs(monkeypatch, tmp_path, {"tier0": {**BASELINE, "rb-a": NONE}})
    args = ["gym", "verify", "--reference", str(_reference(tmp_path))]
    args += ["--settings", str(_settings_file(tmp_path))]

    assert await _run(_arguments(*args, format="markdown")) == 1
    assert ran == ["tier0"]
    captured = capsys.readouterr()
    text = captured.out
    # The final line is on stdout in the human view and on stderr in every format.
    assert captured.err.rstrip().splitlines()[-1] == "VERDICT: REJECTED"
    assert text.startswith("### tier0")
    assert "## Gate (smoke): REJECTED" in text
    assert "- tier1 was not run because tier0 was REJECTED." in text
    assert text.rstrip().splitlines()[-1] == "VERDICT: REJECTED"
    (verdict_path,) = (tmp_path / "artifacts/gym/verify").glob("*/verdict.json")
    record = VerifyRecord.model_validate_json(verdict_path.read_text())
    assert (record.branch, record.commit) == ("gym/loop", "a" * 40)
    assert (record.decision, record.complete) == (GateDecision.REJECTED, False)
    assert record.skipped == {"tier1": "rejected_at_tier0"}
    assert record.reference == str(tmp_path / "reference")
    assert record.tier0 is not None and record.tier1 is None
    assert record.tier0.scorecard == str(tmp_path / "runs/tier0" / SCORECARD_FILE)
    assert record.tier0.run_dir == str(tmp_path / "runs/tier0")
    assert record.tier0.reference == str(tmp_path / "reference/tier0.json")
    assert record.tier0.gate.language_deltas == {"python": 0.0, "ruby": -0.5}
    assert record.invocation and record.recorded_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tier0", "tier1", "code", "decision"),
    [
        ({**BASELINE, "py-b": ALL}, {**BASELINE, "py-b": ALL}, 0, "ACCEPTED"),
        ({**BASELINE, "py-b": ALL}, {**BASELINE, "rb-a": NONE}, 1, "REJECTED"),
        # An unchanged tier0 passes the smoke gate (objective margin reported, not rejecting).
        (BASELINE, {**BASELINE, "py-b": ALL}, 0, "ACCEPTED"),
    ],
)
async def test_verify_runs_tier1_after_tier0_and_decides_over_both_gates(
    tmp_path, capsys, monkeypatch, tier0, tier1, code, decision
):
    ran = _fake_runs(monkeypatch, tmp_path, {"tier0": tier0, "tier1": tier1})
    args = ["gym", "verify", "--reference", str(_reference(tmp_path))]
    args += ["--settings", str(_settings_file(tmp_path))]

    assert await _run(_arguments(*args)) == code
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert captured.err.rstrip().splitlines()[-1] == f"VERDICT: {decision}"
    assert "VERDICT" not in captured.out
    assert ran == ["tier0", "tier1"]
    assert record["decision"] == decision
    assert Path(record["verdict"]).is_file()
    # tier0 is gated in smoke mode (objective margin reported, not rejecting); tier1 is not.
    assert record["tier0"]["gate"]["smoke"] is True
    if record["tier1"] is not None:
        assert record["tier1"]["gate"]["smoke"] is False


@pytest.mark.asyncio
async def test_verify_with_skip_tier1_or_a_mismatched_reference(tmp_path, capsys, monkeypatch):
    ran = _fake_runs(monkeypatch, tmp_path, {"tier0": {**BASELINE, "py-b": ALL}})
    reference = _reference(tmp_path)
    (reference / "tier1.json").unlink()
    settings = ["--settings", str(_settings_file(tmp_path))]
    args = ["gym", "verify", "--reference", str(reference), *settings]

    with pytest.raises(ValueError, match="no reference scorecard"):
        await _run(_arguments(*args))
    assert ran == []
    assert await _run(_arguments(*args, "--skip-tier1", format="markdown")) == 0
    text = capsys.readouterr().out
    assert "- tier1 was skipped on request (--skip-tier1); this is not an acceptance." in text
    assert text.rstrip().endswith("VERDICT: ACCEPTED")

    sliced = reference / "tier0.json"
    _card(sliced, BASELINE, run_id="ref-tier0", sliced=True)
    assert await _run(_arguments(*args, "--skip-tier1")) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["decision"] == "INCOMPARABLE"
    assert captured.err.rstrip().splitlines()[-1] == "VERDICT: INCOMPARABLE"
    with pytest.raises(ValueError, match="no reference directory"):
        await _run(_arguments("gym", "verify", "--reference", str(tmp_path / "x"), *settings))


@pytest.mark.asyncio
async def test_a_verify_record_appends_to_the_ledger_and_renders(tmp_path, capsys, monkeypatch):
    _fake_runs(monkeypatch, tmp_path, {"tier0": {**BASELINE, "py-b": ALL}, "tier1": BASELINE})
    settings = ["--settings", str(_settings_file(tmp_path))]
    verify = ["gym", "verify", "--reference", str(_reference(tmp_path)), *settings]
    assert await _run(_arguments(*verify)) == 1
    verdict = Path(json.loads(capsys.readouterr().out)["verdict"])
    record = VerifyRecord.model_validate_json(verdict.read_text())
    assert (record.decision, record.complete) == (GateDecision.REJECTED, True)

    ledger, markdown = tmp_path / "ledger.jsonl", tmp_path / "LEDGER.md"
    shutil.copy(ROOT / "evals/experiments/LEDGER.md", markdown)
    common = ["--ledger", str(ledger)]
    append = ["gym", "ledger", "append", "--id", "exp-v", "--entry", "experiment"]
    append += ["--wave", "1", "--track", "prompt", "--verdict", str(verdict), *common]
    assert await _run(_arguments(*append, "--decision", "rejected")) == 0
    render = ["gym", "ledger", "render", *common, "--markdown", str(markdown)]
    assert await _run(_arguments(*render)) == 0

    (row,) = read_ledger(ledger)
    assert (row.branch, row.commit) == ("gym/loop", "a" * 40)
    assert (row.tier0, row.tier1) == (record.tier0, record.tier1)
    text = markdown.read_text()
    assert "| exp-v | prompt | `gym/loop@aaaaaaa` | ACCEPTED | REJECTED (" in text, text
    with pytest.raises(ValueError, match="name different candidates"):
        await _run(_arguments(*append[:3], "--id", "exp-w", *append[5:], "--commit", "b" * 40))


def test_verify_defaults_to_the_standard_protocol():
    args = _arguments("gym", "verify")
    assert (args.reference, args.repeats, args.concurrency, args.skip_tier1) == (None, 3, 2, False)
    assert (args.track, args.target_language) == ("objective", None)


@pytest.mark.asyncio
async def test_verify_gates_every_tier_on_its_track_and_records_it(tmp_path, capsys, monkeypatch):
    ran = _fake_runs(monkeypatch, tmp_path, {"tier0": BASELINE, "tier1": {**BASELINE, "py-b": ALL}})
    settings = ["--settings", str(_settings_file(tmp_path))]
    verify = ["gym", "verify", "--reference", str(_reference(tmp_path)), *settings]

    assert await _run(_arguments(*verify, "--track", "accuracy")) == 0
    record = VerifyRecord.model_validate_json(
        Path(json.loads(capsys.readouterr().out)["verdict"]).read_text()
    )
    assert record.track == "accuracy"
    assert record.tier0 is not None and record.tier1 is not None
    # tier0 is the smoke gate: its unchanged accuracy is reported, never rejecting.
    assert record.tier0.gate.track == record.tier1.gate.track == "accuracy"
    assert record.tier0.gate.reasons == ["accuracy_not_improved"]
    assert record.tier1.gate.decision is GateDecision.ACCEPTED
    assert ran == ["tier0", "tier1"]

    ran.clear()
    with pytest.raises(ValueError, match="not a baseline language"):
        await _run(_arguments(*verify, "--track", "accuracy", "--target-language", "c"))
    with pytest.raises(ValueError, match="only to the accuracy track"):
        await _run(_arguments(*verify, "--target-language", "python"))
    assert ran == []


# The run lock


def test_run_and_verify_take_the_lock_by_default_with_a_two_hour_timeout():
    for argv in (("gym", "run", "tier0"), ("gym", "verify")):
        args = _arguments(*argv)
        assert (args.no_lock, args.lock_timeout) == (False, gym.DEFAULT_LOCK_TIMEOUT)
    args = _arguments("gym", "run", "tier0", "--no-lock", "--lock-timeout", "30m")
    assert (args.no_lock, args.lock_timeout) == (True, 1800.0)
    assert _arguments("gym", "verify", "--lock-timeout", "90").lock_timeout == 90.0
    assert _arguments("gym", "verify", "--lock-timeout", "1.5h").lock_timeout == 5400.0


@pytest.mark.parametrize("value", ["soon", "2d", "-1h", ""])
def test_a_malformed_lock_timeout_exits_with_usage(capsys, value):
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(["gym", "run", "tier0", "--lock-timeout", value])
    assert error.value.code == 2
    assert "argument --lock-timeout" in capsys.readouterr().err


def test_no_lock_says_it_is_for_scripted_tests_only(capsys):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["gym", "run", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "--no-lock Scripted tests only" in text


def _held(root: Path, run_id: str = "gym-tier1-20261027t010000-aaaaaa") -> gym.LockHolder:
    holder = gym.new_lock_holder(run_id, tier="tier1", branch="gym/h1", commit="c" * 40)
    path = gym.lock_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**holder.record(), "token": holder.token}))
    return holder


@pytest.mark.asyncio
async def test_lock_status_and_a_forced_release_print_the_holder(tmp_path, capsys):
    root = ["--root", str(tmp_path)]
    assert await _run(_arguments("gym", "lock", "status", *root, format="markdown")) == 0
    assert capsys.readouterr().out == f"Gym lock under `{tmp_path / 'lock'}` is free.\n"
    assert await _run(_arguments("gym", "lock", "status", *root)) == 0
    assert json.loads(capsys.readouterr().out) == {"held": False, "holder": None}

    holder = _held(tmp_path)
    assert await _run(_arguments("gym", "lock", "status", *root, format="markdown")) == 0
    text = capsys.readouterr().out
    assert text.startswith(f"Gym lock: held by `{holder.run_id}` (tier1, gym/h1@ccccccc, pid ")
    assert ", running) for " in text
    assert await _run(_arguments("gym", "lock", "status", *root)) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["held"] is True and status["holder"]["run_id"] == holder.run_id
    assert "token" not in status["holder"]

    with pytest.raises(gym.GymRefused, match=f"held by `{holder.run_id}`.*pass --force"):
        await _run(_arguments("gym", "lock", "release", *root))
    assert gym.read_lock(tmp_path) == holder
    release = ["gym", "lock", "release", "--force", *root]
    assert await _run(_arguments(*release, format="markdown")) == 0
    assert capsys.readouterr().out.startswith(f"Released the gym lock held by `{holder.run_id}`")
    assert gym.read_lock(tmp_path) is None
    assert await _run(_arguments(*release)) == 0
    assert json.loads(capsys.readouterr().out) == {"released": False, "holder": None}


@pytest.mark.asyncio
async def test_runs_shows_a_held_lock_above_the_table(tmp_path, capsys):
    root = tmp_path / "gym"
    _stored_run(root, "gym-tier0-20261027t010807-479fc5", BASELINE)
    args = ["gym", "runs", "--root", str(root)]
    assert await _run(_arguments(*args, format="markdown")) == 0
    assert capsys.readouterr().out.startswith("## Gym runs under")

    holder = _held(root)
    assert await _run(_arguments(*args, format="markdown")) == 0
    first, blank, heading = capsys.readouterr().out.splitlines()[:3]
    assert first.startswith(f"Gym lock: held by `{holder.run_id}` (tier1,")
    assert (blank, heading) == ("", f"## Gym runs under `{root}`")
    assert await _run(_arguments(*args)) == 0
    assert [row["run_id"] for row in json.loads(capsys.readouterr().out)] == [
        "gym-tier0-20261027t010807-479fc5"
    ]


# The noise band

NOISE_IDENTITY = {"config": ["c" * 64]}
NOISY = {**BASELINE, "rb-a": NONE}


def _identified(
    path: Path, verified: dict[str, list[bool]], *, run_id: str, tokens: float = 100.0
) -> Path:
    """A scorecard of the noise configuration: one recorded identity, one dataset."""
    rows = [
        _trajectory(case, repeat, flag, tokens)
        for case, flags in verified.items()
        for repeat, flag in enumerate(flags)
    ]
    run = RunContext(run_id=run_id, git_branch="gym/loop", git_commit="a" * 40)
    card = build_scorecard(rows, run=run, dataset_digest="d" * 64, cases=CASES)
    write_scorecard(path, card.model_copy(update={"run_identity": NOISE_IDENTITY}))
    return path


def _noise_runs(root: Path) -> list[Path]:
    """Two stored tier1 runs of one configuration: ruby flips once, tokens differ 1.2x."""
    first = root / "runs/gym-tier1-20261027t012146-ade22e"
    second = root / "runs/gym-tier1-20261027t111450-29968e"
    _identified(first / SCORECARD_FILE, BASELINE, run_id=first.name)
    _identified(second / SCORECARD_FILE, NOISY, run_id=second.name, tokens=120.0)
    return [first, second]


@pytest.mark.asyncio
async def test_noise_writes_the_band_of_two_runs_under_the_reference_directory(tmp_path, capsys):
    root = tmp_path / "gym"
    first, second = _noise_runs(root)
    args = ["gym", "noise", str(first), str(second / SCORECARD_FILE), "--root", str(root)]

    assert await _run(_arguments(*args)) == 0
    record = json.loads(capsys.readouterr().out)
    out = root / "reference/noise-tier1.json"
    assert record["noise"] == str(out)
    band = NoiseBand.model_validate_json(out.read_text())
    assert band.runs == [first.name, second.name]
    assert band.languages["ruby"].band == 0.5
    assert record["n_runs"] == 2 and record["schema_version"] == "corsair.gym-noise/1"
    # The same band again is a no-op; a different band never replaces a reference.
    assert await _run(_arguments(*args, format="markdown")) == 0
    text = capsys.readouterr().out
    assert text.startswith("## Noise band: 2 runs\n")
    assert f"- Written to `{out}`" in text
    with pytest.raises(ValueError, match="already holds a different noise band"):
        await _run(_arguments("gym", "noise", str(second), str(first), "--root", str(root)))


@pytest.mark.asyncio
async def test_noise_refuses_runs_of_another_configuration_and_needs_a_tier_or_out(tmp_path):
    root = tmp_path / "gym"
    first, _ = _noise_runs(root)
    other = _card(tmp_path / "other.json", NOISY, run_id="other")  # no recorded identity
    with pytest.raises(ValueError, match="identity_mismatch"):
        await _run(_arguments("gym", "noise", str(first), str(other), "--out", str(tmp_path / "n")))
    custom = _identified(tmp_path / "custom.json", NOISY, run_id="custom")
    with pytest.raises(ValueError, match="pass --out"):
        await _run(_arguments("gym", "noise", str(first), str(custom), "--root", str(root)))
    out = tmp_path / "band.json"
    assert await _run(_arguments("gym", "noise", str(first), str(custom), "--out", str(out))) == 0
    assert out.is_file()
    with pytest.raises(SystemExit):
        _arguments("gym", "noise", str(first))


def _band(tmp_path: Path) -> Path:
    first, second = _noise_runs(tmp_path / "gym")
    out = tmp_path / "noise-tier1.json"
    write_noise(
        out, noise_band([read_scorecard(path / SCORECARD_FILE) for path in (first, second)])
    )
    return out


@pytest.mark.asyncio
async def test_gate_with_a_noise_band_exits_3_on_a_regression_inside_it(tmp_path, capsys):
    noise = _band(tmp_path)
    baseline = _card(tmp_path / "base.json", BASELINE, run_id="base")
    noisy = _identified(tmp_path / "cand.json", NOISY, run_id="cand", tokens=120.0)
    args = ["gym", "gate", "--baseline", str(baseline), "--candidate", str(noisy)]

    assert await _run(_arguments(*args)) == 1
    assert json.loads(capsys.readouterr().out)["decision"] == "REJECTED"
    assert await _run(_arguments(*args, "--noise", str(noise))) == 3
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["decision"] == "INCONCLUSIVE"
    assert verdict["reasons"][-1] == "within_noise"
    assert verdict["noise"]["runs"] == [
        "gym-tier1-20261027t012146-ade22e",
        "gym-tier1-20261027t111450-29968e",
    ]
    assert await _run(_arguments(*args, "--noise", str(noise), format="markdown")) == 3
    text = capsys.readouterr().out
    assert text.startswith("## Gate: INCONCLUSIVE\n")
    assert "Noise band from 2 runs" in text


@pytest.mark.asyncio
async def test_verify_reads_each_tiers_noise_band_and_exits_3_when_inconclusive(
    tmp_path, capsys, monkeypatch
):
    noise = _band(tmp_path)
    ran = _fake_runs(monkeypatch, tmp_path, {"tier0": BASELINE, "tier1": NOISY})
    settings = ["--settings", str(_settings_file(tmp_path))]
    verify = ["gym", "verify", "--reference", str(_reference(tmp_path)), *settings]

    assert await _run(_arguments(*verify)) == 1
    capsys.readouterr()
    assert await _run(_arguments(*verify, "--noise", str(noise))) == 3
    captured = capsys.readouterr()
    assert captured.err.rstrip().splitlines()[-1] == "VERDICT: INCONCLUSIVE"
    record = VerifyRecord.model_validate_json(Path(json.loads(captured.out)["verdict"]).read_text())
    assert record.decision is GateDecision.INCONCLUSIVE
    assert record.noise == [str(noise)]
    assert record.tier1 is not None and record.tier1.gate.noise is not None
    assert record.tier1.gate.decision is GateDecision.INCONCLUSIVE
    assert ran == ["tier0", "tier1", "tier0", "tier1"]

    ran.clear()
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(
        read_noise(noise).model_copy(update={"dataset_digest": "e" * 64}).model_dump_json()
    )
    with pytest.raises(ValueError, match="matches no gated tier"):
        await _run(_arguments(*verify, "--noise", str(elsewhere)))
    assert ran == []


@pytest.mark.asyncio
async def test_ledger_append_records_the_noise_band_and_an_inconclusive_gate(tmp_path, capsys):
    noise = _band(tmp_path)
    ledger, markdown = tmp_path / "ledger.jsonl", tmp_path / "LEDGER.md"
    shutil.copy(ROOT / "evals/experiments/LEDGER.md", markdown)
    reference = _card(tmp_path / "ref.json", BASELINE, run_id="ref")
    candidate = _identified(tmp_path / "cand.json", NOISY, run_id="cand", tokens=120.0)
    append = ["gym", "ledger", "append", "--ledger", str(ledger), "--entry", "experiment"]
    append += ["--wave", "4", "--tier1", str(candidate), "--reference-tier1", str(reference)]

    assert await _run(_arguments(*append, "--id", "n1", "--noise", str(noise))) == 0
    (row,) = read_ledger(ledger)
    assert row.noise == [str(noise)]
    assert row.tier1 is not None and row.tier1.gate.decision is GateDecision.INCONCLUSIVE
    render = ["gym", "ledger", "render", "--ledger", str(ledger), "--markdown", str(markdown)]
    assert await _run(_arguments(*render)) == 0
    text = markdown.read_text()
    assert "| n1 |  | `gym/loop@aaaaaaa` | — | INCONCLUSIVE (" in text
    assert "within_noise; regressed: ruby; within noise: objective_j" in text
    capsys.readouterr()
    with pytest.raises(ValueError, match="matches no gated tier"):
        await _run(_arguments(*append[:-4], "--id", "n2", "--noise", str(noise), "--branch", "b"))
