import ast
import asyncio
import io
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from corsair.entrypoints import terminal as terminal_module
from corsair.entrypoints.cli import execute, parser, validate_run_id
from corsair.entrypoints.terminal import Terminal, progress_fields, progress_panel
from corsair.observability.logging import JsonFormatter, MetadataFilter, event


@pytest.mark.parametrize(
    "arguments",
    [
        ["--format", "json", "report", "x"],
        ["report", "x", "--format", "json"],
    ],
)
def test_presentation_options_work_before_and_after_command(arguments):
    args = parser().parse_args(arguments)
    assert args.format == "json"
    assert args.no_animation is False


def test_machine_output_has_no_ansi_even_with_forced_color(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    terminal.emit({"status": "pass", "message": "[red]data not markup[/red]"})
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert json.loads(output)["message"].startswith("[red]")
    assert not terminal.animate


def test_human_terminal_displays_colors_without_interpreting_data(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    terminal = Terminal(parser().parse_args(["--format", "human", "report", "x"]))
    terminal.emit({"attempts": 3, "passed": 2, "failed": 1, "cost_usd": None})
    output = capsys.readouterr().out
    assert "\x1b[" in output
    assert "Corsair" in output
    assert "unknown" in output


def test_no_color_and_no_animation_disable_control_codes(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    terminal = Terminal(
        parser().parse_args(
            [
                "report",
                "x",
                "--format",
                "human",
                "--no-color",
                "--no-animation",
            ]
        )
    )
    terminal.emit({"attempts": 1})
    assert "\x1b" not in capsys.readouterr().out
    assert not terminal.animate


async def test_wait_observes_queries_and_propagates_result():
    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    queries = []

    async def query():
        queries.append(True)
        return {"phase": "evidence", "round": 1}

    result = await terminal.wait(asyncio.sleep(0, result=42), "Real waiter", query=query)
    assert result == 42
    assert len(queries) == 1


async def test_cancelling_local_wait_does_not_call_remote_cancel():
    terminal = Terminal(parser().parse_args(["report", "x"]))
    released = asyncio.Event()

    async def pending():
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    waiter = asyncio.create_task(terminal.wait(pending(), "pending"))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert released.is_set()


def test_structured_logs_whitelist_and_redact_credentials(monkeypatch):
    monkeypatch.setenv("PRIVATE_API_TOKEN", "private-token-to-redact")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(MetadataFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("corsair")
    prior_handlers = logger.handlers[:]
    prior_level, prior_propagate = logger.level, logger.propagate
    logger.handlers.clear()
    logger.handlers.append(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    try:
        event(
            "activity.failed",
            run_id="r1",
            error_type="RuntimeError",
            message="private-token-to-redact https://user:password@example.com/x?token=y\x1b[31m",
            prompt="NEVER_LOG_THIS",
            payload="NEVER_LOG_THIS",
        )
    finally:
        logger.handlers.clear()
        logger.handlers.extend(prior_handlers)
        logger.propagate = prior_propagate
        logger.setLevel(prior_level)
    row = json.loads(output.getvalue())
    assert row["run_id"] == "r1"
    assert "prompt" not in row and "payload" not in row
    assert "private-token-to-redact" not in output.getvalue()
    assert "password" not in output.getvalue()
    assert "\x1b" not in output.getvalue()


def test_failed_command_has_clean_jsonl_stderr_and_nonzero_exit(tmp_path):
    executable = Path(sys.executable).parent / "corsair"
    result = subprocess.run(
        [
            str(executable),
            "--format",
            "json",
            "--log-format",
            "json",
            "report",
            str(tmp_path / "absent"),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "FORCE_COLOR": "1"},
    )
    assert result.returncode == 2
    assert result.stdout == ""
    rows = [json.loads(line) for line in result.stderr.splitlines()]
    assert rows[-1]["event"] == "cli.failed"
    assert rows[-1]["error_type"] == "FileNotFoundError"
    assert "\x1b" not in result.stderr and "Traceback" not in result.stderr


def test_runtime_has_no_placeholder_or_test_dependency():
    root = Path(__file__).resolve().parents[2] / "src/corsair"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("tests", "unittest.mock")), path
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.startswith(("tests", "unittest.mock")) for alias in node.names
                ), path
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                assert getattr(node.exc.func, "id", None) != "NotImplementedError", path


def test_nested_native_pydantic_receipts_are_json_serializable(capsys):
    from corsair.contracts import BatchItem

    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    terminal.emit([BatchItem(case_id="case1", run_id="run1", error="unavailable")])
    assert json.loads(capsys.readouterr().out)[0]["case_id"] == "case1"


async def test_execute_dispatches_report_without_runtime_services(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {"attempts": 1, "failed": 0}}))

    args = parser().parse_args(["--format", "json", "report", str(report)])

    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out) == {"attempts": 1, "failed": 0}


