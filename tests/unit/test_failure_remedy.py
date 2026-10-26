import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import docker.errors
import pytest
from temporalio.service import RPCError, RPCStatusCode

from corsair.entrypoints.diagnostics import _failed_check
from corsair.entrypoints.terminal import Terminal, failure_remedy
from corsair.observability.logging import TextFormatter
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.ports.scm import SourceAdmissionError
from corsair.settings import load_settings


def _validation_error(text: str, tmp_path: Path) -> Exception:
    settings = tmp_path / "settings.json"
    settings.write_text(text)
    with pytest.raises(ValueError) as caught:
        load_settings(settings)
    return caught.value


def _rpc(message: str, status: RPCStatusCode) -> RPCError:
    return RPCError(message, status, b"")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileNotFoundError(2, "No such file or directory", "x.json"), "Check the path"),
        (IsADirectoryError(21, "Is a directory", "x"), "not a directory"),
        (PermissionError(13, "Permission denied", "x"), "permissions"),
        (json.JSONDecodeError("Expecting value", "", 0), "not valid JSON"),
        (
            SourceAdmissionError("absolute source is outside configured source_root"),
            "Set source_root",
        ),
        (
            SourceAdmissionError("source snapshot digest does not match expected_digest"),
            "never edit a frozen digest",
        ),
        (SourceAdmissionError("source path does not exist"), "source.path"),
        (SourceAdmissionError("configured source_root does not exist"), "existing, readable"),
        (SourceAdmissionError("source exceeds configured byte limit"), "source_limit_bytes"),
        (SourceAdmissionError("symbolic links are not admitted: a"), "regular files"),
        (
            SandboxUnavailable("trusted image unavailable; build deploy/python/Dockerfile"),
            "just images",
        ),
        (SandboxUnavailable("Docker client unavailable: DockerException"), "Docker daemon"),
        (docker.errors.ImageNotFound("No such image"), "just images"),
        (docker.errors.DockerException("Error while fetching server API version"), "DOCKER_HOST"),
        (_rpc("workflow not found for ID: r1", RPCStatusCode.NOT_FOUND), "temporal workflow list"),
        (_rpc("Namespace n is not found.", RPCStatusCode.NOT_FOUND), "namespace create"),
        (_rpc("connection lost", RPCStatusCode.UNAVAILABLE), "Start Temporal"),
        (RuntimeError("Failed client connect: Server connection error"), "temporal_address"),
        (TimeoutError(), "corsair doctor"),
        (ValueError("No committed result; use --online"), "artifact_root"),
    ],
)
def test_known_failure_classes_map_to_one_fixed_remedy(error, expected):
    remedy = failure_remedy(error)
    assert remedy is not None and expected in remedy


def test_validation_remedy_distinguishes_invalid_json_from_invalid_fields(tmp_path):
    malformed = failure_remedy(_validation_error("{", tmp_path))
    invalid = failure_remedy(_validation_error('{"pids_limit": 1, "colour": "x"}', tmp_path))
    assert malformed is not None and "not valid JSON" in malformed
    assert invalid is not None and "docs/reference/configuration.md" in invalid


@pytest.mark.parametrize(
    "error",
    [
        ValueError("report must contain a summary object"),
        KeyError("case01"),
        RuntimeError("something else"),
        SourceAdmissionError("source artifact contains duplicate members"),
        _rpc("denied", RPCStatusCode.PERMISSION_DENIED),
    ],
)
def test_unknown_failures_have_no_invented_remedy(error):
    assert failure_remedy(error) is None


def test_remedy_never_reflects_error_content():
    secret = "sk-private-value-never-echoed"
    for error in (
        SourceAdmissionError(f"source snapshot digest does not match expected_digest {secret}"),
        RuntimeError(f"Failed client connect: https://{secret}@host"),
        FileNotFoundError(2, "No such file", f"/{secret}.json"),
        _rpc(f"workflow not found for ID: {secret}", RPCStatusCode.NOT_FOUND),
    ):
        remedy = failure_remedy(error)
        assert remedy is not None and secret not in remedy


def test_text_log_puts_remedy_on_its_own_line():
    record = logging.LogRecord("corsair", logging.ERROR, "", 0, "cli.failed", (), None)
    record.fields = {"error_type": "ValueError", "message": "detail", "remedy": "do this"}
    assert TextFormatter().format(record) == (
        "cli.failed error_type=ValueError message=detail\nremedy: do this"
    )
    record.fields = {"error_type": "ValueError"}
    assert TextFormatter().format(record) == "cli.failed error_type=ValueError"


def test_doctor_check_carries_remedy_only_when_known(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "250")
    connect = _failed_check("temporal", RuntimeError("Failed client connect: refused"))
    unknown = _failed_check("source_root", ValueError("source_root must be a readable directory"))
    assert connect["detail"].startswith("RuntimeError: Failed client connect")
    assert "Start Temporal" in connect["remedy"]
    assert "remedy" not in unknown
    terminal = Terminal(
        argparse.Namespace(format="human", no_color=True, no_animation=True, log_format="text")
    )
    terminal.emit({"checks": [connect, unknown], "qualification": "infrastructure only"})
    output = capsys.readouterr().out
    assert "→ Start Temporal" in output and "readable directory" in output


def _corsair(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(Path(sys.executable).parent / "corsair"), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "COLUMNS": "200", "NO_COLOR": "1"},
    )


def test_main_reports_remedy_beside_original_error_in_json_logs(tmp_path):
    missing = tmp_path / "absent-settings.json"
    result = _corsair("inspect", "r1", "--settings", str(missing), "--log-format", "json")
    assert result.returncode == 2 and result.stdout == ""
    row = json.loads(result.stderr.splitlines()[-1])
    assert row["event"] == "cli.failed"
    assert row["error_type"] == "FileNotFoundError"
    assert str(missing) in row["message"]
    assert row["remedy"].startswith("Check the path")


def test_main_reports_remedy_on_its_own_line_in_text_logs(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"artifact_root": str(tmp_path / "runs")}))
    result = _corsair("inspect", "r1", "--settings", str(settings), "--no-animation")
    assert result.returncode == 2 and result.stdout == ""
    assert "cli.failed error_type=ValueError message=No committed result" in result.stderr
    assert "remedy: Check the run id and artifact_root" in result.stderr
    assert "Traceback" not in result.stderr


def test_main_omits_remedy_for_an_unmapped_failure(tmp_path):
    report = tmp_path / "report.json"
    report.write_text("[]")
    json_result = _corsair("report", str(report), "--log-format", "json")
    text_result = _corsair("report", str(report))
    row = json.loads(json_result.stderr.splitlines()[-1])
    assert row["event"] == "cli.failed" and "remedy" not in row
    assert "summary object" in text_result.stderr and "remedy:" not in text_result.stderr
