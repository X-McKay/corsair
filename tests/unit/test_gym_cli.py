"""Offline ``corsair gym`` handlers: argument admission, exit codes and code-owned views.

``gym run`` needs Temporal and Docker and is covered by tests/integration/test_gym_runner.py;
every other subcommand reads saved files only.
"""

import json
import shutil
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import RunContext, Scorecard
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.budgets import load_budgets
from corsair.evaluation.gym.ledger import read_ledger
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
    card = Scorecard.model_validate(json.loads(capsys.readouterr().out))
    assert card == read_scorecard(run_dir / SCORECARD_FILE)
    assert card.run.run_id == "report"
    assert [item.case_id for item in read_trajectories(run_dir / TRAJECTORIES_FILE)] == [CASE] * 2


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
        await _run(_arguments("gym", "replay", str(run_dir), "--case", "absent"))


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
