"""Offline CLI handler regressions: exit codes, JSON receipts and error paths.

The native console process, Docker and Temporal are covered by tests/integration/test_cli.py.
These tests call the same handlers in-process with a JSON terminal, settings on tmp_path and
the labelled evidence-unit sandbox double, so no container, workflow or provider is involved.
"""

import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.adapters.sandboxing import docker
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Disposition,
    ExecutionStatus,
    InvestigationResult,
    Submission,
    Verdict,
)
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.settings import Settings
from tests.unit.test_evidence import _FakeSandbox, _submission

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals/datasets/dev.json"
# A case02 INCONCLUSIVE completion is acceptable to its external oracle without evidence.
CASE = "case02"
SOURCE = (
    "def read_file(root, path):\n"
    "    import os\n"
    "\n"
    "    return open(os.path.join(root, path)).read()\n"
)


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


def _terminal(args: cli.CliArguments) -> Terminal:
    terminal = Terminal(args)
    assert not terminal.human and not terminal.animate
    return terminal


def _settings_file(tmp_path: Path) -> tuple[Path, ArtifactStore]:
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    path = tmp_path / "settings.json"
    path.write_text(settings.model_dump_json())
    return path, ArtifactStore(settings.artifact_root)


def _commit_result(store: ArtifactStore, run_id: str, case_id: str = CASE) -> None:
    result = InvestigationResult(
        run_id=run_id,
        case_id=case_id,
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        reason="budget exhausted without a demonstration",
    )
    store.commit(f"result.{run_id}", store.put_json(result))


async def _run(args: cli.CliArguments) -> int:
    return await cli.execute(args, _terminal(args))


@pytest.fixture
def restored_logging() -> Iterator[None]:
    """main() installs process-wide handlers; return the loggers to their prior state."""
    selected = [logging.getLogger(name) for name in ("corsair", "")]
    prior = [(log.handlers[:], log.level, log.propagate, log.disabled) for log in selected]
    try:
        yield
    finally:
        for log, (handlers, level, propagate, disabled) in zip(selected, prior, strict=True):
            for handler in log.handlers:
                if handler not in handlers:
                    handler.close()
            log.handlers = handlers
            log.setLevel(level)
            log.propagate = propagate
            log.disabled = disabled


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["corsair", "--format", "json", "--log-format", "json", *argv])
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert isinstance(stopped.value.code, int)
    return stopped.value.code


def _stderr_events(stderr: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stderr.splitlines()]


# report


@pytest.mark.usefixtures("restored_logging")
def test_main_reports_a_saved_report_with_exit_zero(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"rows": [], "summary": {"attempts": 2, "failed": 0}}))

    assert _main(monkeypatch, "report", str(report)) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"rows": [], "summary": {"attempts": 2, "failed": 0}}
    assert captured.err == ""


