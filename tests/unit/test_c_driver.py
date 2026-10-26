"""Pure-helper behavior of the trusted C driver, exercised without a container.

The driver's run is replaced by a fake that writes ``run.log`` and returns an exit
status, so these pin how the driver combines the sanitizer report text with the
process exit status. The real compile/run/coverage behavior is a Docker integration
concern (tests/integration/test_docker_c.py).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from corsair.adapters.sandboxing.drivers.c import driver

# Text a target can print itself with fprintf(stderr, ...) before returning normally.
FORGED_REPORT = (
    "==1==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x0\n"
    "    #0 0x0 in dup_n /source/dup.c:5\n"
)


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, value in {
        "WORK": tmp_path,
        "HARNESS": tmp_path / "harness.c",
        "PROG": tmp_path / "prog",
        "RUN_LOG": tmp_path / "run.log",
        "JOB_PATH": tmp_path / "job.json",
    }.items():
        monkeypatch.setattr(driver, name, value)
    return tmp_path


def _observation(work: Path, log: str, run_exit: int) -> str:
    (work / "run.log").write_text(log, encoding="utf-8")
    report = driver._sanitizer_report("dup.c", "heap-buffer-overflow")
    return driver._adversarial_observation(report, run_exit)


def test_report_text_with_a_normal_exit_is_operational_error(work: Path) -> None:
    # The target printed the report and returned: not the sanitizer's own halt.
    assert _observation(work, FORGED_REPORT, 0) == "execution_error"


def test_report_text_with_another_failing_exit_is_operational_error(work: Path) -> None:
    assert _observation(work, FORGED_REPORT, 1) == "execution_error"


def test_sanitizer_exit_without_a_target_bound_report_is_operational_error(work: Path) -> None:
    assert _observation(work, "", driver.ASAN_EXITCODE) == "execution_error"


def test_report_with_the_sanitizer_exit_status_is_a_sanitizer_report(work: Path) -> None:
    assert _observation(work, FORGED_REPORT, driver.ASAN_EXITCODE) == "sanitizer_report"


def test_clean_run_holds(work: Path) -> None:
    assert _observation(work, "", 0) == "held"


def test_forged_report_from_a_normally_returning_target_is_never_a_violation(
    work: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    job = {
        "schema_version": "corsair.driver-job/1",
        "operation_id": "op",
        "role": "adversarial",
        "source_digest": "a" * 64,
        "submission_digest": "b" * 64,
        "recipe": {
            "kind": "c.integer_overflow/1",
            "module_file": "dup.c",
            "function": "dup_n",
            "sanitizer_class": "heap-buffer-overflow",
        },
        "payload": 65535,
    }
    (work / "job.json").write_text(json.dumps(job), encoding="utf-8")

    def forged_run() -> int:
        (work / "run.log").write_text(FORGED_REPORT, encoding="utf-8")
        return 0

    compiled = subprocess.CompletedProcess(args=["gcc"], returncode=0)
    monkeypatch.setattr(driver, "_compile", lambda module_file: compiled)
    monkeypatch.setattr(driver, "_run", forged_run)
    monkeypatch.setattr(driver, "_coverage_lines", lambda module_file: [5])

    assert driver.main() == 2
    record = json.loads(capsys.readouterr().out)
    assert record["outcome"] == "ERROR"
    assert record["observation_kind"] == "execution_error"
    assert record["junit"]["status"] == "ERROR"
    assert record["target_executed"] is False
