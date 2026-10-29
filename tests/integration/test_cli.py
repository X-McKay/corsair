"""Real console processes and SDK infrastructure; no model response is mocked here."""

import asyncio
import json
import os
import pty
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from corsair.settings import Settings
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.docker, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]
ROOT = Path(__file__).resolve().parents[2]
CLI = Path(sys.executable).parent / "corsair"


async def _command(*args, timeout=30):
    process = await asyncio.create_subprocess_exec(
        str(CLI),
        *map(str, args),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    async with asyncio.timeout(timeout):
        stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.parametrize(
    ("option", "value"),
    [("repeats", 0), ("repeats", 9), ("concurrency", 0), ("concurrency", 9)],
)
async def test_real_cli_rejects_eval_bounds_before_handler_io(tmp_path, option, value):
    missing_dataset = tmp_path / "unread-dataset.json"
    missing_settings = tmp_path / "unread-settings.json"

    code, stdout, stderr = await _command(
        "eval",
        missing_dataset,
        "--settings",
        missing_settings,
        f"--{option}",
        value,
    )

    assert code == 2
    assert stdout == ""
    assert f"argument --{option}: invalid choice: '{value}'" in stderr
    assert "cli.failed" not in stderr
    assert not missing_dataset.exists()
    assert not missing_settings.exists()


async def test_real_cli_worker_doctor_and_native_reference(temporal_server, tmp_path):
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for native CLI testing")
    settings = Settings(
        source_root=str(ROOT),
        artifact_root=str(tmp_path / "artifacts"),
        images={"python.secret_disclosure/1": "corsair-python:0.1"},
        temporal_address=temporal_server.client.service_client.config.target_host,
        task_queue=temporal_id("cli-worker"),
    )
    config = tmp_path / "settings.json"
    config.write_text(settings.model_dump_json())
    worker_log = tmp_path / "worker.jsonl"
    with worker_log.open("wb") as output:
        worker = subprocess.Popen(
            [
                str(CLI),
                "worker",
                "--settings",
                str(config),
                "--format",
                "json",
                "--log-format",
                "json",
            ],
            stdout=subprocess.DEVNULL,
            stderr=output,
        )
        try:
            async with asyncio.timeout(20):
                while '"worker.ready"' not in worker_log.read_text():
                    assert worker.poll() is None, worker_log.read_text()
                    await asyncio.sleep(0.1)
            code, stdout, stderr = await _command(
                "doctor",
                "--settings",
                config,
                "--format",
                "json",
                "--log-format",
                "json",
            )
            assert code == 0, stderr + stdout
            report = json.loads(stdout)
            assert report["ready"]
            assert any(check["name"] == "worker_pollers" for check in report["checks"])
            assert "not tested" in report["qualification"]
            assert "\x1b" not in stdout + stderr
            log_file = tmp_path / "reference.jsonl"
            code, stdout, stderr = await _command(
                "verify",
                ROOT / "evals/fixtures/case01/request.json",
                ROOT / "evals/fixtures/case01/submission.json",
                "--settings",
                config,
                "--format",
                "json",
                "--log-format",
                "json",
                "--log-file",
                log_file,
            )
            assert code == 0, stderr + stdout
            native = json.loads(stdout)
            assert native["adversarial"]["outcome"] == "VIOLATION"
            assert native["cleanup_confirmed"]
            events = [json.loads(line) for line in stderr.splitlines()]
            assert events[0]["event"] == "reference.started"
            assert events[-1]["event"] == "reference.completed"
            assert [json.loads(line) for line in log_file.read_text().splitlines()] == events
        finally:
            worker.send_signal(signal.SIGTERM)
            await asyncio.to_thread(worker.wait, 50)
    assert worker.returncode == 0, worker_log.read_text()
    events = [json.loads(line)["event"] for line in worker_log.read_text().splitlines()]
    assert events[:2] == ["worker.connecting", "worker.ready"]
    assert events[-2:] == ["worker.stopping", "worker.stopped"]


async def test_real_cli_reference_in_pseudo_terminal_has_animation(tmp_path):
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for native terminal testing")
    config = tmp_path / "settings.json"
    config.write_text(
        Settings(source_root=str(ROOT), artifact_root=str(tmp_path / "artifacts")).model_dump_json()
    )
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [
            str(CLI),
            "verify",
            str(ROOT / "evals/fixtures/case01/request.json"),
            str(ROOT / "evals/fixtures/case01/submission.json"),
            "--settings",
            str(config),
            "--format",
            "human",
        ],
        stdin=subprocess.DEVNULL,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color", "FORCE_COLOR": "1", "NO_COLOR": ""},
    )
    os.close(slave)

    def read_terminal():
        chunks = []
        try:
            while True:
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            pass
        finally:
            os.close(master)
        return b"".join(chunks).decode()

    async with asyncio.timeout(30):
        rendered = await asyncio.to_thread(read_terminal)
        await asyncio.to_thread(process.wait)
    assert process.returncode == 0, rendered
    assert "\x1b[?25l" in rendered  # Rich hides/restores cursor around a real status animation.
    assert "\x1b[?25h" in rendered
    assert "\x1b[" in rendered
    assert "Native reference observation" in rendered and "violated" in rendered
    assert "reference.started" in rendered and "reference.completed" in rendered


