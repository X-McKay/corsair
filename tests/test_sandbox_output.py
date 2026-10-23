"""The synchronous sandbox path bounds untrusted stdout and stderr before they reach host memory."""
import subprocess
import sys
import time
from pathlib import Path

import pytest

import corsair.sandbox.docker as docker_sandbox
from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case
from corsair.frameworks import framework
from corsair.kernel import Fix, Gate, Kernel, Label, RoleResult, Submission, terminal_verdict
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import MAX_OUTPUT_BYTES, docker, docker_available
from corsair.sandbox.port import Exec
from corsair.sandbox.docker import _bounded_process
from tests.test_kernel import accept


ROOT = Path(__file__).resolve().parents[1]
PYTHON_CASE = ROOT / "cases/path-traversal-fixture"


def test_bounded_process_stops_at_the_combined_output_limit():
    command = [sys.executable, "-c", "import os; os.write(1, b'x' * 4096); os.write(2, b'y' * 4096)"]
    result = _bounded_process(command, timeout=5, limit=1024)
    assert result.output_limited and result.exit_code is None and not result.timed_out
    assert len(result.stdout) + len(result.stderr) == 1024


def test_bounded_process_preserves_normal_exit_and_streams():
    command = [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"]
    result = _bounded_process(command, timeout=5, limit=1024)
    assert result.exit_code == 0 and result.stdout == b"out\n" and result.stderr == b"err\n"
    assert not result.output_limited and not result.timed_out


def test_bounded_process_applies_deadline_after_streams_close():
    command = [sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(2)"]
    started = time.monotonic()
    result = _bounded_process(command, timeout=0.1, limit=1024)
    assert result.timed_out and result.exit_code is None
    assert time.monotonic() - started < 1


def test_exec_once_kills_in_container_process_after_local_timeout(monkeypatch):
    commands = []

    def bounded(argv, *, timeout):
        commands.append(list(argv))
        return Exec(None, b"", b"", timed_out=True)

    controls = []
    monkeypatch.setattr(docker_sandbox, "_bounded_process", bounded)
    monkeypatch.setattr(docker_sandbox, "docker", lambda *args, **kwargs: controls.append(args))

    result = docker_sandbox.exec_once("box", ["sleep", "99"], workdir="/work", timeout=0.1)

    assert result.timed_out
    assert commands[0][0:4] == ["docker", "exec", "-w", "/work"]
    assert "sh" in commands[0] and "sleep" in commands[0]
    assert controls and controls[0][0:3] == ("exec", "-w", "/")


def test_exec_once_kills_in_container_process_after_local_output_overflow(monkeypatch):
    commands = []

    def bounded(argv, *, timeout):
        commands.append(list(argv))
        return Exec(None, b"x" * 16, b"y" * 16, output_limited=True)

    controls = []
    monkeypatch.setattr(docker_sandbox, "_bounded_process", bounded)
    monkeypatch.setattr(docker_sandbox, "docker", lambda *args, **kwargs: controls.append(args))

    result = docker_sandbox.exec_once("box", ["python", "flood.py"], workdir="/work", timeout=1)

    assert result.output_limited and not result.timed_out
    assert commands[0][0:4] == ["docker", "exec", "-w", "/work"]
    assert controls and controls[0][0:3] == ("exec", "-w", "/")


class ChildOutputFloodingDocker(DockerSandboxes):
    """Replace only the primary native command with a real waited child that floods both streams."""

    def __init__(self, target_file):
        super().__init__()
        self.primary = tuple(framework("pytest").command("control", target_file))
        self.post = tuple(framework("pytest").post_command("control", target_file).argv)
        self.primary_results = []
        self.post_attempts = 0
        self.started = []
        self.removed = []

    def open_environment(self, image, workdir, sandbox_labels):
        name = super().open_environment(image, workdir, sandbox_labels)
        self.started.append(name)
        return name

    def exec_once(self, name, argv, *, workdir, env=None, timeout=None):
        if tuple(argv) == self.primary and env is not None and env.get("CORSAIR_ROLE") == "control":
            chunk = 64 * 1024
            writes = MAX_OUTPUT_BYTES // chunk + 16
            child = ("import os\n"
                     f"chunk = b'x' * {chunk}\n"
                     f"for index in range({writes}):\n"
                     "    os.write(1 if index % 2 == 0 else 2, chunk)\n")
            parent = ("import subprocess, sys\n"
                      f"child = {child!r}\n"
                      "process = subprocess.Popen([sys.executable, '-c', child])\n"
                      "raise SystemExit(process.wait())\n")
            result = super().exec_once(name, ["python", "-c", parent], workdir=workdir, env=env, timeout=timeout)
            self.primary_results.append(result)
            return result
        if tuple(argv) == self.post:
            self.post_attempts += 1
        return super().exec_once(name, argv, workdir=workdir, env=env, timeout=timeout)

    def remove(self, name):
        confirmed = super().remove(name)
        if name in self.started:
            self.removed.append((name, confirmed))
        return confirmed


@pytest.mark.docker
@pytest.mark.anyio
async def test_child_output_overflow_is_infra_and_cleans_up_without_postprocessing(tmp_path):
    row = matrix.select(load_case(PYTHON_CASE))
    if not (docker_available() and docker("image", "inspect", row.image).returncode == 0):
        pytest.skip(f"docker or {row.image} unavailable (make image)")
    submission = Submission.model_validate_json((PYTHON_CASE / "reference-submission.json").read_text())
    backend = ChildOutputFloodingDocker(submission.hypothesis.target_file)
    kernel = Kernel(backend, row, load_case(PYTHON_CASE), artifacts=ArtifactStore(tmp_path / "artifacts"),
                    auditor=accept, run_id=f"f{tmp_path.name[-8:]}".lower())

    evaluation = await kernel.evaluate(submission)

    assert evaluation.gate.stage is Gate.INFRA and "output limit" in evaluation.gate.reason
    assert terminal_verdict(evaluation.gate, 1).label is Label.ERROR
    assert evaluation.verdict is not None and evaluation.verdict.fix is Fix.NOT_VERIFIED
    assert len(evaluation.runs) == 1
    run = evaluation.runs[0]
    assert run.result is RoleResult.INFRA and run.invariant_held is None
    assert run.junit_tests == 0 and run.covered_target is None and run.covered_lines == ()
    assert run.junit is None and run.coverage is None and run.cleanup_confirmed is True
    assert backend.post_attempts == 0
    assert len(backend.primary_results) == 1
    observed = backend.primary_results[0]
    assert observed.output_limited and not observed.timed_out and not observed.container_failed
    assert len(observed.stdout) + len(observed.stderr) == MAX_OUTPUT_BYTES
    assert len(backend.started) == 1 and backend.removed
    assert all(name == backend.started[0] and confirmed for name, confirmed in backend.removed)
    assert backend.labelled(kernel.run_id) == []
