"""Native replay of mismatching isolated producer proposals (labelled sandbox double).

Source admission, ``run_evidence`` and evidence validation are real; only the sandbox is
the shared ``_FakeSandbox`` double, so these tests prove replay mechanics, never Docker.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from corsair.adapters.sandboxing import docker
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    PlanRevision,
    ProducerDecision,
    ProducerOutput,
    ProducerProposal,
    Submission,
    digest,
)
from corsair.entrypoints import cli
from corsair.entrypoints.markdown import to_markdown
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.agents import fixture_score_row
from corsair.evaluation.replay import replay_candidates
from corsair.evaluation.scoring import summarize
from corsair.settings import Settings
from tests.unit.test_evidence import _FakeSandbox

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals/datasets/producer-dev.json"
ORACLE = ROOT / "evals/fixtures/case01/producer-oracle.json"
# Semantically equivalent to the oracle's traversal but absent from its allowed list.
UNLISTED = "./../private/secret.txt"


def _settings(tmp_path: Path) -> Settings:
    return Settings(source_root=str(ROOT), artifact_root=str(tmp_path / "artifacts"))


def _output(control: str, exploit: str) -> ProducerOutput:
    submission = Submission(
        control_payload=control,
        exploit_payload=exploit,
        hypothesis="the joined path escapes the fixed root",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )
    return ProducerOutput(decision=ProducerDecision(ProducerProposal(submission=submission)))


def _report(settings: Settings, store: ArtifactStore, *outputs: ProducerOutput) -> dict[str, Any]:
    """An isolated producer report scored exactly as ``evaluate`` scores it."""
    oracle = json.loads(ORACLE.read_bytes())
    rows = [
        fixture_score_row(
            output,
            oracle,
            identity=f"isolated-{index}",
            case_id="case01",
            repeat=index,
            agent="producer",
            settings=settings,
            store=store,
        )
        for index, output in enumerate(outputs)
    ]
    dataset = json.loads(DATASET.read_bytes())
    return {"dataset_digest": digest(dataset), "rows": rows, "summary": summarize(rows)}


async def _replay(tmp_path: Path, sandbox_options: dict[str, Any], *outputs: ProducerOutput):
    settings = _settings(tmp_path)
    store = ArtifactStore(settings.artifact_root)
    sandbox = _FakeSandbox(store, **sandbox_options)
    report = _report(settings, store, *outputs)
    replayed = await replay_candidates(
        report, DATASET, settings, store, sandbox, replay_id="replay-unit"
    )
    return report, replayed, sandbox


async def test_a_demonstrating_unlisted_candidate_is_recorded_without_changing_the_fail(
    tmp_path,
):
    report, replayed, sandbox = await _replay(tmp_path, {}, _output("hello.txt", UNLISTED))

    [row] = replayed["rows"]
    assert row["match_kind"] == "candidate_exact_mismatch"
    assert row["status"] == "fail" == report["rows"][0]["status"]
    assert row["replay"] == {
        "status": "demonstrated",
        "demonstrated": True,
        "control": "PROPERTY_HELD",
        "adversarial": "VIOLATION",
        "covered": True,
        "cleanup_confirmed": True,
        "gate": None,
        "operation_id": "replay-unit.c0",
        "observation": row["replay"]["observation"],
    }
    assert row["replay"]["observation"] is not None
    assert sandbox.calls == 2
    assert {key: value for key, value in replayed["summary"].items() if key != "replay"} == (
        report["summary"]
    )
    assert replayed["summary"]["replay"] == {
        "demonstrated": 1,
        "not_demonstrated": 0,
        "unavailable": 0,
        "not_replayed": 0,
    }
    assert "human oracle decision" in replayed["replay_note"]
    assert "replay" not in report["rows"][0]


async def test_a_non_demonstrating_candidate_is_retained_as_does_not(tmp_path):
    _, replayed, sandbox = await _replay(
        tmp_path, {"adversarial_violates": False}, _output("hello.txt", "hello.txt")
    )

    [row] = replayed["rows"]
    assert row["status"] == "fail"
    assert row["replay"]["status"] == "not_demonstrated"
    assert row["replay"]["demonstrated"] is False
    assert (row["replay"]["control"], row["replay"]["adversarial"]) == (
        "PROPERTY_HELD",
        "PROPERTY_HELD",
    )
    assert row["replay"]["covered"] is True
    assert sandbox.calls == 2


async def test_an_invalid_receipt_never_demonstrates(tmp_path):
    _, replayed, _ = await _replay(tmp_path, {"forged": True}, _output("hello.txt", UNLISTED))

    [row] = replayed["rows"]
    assert row["replay"]["status"] == "not_demonstrated"
    assert row["replay"]["control"] == "INVALID"
    assert row["replay"]["covered"] is False


async def test_exact_matches_are_not_replayed_and_need_no_sandbox(tmp_path):
    exact = _output("hello.txt", "../private/secret.txt")
    _, replayed, sandbox = await _replay(tmp_path, {}, exact, _output("hello.txt", UNLISTED))

    first, second = replayed["rows"]
    assert first["match_kind"] == "exact_match" and first["replay"] is None
    assert second["replay"]["operation_id"] == "replay-unit.c1"
    assert replayed["summary"]["replay"]["not_replayed"] == 1
    assert sandbox.calls == 2


async def test_an_unreadable_producer_artifact_is_unavailable_not_demonstrated(tmp_path):
    settings = _settings(tmp_path)
    store = ArtifactStore(settings.artifact_root)
    report = _report(settings, store, _output("hello.txt", UNLISTED))
    report["rows"][0]["output_artifact"] = {"sha256": "0" * 64, "size": 1}
    sandbox = _FakeSandbox(store)

    replayed = await replay_candidates(
        report, DATASET, settings, store, sandbox, replay_id="replay-unit"
    )

    assert replayed["rows"][0]["replay"]["status"] == "unavailable"
    assert replayed["rows"][0]["replay"]["demonstrated"] is None
    assert sandbox.calls == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"dataset_digest": "f" * 64}, "dataset digest differs"),
        ({"agent": "auditor"}, "producer reports only"),
    ],
)
async def test_mismatched_dataset_or_non_producer_report_is_refused(tmp_path, change, message):
    settings = _settings(tmp_path)
    store = ArtifactStore(settings.artifact_root)
    report = _report(settings, store, _output("hello.txt", UNLISTED))
    if "agent" in change:
        report["rows"][0]["agent"] = change["agent"]
    else:
        report.update(change)

    with pytest.raises(ValueError, match=message):
        await replay_candidates(
            report, DATASET, settings, store, _FakeSandbox(store), replay_id="replay-unit"
        )


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(argv, namespace=cli.CliArguments())


async def test_cli_writes_a_replay_report_and_leaves_report_and_oracle_bytes(
    tmp_path, monkeypatch, capsys
):
    settings = _settings(tmp_path)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(settings.model_dump_json())
    store = ArtifactStore(settings.artifact_root)
    sandbox = _FakeSandbox(store)
    monkeypatch.setattr(docker, "DockerSandbox", lambda settings, *, store: sandbox)
    report_path = tmp_path / "producer.json"
    report_path.write_text(json.dumps(_report(settings, store, _output("hello.txt", UNLISTED))))
    before = (report_path.read_bytes(), ORACLE.read_bytes())
    output = tmp_path / "replay.json"

    args = _arguments(
        "--format",
        "json",
        "dataset",
        "replay-candidates",
        str(report_path),
        str(DATASET),
        "--settings",
        str(settings_path),
        "--run-id",
        "replay-cli",
        "--output",
        str(output),
    )
    code = await cli.execute(args, Terminal(args))

    assert code == 0
    emitted = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text())
    assert emitted["report"] == str(output)
    assert saved["rows"][0]["replay"]["status"] == "demonstrated"
    assert saved["rows"][0]["status"] == "fail"
    assert saved["replay_id"] == "replay-cli"
    assert (report_path.read_bytes(), ORACLE.read_bytes()) == before


async def test_cli_exits_one_when_a_replay_is_unavailable(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(settings.model_dump_json())
    store = ArtifactStore(settings.artifact_root)
    monkeypatch.setattr(docker, "DockerSandbox", lambda settings, *, store: _FakeSandbox(store))
    report = _report(settings, store, _output("hello.txt", UNLISTED))
    report["rows"][0]["output_artifact"] = None
    report_path = tmp_path / "producer.json"
    report_path.write_text(json.dumps(report))

    args = _arguments(
        "--format",
        "json",
        "dataset",
        "replay-candidates",
        str(report_path),
        str(DATASET),
        "--settings",
        str(settings_path),
        "--output",
        str(tmp_path / "replay.json"),
    )

    assert await cli.execute(args, Terminal(args)) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["replay"]["unavailable"] == 1


async def test_replay_renders_a_demonstrates_column_in_markdown_and_human(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("COLUMNS", "240")
    _, replayed, _ = await _replay(tmp_path, {}, _output("hello.txt", UNLISTED))

    markdown = to_markdown(replayed)
    assert "| Label | Replay | Stop |" in markdown
    assert "| demonstrates |" in markdown
    assert "### Native replay" in markdown
    assert "human oracle decision" in markdown

    args = _arguments("--format", "human", "--no-color", "report", "unused.json")
    Terminal(args).emit(replayed)
    human = capsys.readouterr().out
    assert "Replay" in human and "demonstrates" in human
    assert "human oracle decision" in human