@pytest.mark.parametrize(
    "boundary", ["image", "runtime", "source_root", "artifact_root", "namespace", "daemon"]
)
async def test_real_doctor_reports_failed_dependency(
    temporal_server, tmp_path, boundary, monkeypatch
):
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for actual dependency diagnosis")
    values = {
        "source_root": str(ROOT),
        "artifact_root": str(tmp_path / "artifacts"),
        "temporal_address": temporal_server.client.service_client.config.target_host,
        "task_queue": temporal_id("no-worker"),
    }
    failed_check = "docker"
    if boundary == "image":
        values["image"] = "corsair-deliberately-missing:diagnostic"
        failed_check = "image:corsair-deliberately-missing:diagnostic"
    elif boundary == "runtime":
        values["runtime"] = "deliberately-unregistered-runtime"
    elif boundary == "source_root":
        values["source_root"] = str(tmp_path / "missing-source")
        failed_check = "source_root"
    elif boundary == "artifact_root":
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("file not directory")
        values["artifact_root"] = str(blocker)
        failed_check = "artifact_root"
    elif boundary == "namespace":
        values["temporal_namespace"] = temporal_id("no-namespace")
        failed_check = "temporal"
    else:
        monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/absent.sock")
    config = tmp_path / "settings.json"
    config.write_text(Settings.model_validate(values).model_dump_json())
    code, stdout, stderr = await _command(
        "doctor",
        "--settings",
        config,
        "--format",
        "json",
        "--log-format",
        "json",
    )
    assert code == 1, stdout + stderr
    report = json.loads(stdout)
    assert not report["ready"]
    assert any(
        check["name"] == failed_check and check["status"] == "fail" for check in report["checks"]
    )
    assert not (tmp_path / "artifacts").exists()  # doctor is read-only even on failed preflight.


