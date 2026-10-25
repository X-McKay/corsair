import ast
import asyncio
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.cli import execute, parser, validate_run_id
from corsair.observability.logging import JsonFormatter, MetadataFilter, event
from corsair.runtime.terminal import Terminal


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
        "from corsair.cli import main\n"
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
