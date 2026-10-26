"""Behavior of the local-stack developer script against real processes and stand-in CLIs.

The stand-in `temporal` and `uv` executables only listen on a port or write a readiness
line; they exercise process ownership, ports and settings, not Temporal or the worker.
"""

import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/local_stack.py"

FAKE_TEMPORAL = """
import signal, socket, sys, time
arguments = sys.argv[1:]
if arguments[:1] == ["operator"]:
    sys.exit(0)
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", int(arguments[arguments.index("--port") + 1])))
listener.listen()
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True:
    time.sleep(1)
"""

FAKE_UV = """
import os, pathlib, signal, sys, time
arguments = sys.argv[1:]
if "doctor" in arguments:
    print(os.environ["FAKE_DOCTOR_REPORT"])
    sys.exit(int(os.environ["FAKE_DOCTOR_EXIT"]))
if "worker" in arguments:
    events = pathlib.Path(arguments[arguments.index("--log-file") + 1])
    with events.open("a") as handle:
        handle.write('{"event": "worker.ready"}\\n')
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(1)
sys.exit(2)
"""


@pytest.fixture
def stack(tmp_path: Path) -> Iterator[Path]:
    """A repository-shaped root with the real settings template and stand-in CLIs."""

    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/settings.example.json").write_bytes(
        (ROOT / "deploy/settings.example.json").read_bytes()
    )
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    for name, body in (("temporal", FAKE_TEMPORAL), ("uv", FAKE_UV)):
        executable = bin_path / name
        executable.write_text(f"#!{sys.executable}\n{body}")
        executable.chmod(0o755)
    yield tmp_path
    for command in ("worker-down", "temporal-down"):
        if (tmp_path / ".state/settings.json").exists():
            run(tmp_path, command)


def run(root: Path, command: str, **environment: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}", **environment)
    return subprocess.run(
        [sys.executable, str(SCRIPT), command, "--root", str(root)],
        capture_output=True,
        env=env,
        text=True,
        timeout=120,
    )


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def accepting(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def settings(root: Path) -> dict:
    return json.loads((root / ".state/settings.json").read_text())


def configure_port(root: Path, port: int) -> None:
    assert run(root, "settings-init").returncode == 0
    values = settings(root)
    values["temporal_address"] = f"localhost:{port}"
    (root / ".state/settings.json").write_text(json.dumps(values))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_settings_init_writes_absolute_source_root_once(stack: Path):
    created = run(stack, "settings-init")
    assert created.returncode == 0, created.stderr
    values = settings(stack)
    assert values["source_root"] == str(stack.resolve())
    assert values["temporal_address"] == "localhost:7233"

    (stack / ".state/settings.json").write_text('{"operator": "edited"}')
    kept = run(stack, "settings-init")
    assert kept.returncode == 0, kept.stderr
    assert "never overwritten" in kept.stdout
    assert settings(stack) == {"operator": "edited"}


def test_temporal_up_is_idempotent_and_down_leaves_nothing_listening(stack: Path):
    port = free_port()
    configure_port(stack, port)

    started = run(stack, "temporal-up")
    assert started.returncode == 0, started.stderr
    pid = int((stack / ".state/temporal.pid").read_text())
    assert accepting(port)
    assert settings(stack)["temporal_address"] == f"localhost:{port}"

    again = run(stack, "temporal-up")
    assert again.returncode == 0, again.stderr
    assert "already running" in again.stdout
    assert int((stack / ".state/temporal.pid").read_text()) == pid

    stopped = run(stack, "temporal-down")
    assert stopped.returncode == 0, stopped.stderr
    assert not (stack / ".state/temporal.pid").exists()
    assert not alive(pid)
    assert not accepting(port)


def test_temporal_up_records_a_different_port_when_the_configured_one_answers(stack: Path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        taken = occupied.getsockname()[1]
        configure_port(stack, taken)

        started = run(stack, "temporal-up")
        assert started.returncode == 0, started.stderr
        chosen = int(settings(stack)["temporal_address"].rpartition(":")[2])
        assert chosen != taken
        assert accepting(chosen)
        assert "recorded temporal_address" in started.stdout
        assert run(stack, "temporal-down").returncode == 0
        assert not accepting(chosen)


def test_temporal_up_refuses_a_remote_address(stack: Path):
    assert run(stack, "settings-init").returncode == 0
    values = settings(stack)
    values["temporal_address"] = "temporal.example:7233"
    (stack / ".state/settings.json").write_text(json.dumps(values))

    refused = run(stack, "temporal-up")
    assert refused.returncode == 1
    assert "only a local development server" in refused.stderr
    assert not (stack / ".state/temporal.pid").exists()


def test_down_never_signals_a_process_it_did_not_start(stack: Path):
    configure_port(stack, free_port())
    (stack / ".state/temporal.pid").write_text(f"{os.getpid()}\n")

    result = run(stack, "temporal-down")
    assert result.returncode == 0, result.stderr
    assert "Removed stale" in result.stdout
    assert not (stack / ".state/temporal.pid").exists()


def test_worker_up_refuses_without_the_managed_temporal_server(stack: Path):
    assert run(stack, "settings-init").returncode == 0

    refused = run(stack, "worker-up")
    assert refused.returncode != 0
    assert "run `just temporal-up` first" in refused.stderr
    assert not (stack / ".state/worker.pid").exists()


def test_worker_up_waits_for_ready_event_and_down_stops_it(stack: Path):
    assert run(stack, "settings-init").returncode == 0
    assert run(stack, "temporal-up").returncode == 0

    started = run(stack, "worker-up")
    assert started.returncode == 0, started.stderr
    pid = int((stack / ".state/worker.pid").read_text())
    assert alive(pid)
    assert "already running" in run(stack, "worker-up").stdout

    stopped = run(stack, "worker-down")
    assert stopped.returncode == 0, stopped.stderr
    assert not alive(pid)
    assert not (stack / ".state/worker.pid").exists()


def doctor_report(*statuses: tuple[str, str]) -> str:
    checks = [{"name": name, "status": status, "detail": "d"} for name, status in statuses]
    return json.dumps({"ready": all(s == "pass" for _, s in statuses), "checks": checks})


def test_demo_doctor_tolerates_only_missing_worker_pollers(stack: Path):
    assert run(stack, "settings-init").returncode == 0
    waiting = doctor_report(("docker", "pass"), ("temporal", "pass"), ("worker_pollers", "warn"))
    tolerated = run(stack, "demo-doctor", FAKE_DOCTOR_REPORT=waiting, FAKE_DOCTOR_EXIT="1")
    assert tolerated.returncode == 0, tolerated.stderr
    assert "just worker-up" in tolerated.stdout

    broken = doctor_report(("docker", "fail"), ("temporal", "pass"), ("worker_pollers", "warn"))
    failed = run(stack, "demo-doctor", FAKE_DOCTOR_REPORT=broken, FAKE_DOCTOR_EXIT="1")
    assert failed.returncode == 1
    assert "doctor checks failed: docker" in failed.stderr