async def test_eval_saves_the_loaded_dataset_digest(tmp_path, monkeypatch, capsys):
    from corsair.adapters.temporal import client as temporal_client
    from corsair.contracts import BatchItem, digest
    from corsair.entrypoints import api
    from corsair.evaluation.scoring import load_dataset
    from corsair.settings import Settings

    class Handle:
        id = "eval-provenance"

        async def query(self, _query):
            return {"completed": 1, "total": 1}

    dataset_path = Path(__file__).resolve().parents[2] / "evals/datasets/dev.json"
    dataset, _, _ = load_dataset(dataset_path)

    async def connect(_settings):
        return object()

    async def start_evaluation(_client, _batch, _settings):
        return Handle()

    async def wait_for_result(_handle):
        return [BatchItem(case_id="case01", run_id="eval-provenance-case01", error="unavailable")]

    monkeypatch.setattr(
        "corsair.entrypoints.cli._settings",
        lambda _: Settings(artifact_root=str(tmp_path / "artifacts")),
    )
    monkeypatch.setattr(temporal_client, "connect", connect)
    monkeypatch.setattr(temporal_client, "wait_for_result", wait_for_result)
    monkeypatch.setattr(api, "start_evaluation", start_evaluation)
    report = tmp_path / "evaluation.json"
    args = parser().parse_args(
        [
            "--format",
            "json",
            "eval",
            str(dataset_path),
            "--run-id",
            "eval-provenance",
            "--output",
            str(report),
        ]
    )

    assert await execute(args) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["unavailable_results"] == 1
    assert json.loads(report.read_text())["dataset_digest"] == digest(dataset)


async def test_rescore_saves_the_loaded_dataset_digest(tmp_path, monkeypatch, capsys):
    from corsair.contracts import digest
    from corsair.entrypoints import cli
    from corsair.evaluation.scoring import load_dataset
    from corsair.settings import Settings

    dataset_path = Path(__file__).resolve().parents[2] / "evals/datasets/dev.json"
    dataset, _, _ = load_dataset(dataset_path)
    monkeypatch.setattr(
        cli, "_settings", lambda _: Settings(artifact_root=str(tmp_path / "artifacts"))
    )
    monkeypatch.setattr(
        cli,
        "_score_saved_result",
        lambda _store, identity, _oracles: {"run_id": identity, "status": "pass"},
    )
    report = tmp_path / "rescored.json"
    args = parser().parse_args(
        [
            "--format",
            "json",
            "rescore",
            str(dataset_path),
            "rescore-provenance",
            "--output",
            str(report),
        ]
    )

    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["passed"] == 1
    assert json.loads(report.read_text())["dataset_digest"] == digest(dataset)


async def test_inspect_rejects_watch_before_loading_or_creating_runtime_state():
    args = parser().parse_args(["inspect", "run1", "--watch"])

    with pytest.raises(ValueError, match="--watch requires --online"):
        await execute(args)


def test_run_id_rejects_invalid_or_reserved_length_values():
    with pytest.raises(ValidationError):
        validate_run_id("invalid/id")
    with pytest.raises(ValueError, match="operation suffixes"):
        validate_run_id("a" * 61)


def test_cli_exit_does_not_retain_handled_exception_tracebacks(tmp_path):
    # A test-only context observer invokes the actual main function, without fake responses.
    probe = (
        "import json\n"
        "from corsair.entrypoints.cli import main\n"
        "try:\n"
        "    main()\n"
        "except SystemExit as exit:\n"
        "    print(json.dumps({'code': exit.code, 'context_released': exit.__context__ is None}))\n"
        "    raise\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, "report", str(tmp_path / "absent"), "--log-format", "json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"code": 2, "context_released": True}
    assert json.loads(result.stderr.splitlines()[-1])["event"] == "cli.failed"


def test_client_only_operations_do_not_import_worker_or_adk_composition():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import corsair.adapters.temporal.client; "
            "assert 'corsair.entrypoints.worker' not in sys.modules; "
            "assert not any(name.startswith('google.adk') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


_NOW = datetime(2026, 10, 25, 12, 4, 30, tzinfo=UTC)


def _status(phase: str, session: int, round_index: int, **extra: object) -> dict[str, object]:
    timeline = [
        {"phase": "prepare", "session": 0, "round": 0, "at": "2026-10-25T12:00:00+00:00"},
        {"phase": "producer", "session": 1, "round": 1, "at": "2026-10-25T12:00:05+00:00"},
    ]
    return {
        "phase": phase,
        "session": session,
        "round": round_index,
        "max_sessions": 2,
        "max_rounds": 4,
        "gate": None,
        "started": "2026-10-25T12:00:00+00:00",
        "deadline": "2026-10-25T12:15:00+00:00",
        "timeline": timeline,
        **extra,
    }


