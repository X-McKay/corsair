"""CLI/output integration over the real direct chain with deterministic stage/model doubles."""
import asyncio
from contextlib import asynccontextmanager
import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from chain_fakes import Fakes, case, models
from corsair.v2 import cli
from corsair.v2.chain import LocalOps, run_case
from corsair.v2.presentation import StageReporter, agent_table, console
from corsair.v2.record import RunRecorder


def _fake_cli(monkeypatch, tmp_path):
    from corsair.v2 import chain, models as model_config
    fakes = Fakes()
    monkeypatch.setattr(cli, "_intake", lambda args: case(tmp_path))
    monkeypatch.setattr(chain, "default_stages", fakes.stages)
    monkeypatch.setattr(model_config, "load_provider_config", lambda path: None)

    @asynccontextmanager
    async def agent_models(config):
        yield models()

    monkeypatch.setattr(model_config, "agent_models", agent_models)


def test_run_json_is_one_value_and_progress_is_stderr(tmp_path, monkeypatch, capsys):
    _fake_cli(monkeypatch, tmp_path)
    assert cli.main(["run", "--case", "fixture", "--run-root", str(tmp_path / "runs"), "--format", "json"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["schema"] == cli.CLI_SCHEMA and result["state"] == "completed"
    assert result["verdict"]["label"] == "LIKELY_EXPLOITABLE"
    assert result["agents"]["reviewer"]["retries"] is None
    assert "RUNNING" in captured.err and "DONE" in captured.err
    assert "\x1b" not in captured.out + captured.err


def test_run_text_has_existing_agent_metrics_without_ansi_in_pipe(tmp_path, monkeypatch, capsys):
    _fake_cli(monkeypatch, tmp_path)
    assert cli.main(["run", "--case", "fixture", "--run-root", str(tmp_path / "runs"), "--color", "never"]) == 0
    captured = capsys.readouterr()
    assert "label: LIKELY_EXPLOITABLE" in captured.out
    assert "Agent telemetry" in captured.out and "unknown" in captured.out
    assert "RUNNING" in captured.err and "\x1b" not in captured.out + captured.err


@pytest.mark.parametrize("kind", ["missing", "empty", "malformed", "nonobject", "badagents"])
def test_bad_run_records_return_data_error_before_any_output(tmp_path, capsys, kind):
    path = tmp_path / "record"
    if kind != "missing":
        path.mkdir()
    if kind == "malformed":
        (path / "run.json").write_text("{not json}")
    if kind == "nonobject":
        (path / "run.json").write_text("[]")
    if kind == "badagents":
        (path / "summary.json").write_text('{"agents": {"reviewer": 1}}')
    assert cli.main(["runs", "compare", str(path), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "corsair-v2:" in captured.err


def test_incomplete_record_stays_unknown_and_does_not_claim_active_work(tmp_path, capsys):
    path = tmp_path / "record"
    path.mkdir()
    (path / "run.json").write_text('{"run_id": "partial", "state": "recorded"}')
    assert cli.main(["runs", "compare", str(path), "--format", "json"]) == 0
    result = json.loads(capsys.readouterr().out)["runs"][0]
    assert result["state"] == "incomplete" and result["tokens"] is None and result["label"] is None


def test_no_color_environment_uses_native_rich_policy(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert console().no_color is True
    assert console(color="never").color_system is None


def test_nonterminal_reporter_does_not_animate_and_escapes_controls(capsys):
    with StageReporter() as progress:
        assert not progress.interactive
        progress("select", "started")
        progress("select", "ok 0.1s")
        progress.announce("untrusted\x1b[2J")
    text = capsys.readouterr().err
    assert "RUNNING" in text and "DONE" in text and "\\x1b[2J" in text and "\x1b" not in text


def test_tty_reporter_logs_and_updates_native_live_display(monkeypatch):
    sink = io.StringIO()
    tty = Console(file=sink, force_terminal=True, width=100)
    import corsair.v2.presentation as presentation
    monkeypatch.setattr(presentation, "console", lambda **kwargs: tty)
    monkeypatch.setenv("TERM", "xterm-256color")
    with StageReporter() as progress:
        assert progress.interactive
        progress("select", "started")
        progress("select", "ok 0.1s")
    assert "RUNNING" in sink.getvalue() and "DONE" in sink.getvalue()


def test_code_step_emits_start_and_one_terminal_event(tmp_path):
    fakes, events = Fakes(), []
    record = RunRecorder.create(tmp_path / "runs", "run")
    record.begin(case(tmp_path), mode="direct")
    ops = LocalOps(fakes.stages(), models(), tmp_path / "matrix", record,
                   lambda step, text: events.append((step, text)))
    result = asyncio.run(ops._code("select", {}, lambda: 42))
    assert result.output == 42 and len(events) == 2
    assert events[0] == ("select", "started") and events[1][1].startswith("ok ")
    assert json.loads((record.run_dir / "run.json").read_text())["last_started_step"] == "select"


def test_direct_cancel_propagates_and_records_no_invented_verdict(tmp_path, monkeypatch):
    from corsair.v2 import chain

    async def cancelled(case, ops, budget):
        ops._report("select", "started")
        raise asyncio.CancelledError()

    monkeypatch.setattr(chain, "compose", cancelled)
    record = RunRecorder.create(tmp_path / "runs", "cancelled")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_case(case(tmp_path), stages=Fakes().stages(), models=models(), matrix_path=tmp_path,
                             record=record))
    receipt = json.loads((record.run_dir / "run.json").read_text())
    assert receipt["state"] == "cancelled" and receipt["last_started_step"] == "select"
    assert receipt["stopped_at"] and receipt["finished_at"] is None
    assert not (record.run_dir / "verdict.json").exists() and not (record.run_dir / "summary.json").exists()


def test_agent_table_uses_unknown_not_zero():
    sink = io.StringIO()
    Console(file=sink, width=200).print(agent_table({"reviewer": {"calls": 1, "tool_calls": None}}))
    assert "unknown" in sink.getvalue()


def test_cancelled_json_run_emits_one_result_and_exit_130(tmp_path, monkeypatch, capsys):
    _fake_cli(monkeypatch, tmp_path)
    from corsair.v2 import chain

    async def cancelled(case, ops, budget):
        ops._report("select", "started")
        raise asyncio.CancelledError()

    monkeypatch.setattr(chain, "compose", cancelled)
    assert cli.main(["run", "--case", "fixture", "--run-root", str(tmp_path / "runs"), "--format", "json"]) == 130
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["schema"] == cli.CLI_SCHEMA and result["state"] == "cancelled"
    assert result["verdict"] is None and result["totals"] is None and result["client_interrupted"] is True
    assert "CANCELLED" in captured.err and "\x1b" not in captured.out + captured.err
    receipt = json.loads((Path(result["run_dir"]) / "run.json").read_text())
    assert receipt["finished_at"] is None and receipt["stopped_at"]


@pytest.mark.parametrize("state", ["interrupted", "recorded", "running", None])
def test_unwritten_or_unknown_lifecycle_states_are_incomplete(tmp_path, state):
    from corsair.v2.runs import details

    path = tmp_path / "record"
    path.mkdir()
    (path / "run.json").write_text(json.dumps({"state": state}))
    assert details(path)["state"] == "incomplete"


def test_public_printable_is_shared_by_comparison_and_rich_without_mutating_json(tmp_path, capsys):
    from corsair.v2.runs import printable

    value = "unsafe\x1b[2J\n\x7f\x85[bold]"
    escaped = "unsafe\\x1b[2J\\x0a\\x7f\\x85[bold]"
    assert printable(value) == escaped
    path = tmp_path / "record"
    path.mkdir()
    (path / "summary.json").write_text(json.dumps({"run_id": value, "agents": {value: {"calls": 1}}}))
    assert cli.main(["runs", "compare", str(path), "--agents", "--color", "never"]) == 0
    text = capsys.readouterr().out
    assert escaped in text and "\x1b" not in text and "\x85" not in text
    assert cli.main(["runs", "compare", str(path), "--format", "json"]) == 0
    record = json.loads(capsys.readouterr().out)["runs"][0]
    assert record["run"] == value and value in record["agents"]