@pytest.mark.parametrize("body", ['["summary"]', '{"summary": 3}', '{"rows": []}'])
@pytest.mark.usefixtures("restored_logging")
def test_main_rejects_a_report_without_a_summary_object(tmp_path, monkeypatch, capsys, body):
    report = tmp_path / "report.json"
    report.write_text(body)

    assert _main(monkeypatch, "report", str(report)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    failure = _stderr_events(captured.err)[-1]
    assert failure["event"] == "cli.failed"
    assert failure["error_type"] == "ValueError"
    assert failure["message"] == "report must contain a summary object"


@pytest.mark.usefixtures("restored_logging")
def test_main_rejects_a_report_that_is_not_json(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"
    report.write_text("{not json")

    assert _main(monkeypatch, "report", str(report)) == 2
    failure = _stderr_events(capsys.readouterr().err)[-1]
    assert failure["error_type"] == "JSONDecodeError"


# main exit codes


@pytest.mark.usefixtures("restored_logging")
def test_main_maps_keyboard_interrupt_to_130_and_detaches(monkeypatch, capsys):
    async def interrupted(_args, _terminal):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "execute", interrupted)

    assert _main(monkeypatch, "inspect", "run-detached") == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    interruption = _stderr_events(captured.err)[-1]
    assert interruption["event"] == "cli.interrupted"
    assert interruption["level"] == "WARNING"
    assert "workflows continue" in str(interruption["message"])


@pytest.mark.usefixtures("restored_logging")
def test_main_maps_unexpected_exceptions_to_2_with_safe_detail(monkeypatch, capsys):
    async def failed(_args, _terminal):
        raise RuntimeError("worker lost \x1b[31mcontrol")

    monkeypatch.setattr(cli, "execute", failed)

    assert _main(monkeypatch, "inspect", "run-failed") == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Traceback" not in captured.err
    failure = _stderr_events(captured.err)[-1]
    assert failure["event"] == "cli.failed"
    assert failure["level"] == "ERROR"
    assert failure["error_type"] == "RuntimeError"
    assert "worker lost" in str(failure["message"]) and "\x1b" not in captured.err


async def test_execute_rejects_an_unregistered_command():
    args = _arguments("report", "unread.json")
    args.command = "publish"

    with pytest.raises(ValueError, match="Unknown command"):
        await _run(args)


# inspect (offline)


async def test_inspect_emits_the_committed_result_receipt(tmp_path, capsys):
    settings, store = _settings_file(tmp_path)
    _commit_result(store, "run-committed")

    code = await _run(_arguments("inspect", "run-committed", "--settings", str(settings)))

    assert code == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["run_id"] == "run-committed"
    assert receipt["case_id"] == CASE
    assert receipt["disposition"] == "INCONCLUSIVE"
    assert receipt["schema_version"] == "corsair.result/1"


async def test_inspect_without_a_committed_result_points_to_online(tmp_path, capsys):
    settings, _store = _settings_file(tmp_path)

    with pytest.raises(ValueError, match="No committed result; use --online"):
        await _run(_arguments("inspect", "run-absent", "--settings", str(settings)))
    assert capsys.readouterr().out == ""


async def test_inspect_rejects_an_invalid_run_id_before_reading_settings(tmp_path):
    unread = tmp_path / "unread-settings.json"

    with pytest.raises(ValidationError):
        await _run(_arguments("inspect", "bad/id", "--settings", str(unread)))
    assert not unread.exists()


# rescore


async def test_rescore_keeps_an_unavailable_run_explicit(tmp_path, capsys):
    settings, store = _settings_file(tmp_path)
    _commit_result(store, "run-available")
    output = tmp_path / "rescored.json"

    code = await _run(
        _arguments(
            "rescore",
            str(DATASET),
            "run-available",
            "run-missing",
            "--settings",
            str(settings),
            "--output",
            str(output),
        )
    )

    assert code == 1
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["report"] == str(output)
    summary = emitted["summary"]
    assert (summary["attempts"], summary["passed"], summary["failed"]) == (2, 1, 1)
    assert summary["unavailable_results"] == 1
    rows = {row["run_id"]: row for row in json.loads(output.read_text())["rows"]}
    assert rows["run-available"]["status"] == "pass"
    assert (rows["run-available"]["family"], rows["run-available"]["split"]) == ("family01", "dev")
    assert rows["run-missing"]["status"] == "unavailable"
    assert "family" not in rows["run-missing"]
    assert "No committed result" in rows["run-missing"]["reason"]


async def test_rescore_of_only_available_runs_exits_zero(tmp_path, capsys):
    settings, store = _settings_file(tmp_path)
    _commit_result(store, "run-available")
    output = tmp_path / "rescored.json"

    code = await _run(
        _arguments(
            "rescore",
            str(DATASET),
            "run-available",
            "--settings",
            str(settings),
            "--output",
            str(output),
        )
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 0


async def test_rescore_marks_a_result_for_an_unknown_case_unavailable(tmp_path, capsys):
    settings, store = _settings_file(tmp_path)
    _commit_result(store, "run-other", case_id="case-not-in-dataset")
    output = tmp_path / "rescored.json"

    code = await _run(
        _arguments(
            "rescore",
            str(DATASET),
            "run-other",
            "--settings",
            str(settings),
            "--output",
            str(output),
        )
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out)["summary"]["unavailable_results"] == 1
    assert json.loads(output.read_text())["rows"][0]["status"] == "unavailable"


# verify (labelled sandbox double; real source admission and evidence validation)


def _verify_inputs(tmp_path: Path) -> tuple[Path, Path, Path, ArtifactStore]:
    settings, store = _settings_file(tmp_path)
    source = tmp_path / "case" / "source"
    source.mkdir(parents=True)
    (source / "reader.py").write_text(SOURCE)
    request = tmp_path / "case" / "request.json"
    request.write_text(
        json.dumps(
            {
                "case": {
                    "case_id": "case",
                    "finding": {
                        "title": "secret path",
                        "description": "component finding",
                        "file": "reader.py",
                        "line": 4,
                        "claim_scope": "component",
                    },
                    "source": {"path": "source"},
                    "recipe": {
                        "module_file": "reader.py",
                        "function": "read_file",
                        "payload_parameter": "path",
                        "fixed_kwargs": {"root": "/fixtures/allowed"},
                    },
                }
            }
        )
    )
    submission = tmp_path / "submission.json"
    submission.write_text(_submission().model_dump_json())
    assert Submission.model_validate_json(submission.read_bytes()) == _submission()
    return settings, request, submission, store


def _install_sandbox(monkeypatch: pytest.MonkeyPatch, sandbox: _FakeSandbox) -> None:
    def build(settings: Settings, *, store: ArtifactStore) -> _FakeSandbox:
        del settings
        assert store.root == sandbox.store.root
        return sandbox

    monkeypatch.setattr(docker, "DockerSandbox", build)


def _completion(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    [record] = [record for record in caplog.records if record.message == "reference.completed"]
    return record.__dict__["fields"]


async def test_verify_healthy_observation_exits_zero(tmp_path, monkeypatch, capsys, caplog):
    settings, request, submission, store = _verify_inputs(tmp_path)
    sandbox = _FakeSandbox(store)
    _install_sandbox(monkeypatch, sandbox)
    caplog.set_level(logging.INFO, logger="corsair")

    code = await _run(
        _arguments(
            "verify",
            str(request),
            str(submission),
            "--run-id",
            "reference-healthy",
            "--settings",
            str(settings),
        )
    )

    assert code == 0
    observation = json.loads(capsys.readouterr().out)
    assert observation["operation_id"] == "reference-healthy.reference"
    assert observation["control"]["outcome"] == "PROPERTY_HELD"
    assert observation["adversarial"]["outcome"] == "VIOLATION"
    assert observation["cleanup_confirmed"] is True
    assert observation["feedback"] is None
    assert sandbox.calls == 2
    assert _completion(caplog)["status"] == "pass"


@pytest.mark.parametrize(
    "double",
    [{"forged": True}, {"cleanup_confirmed": False}, {"raw_image_id": "sha256:other"}],
)
async def test_verify_invalid_observation_exits_one(tmp_path, monkeypatch, capsys, caplog, double):
    settings, request, submission, store = _verify_inputs(tmp_path)
    _install_sandbox(monkeypatch, _FakeSandbox(store, **double))
    caplog.set_level(logging.INFO, logger="corsair")

    code = await _run(
        _arguments("verify", str(request), str(submission), "--settings", str(settings))
    )

    assert code == 1
    observation = json.loads(capsys.readouterr().out)
    assert observation["operation_id"].startswith("reference-")
    assert observation["control"]["outcome"] == "INVALID"
    assert _completion(caplog)["status"] == "fail"


async def test_verify_fixed_without_fixed_source_is_blocked(tmp_path, monkeypatch, capsys):
    settings, request, submission, store = _verify_inputs(tmp_path)
    sandbox = _FakeSandbox(store)
    _install_sandbox(monkeypatch, sandbox)

    code = await _run(
        _arguments("verify", str(request), str(submission), "--fixed", "--settings", str(settings))
    )

    assert code == 1
    observation = json.loads(capsys.readouterr().out)
    assert observation["feedback"]["gate"] == "source-admission"
    assert observation["cleanup_confirmed"] is False
    assert sandbox.calls == 0