def _scripted_query(statuses: list[dict[str, object]], done: asyncio.Event):
    """A fake native query that advances one status per poll, then completes the wait."""
    remaining = list(statuses)

    async def query():
        if len(remaining) == 1:
            done.set()
            return remaining[0]
        return remaining.pop(0)

    return query


async def _finish(done: asyncio.Event) -> str:
    await done.wait()
    return "final"


def test_progress_fields_come_only_from_status_and_local_time():
    fields = dict(progress_fields(_status("evidence", 1, 2, gate="coverage"), _NOW, 999.0))

    assert fields == {
        "elapsed": "04:30",
        "phase": "evidence",
        "session": "1/2",
        "round": "2/4",
        "last gate": "coverage",
        "deadline": "2026-10-25T12:15:00+00:00 (10:30 left)",
    }
    assert dict(progress_fields(None, _NOW, 7.0)) == {
        "elapsed": "00:07",
        "status": "waiting for the workflow status query",
    }
    batch = {"completed": 3, "total": 8, "running": 2, "errors": 1}
    assert dict(progress_fields(batch, _NOW, 65.0)) == {
        "elapsed": "01:05",
        "cases": "3/8",
        "running": "2",
        "errors": "1",
    }
    expired = dict(
        progress_fields(_status("audit", 1, 1), datetime(2026, 10, 25, 13, tzinfo=UTC), 0)
    )
    assert expired["deadline"].endswith("(passed)")


def test_progress_panel_renders_status_and_phase_timeline():
    status = _status("producer", 1, 1)
    console = Console(file=io.StringIO(), width=100, color_system=None, record=True)
    console.print(progress_panel("Investigation run1", status, progress_fields(status, _NOW, 0)))
    frame = console.export_text()

    assert "Corsair · Investigation run1" in frame
    assert "Session" in frame and "1/2" in frame
    assert "Round" in frame and "1/4" in frame
    assert "10:30 left" in frame
    assert "+00:00" in frame and "+00:05" in frame and "prepare" in frame


def test_progress_panel_bounds_the_timeline_to_recent_transitions():
    many = [
        {"phase": f"p{index}", "session": 1, "round": index, "at": "2026-10-25T12:00:00+00:00"}
        for index in range(12)
    ]
    status = _status("p11", 1, 11, timeline=many)
    console = Console(file=io.StringIO(), width=100, color_system=None, record=True)
    console.print(progress_panel("run", status, progress_fields(status, _NOW, 0)))
    frame = console.export_text()

    assert "… 4 earlier" in frame
    assert " p3 " not in frame and " p4 " in frame


async def test_plain_human_wait_prints_one_line_per_status_change(capsys, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "--no-animation", "report", "x"]))
    done = asyncio.Event()
    statuses = [
        _status("producer", 1, 1),
        _status("producer", 1, 1),
        _status("evidence", 1, 1),
        _status("audit", 1, 1, gate="coverage"),
    ]

    result = await terminal.wait(
        _finish(done), "Investigation run1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "\x1b" not in captured.err
    common = "session 1/2 · round 1/4"
    deadline = "deadline 2026-10-25T12:15:00+00:00 (10:30 left)"
    assert captured.err.splitlines() == [
        f"Investigation run1 · elapsed 04:30 · phase producer · {common} · {deadline}",
        f"Investigation run1 · elapsed 04:30 · phase evidence · {common} · {deadline}",
        f"Investigation run1 · elapsed 04:30 · phase audit · {common} · last gate coverage"
        f" · {deadline}",
    ]


async def test_json_wait_prints_no_progress_view(capsys, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    terminal = Terminal(parser().parse_args(["--format", "json", "report", "x"]))
    done = asyncio.Event()
    statuses = [_status("producer", 1, 1), _status("evidence", 1, 1)]

    result = await terminal.wait(
        _finish(done), "Investigation run1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "Investigation run1" not in captured.err and "session" not in captured.err
    assert "\x1b" not in captured.err


async def test_animated_wait_draws_the_live_panel_on_stderr(monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "report", "x"]))
    stream = io.StringIO()
    terminal.err = Console(file=stream, force_terminal=True, color_system=None, width=100)
    terminal.animate = True
    done = asyncio.Event()
    statuses = [_status("producer", 1, 1), _status("evidence", 1, 2)]

    result = await terminal.wait(_finish(done), "Evaluation", query=_scripted_query(statuses, done))
    frame = stream.getvalue()

    assert result == "final"
    assert "Corsair · Evaluation" in frame
    assert "evidence" in frame and "2/4" in frame