@pytest.mark.parametrize("presentation", ["json", "human", "pty"])
async def test_ctrl_c_detaches_real_temporal_client_without_cancelling_workflow(
    temporal_server, tmp_path, presentation
):
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.worker import Worker

    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import InvestigationResult
    from corsair.workflows.investigation import InvestigationWorkflow
    from tests.workflow.temporal import ActivityScenario, FakeActivities

    # The provider is intentionally paused via a labelled test activity, not a production fallback.
    settings = Settings(
        source_root=str(ROOT),
        artifact_root=str(tmp_path / "artifacts"),
        temporal_address=temporal_server.client.service_client.config.target_host,
        task_queue=temporal_id("detach-queue"),
    )
    config = tmp_path / "settings.json"
    config.write_text(settings.model_dump_json())
    activities = FakeActivities(
        ArtifactStore(settings.artifact_root), ActivityScenario(pause_produce=True)
    )
    identity = temporal_id("detach-run")
    async with Worker(
        temporal_server.client,
        task_queue=settings.task_queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        diagnostics = tmp_path / "client.jsonl"
        stdout_path, stderr_path = tmp_path / "stdout.json", tmp_path / "stderr.jsonl"
        handle = temporal_server.client.get_workflow_handle(
            identity, result_type=InvestigationResult
        )
        master, slave = pty.openpty() if presentation == "pty" else (None, None)

        def drain_terminal():
            assert master is not None
            chunks = []
            try:
                while data := os.read(master, 65536):
                    chunks.append(data)
            except OSError:
                pass
            finally:
                os.close(master)
            return b"".join(chunks).decode()

        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                [
                    str(CLI),
                    "investigate",
                    str(ROOT / "evals/fixtures/case01/request.json"),
                    "--run-id",
                    identity,
                    "--wait",
                    "--settings",
                    str(config),
                    "--format",
                    "json" if presentation == "json" else "human",
                    "--log-format",
                    "text" if presentation == "pty" else "json",
                    "--log-file",
                    str(diagnostics),
                ],
                stdout=slave if slave is not None else stdout_file,
                stderr=slave if slave is not None else stderr_file,
                env={**os.environ, "PYTHONFAULTHANDLER": "1", "TERM": "xterm-256color"},
            )
            terminal_read = None
            if slave is not None:
                os.close(slave)
                terminal_read = asyncio.create_task(asyncio.to_thread(drain_terminal))
            try:
                async with asyncio.timeout(15):
                    await activities.produce_started.wait()
                    while '"workflow.progress"' not in diagnostics.read_text():
                        assert process.poll() is None
                        await asyncio.sleep(0.05)
                status = Path(f"/proc/{process.pid}/status")
                if status.exists():
                    fields = dict(line.split(":", 1) for line in status.read_text().splitlines())
                    assert not int(fields["SigIgn"], 16) & (1 << (signal.SIGINT - 1)), (
                        "The installed CLI inherited ignored SIGINT from its launcher"
                    )
                process.send_signal(signal.SIGINT)
                try:
                    await asyncio.to_thread(process.wait, 10)
                except subprocess.TimeoutExpired:
                    # Failure-only forensic capture from the actual installed console process.
                    status = Path(f"/proc/{process.pid}/status")
                    signals = status.read_text() if status.exists() else "no proc signal metadata"
                    process.send_signal(signal.SIGABRT)
                    await asyncio.to_thread(process.wait, 10)
                    raise AssertionError(
                        f"CLI did not detach after SIGINT. {signals}\n{stderr_path.read_text()}"
                    ) from None
                assert process.returncode == 130, stderr_path.read_text()
                assert stdout_path.read_bytes() == b""
                assert (
                    json.loads(diagnostics.read_text().splitlines()[-1])["event"]
                    == "cli.interrupted"
                )
                if terminal_read is not None:
                    output = await terminal_read
                    assert "\x1b[?25l" in output and "\x1b[?25h" in output
                    from rich.text import Text

                    plain = " ".join(Text.from_ansi(output).plain.replace("│", " ").split())
                    assert "Detached" in plain and "--online --watch" in plain
                elif presentation == "human":
                    output = stderr_path.read_text()
                    assert "Detached" in output and "--online --watch" in output
                    assert "\x1b" not in output
                assert (await handle.describe()).status == WorkflowExecutionStatus.RUNNING
            finally:
                if process.poll() is None:
                    process.kill()
                    await asyncio.to_thread(process.wait, 10)
                if terminal_read is not None:
                    await terminal_read
                await handle.cancel()
        # Temporal learns activity cancellation through throttled heartbeats (<=15s here).
        async with asyncio.timeout(25):
            result = await handle.result()
        assert result.execution_status.value == "CANCELLED"
