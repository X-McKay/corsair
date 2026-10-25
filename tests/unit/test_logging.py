import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from corsair.observability.logging import JsonFormatter, MetadataFilter


def test_external_sdk_diagnostic_retains_type_not_request_content():
    try:
        raise RuntimeError("private request body and credentials")
    except RuntimeError:
        record = logging.LogRecord(
            "google.adk",
            logging.ERROR,
            __file__,
            10,
            "private request %s",
            ("raw prompt",),
            sys.exc_info(),
        )
    assert MetadataFilter().filter(record)
    diagnostic = JsonFormatter().format(record)
    row = json.loads(diagnostic)
    assert row["event"] == "sdk.diagnostic_content_omitted"
    assert row["logger"] == "google.adk"
    assert row["error_type"] == "RuntimeError"
    assert "private request" not in diagnostic and "raw prompt" not in diagnostic
    assert record.exc_info is None


def test_failed_log_file_setup_still_emits_jsonl_error(tmp_path):
    blocker = tmp_path / "not-directory"
    blocker.write_text("cannot create directory under file")
    command = subprocess.run(
        [
            str(Path(sys.executable).parent / "corsair"),
            "report",
            str(tmp_path / "report.json"),
            "--format",
            "json",
            "--log-format",
            "json",
            "--log-file",
            str(blocker / "output.jsonl"),
        ],
        capture_output=True,
        text=True,
    )
    assert command.returncode == 2
    assert command.stdout == ""
    errors = [json.loads(line) for line in command.stderr.splitlines()]
    assert errors[-1]["event"] == "cli.failed"
    assert errors[-1]["error_type"] == "FileExistsError"
    assert "Traceback" not in command.stderr


def test_new_log_file_permissions_are_restricted(tmp_path):
    report = tmp_path / "report.json"
    report.write_text('{"summary": {"attempts": 1}}')
    log = tmp_path / "restricted.jsonl"
    process = subprocess.run(
        [
            str(Path(sys.executable).parent / "corsair"),
            "report",
            str(report),
            "--format",
            "json",
            "--log-format",
            "json",
            "--log-file",
            str(log),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert log.exists()
    assert os.stat(log).st_mode & 0o077 == 0
