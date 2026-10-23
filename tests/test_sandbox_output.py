"""The synchronous sandbox path bounds untrusted stdout and stderr before they reach host memory."""
import sys
import time

import corsair.sandbox.docker as docker_sandbox
from corsair.sandbox.port import Exec
from corsair.sandbox.docker import _bounded_process


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
