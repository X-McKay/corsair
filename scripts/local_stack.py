#!/usr/bin/env python3
"""Manage the local development stack: settings, a Temporal dev server and the worker.

Developer tooling only. It starts host processes the operator already runs by hand (the
`temporal` CLI and `corsair worker`), records their pid and log under `.state/`, and stops
only a process whose command line still matches the one it started. It never runs model
or target code and never edits settings it did not create, except to record a non-default
Temporal port it had to choose for its own dev server.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SETTINGS = Path(".state/settings.json")
TEMPLATE = Path("deploy/settings.example.json")
# Infrastructure checks that may fall short in the demo before a worker is started.
DEMO_TOLERATED_WARNINGS = frozenset({"worker_pollers"})


@dataclass(frozen=True)
class Service:
    """One background process: how to recognise it, where its pid and output live."""

    name: str
    marker: str
    pid_file: Path
    log_file: Path
    stop_seconds: float


TEMPORAL = Service(
    name="temporal",
    marker="temporal server start-dev",
    pid_file=Path(".state/temporal.pid"),
    log_file=Path(".state/temporal.log"),
    stop_seconds=20,
)
WORKER = Service(
    name="worker",
    marker="corsair worker",
    pid_file=Path(".state/worker.pid"),
    log_file=Path(".state/worker.console.log"),
    # The worker drains for up to 45 seconds after SIGTERM.
    stop_seconds=60,
)
WORKER_EVENTS = Path(".state/worker.log")


class StackError(RuntimeError):
    """An operator-facing failure; printed without a traceback."""


def settings_init(root: Path) -> Path:
    """Create the settings file from the template once, with an absolute source root."""

    target = root / SETTINGS
    if target.exists():
        print(f"Kept existing {SETTINGS}; it is never overwritten.")
        return target
    settings = json.loads((root / TEMPLATE).read_text())
    settings["source_root"] = str(root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Created {SETTINGS} from {TEMPLATE}; source_root={settings['source_root']}")
    return target


def _read_settings(root: Path) -> dict:
    path = root / SETTINGS
    if not path.exists():
        raise StackError(f"{SETTINGS} is missing; run `just settings-init` first")
    return json.loads(path.read_text())


def _temporal_endpoint(settings: dict) -> tuple[str, int]:
    host, separator, port = str(settings.get("temporal_address", "")).rpartition(":")
    host = host.strip("[]")
    if not separator or not port.isdigit():
        raise StackError("temporal_address must be host:port")
    if host not in LOCAL_HOSTS:
        raise StackError(
            f"temporal_address points at {host}, not this host; "
            "temporal-up manages only a local development server"
        )
    return host, int(port)


def _accepting(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _port_free(port: int) -> bool:
    """Whether a new loopback listener here would be the one that clients actually reach.

    Binding alone is not enough: a NAT rule (for example a Kubernetes hostPort or service
    load balancer) can forward localhost:7233 to another Temporal while the port stays
    bindable, and clients would then silently reach that other server.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return not _accepting(port)


def _free_port() -> int:
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if _port_free(port):
            return port
    raise StackError("found no free loopback port that nothing else answers on")


def _command_line(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def running_pid(root: Path, service: Service) -> int | None:
    """Return the recorded pid only while that process is still the one this script started."""

    pid_file = root / service.pid_file
    if not pid_file.exists():
        return None
    text = pid_file.read_text().strip()
    command = _command_line(int(text)) if text.isdigit() else None
    if command is not None and service.marker in command:
        return int(text)
    pid_file.unlink()
    print(f"Removed stale {service.pid_file}; that process is no longer the {service.name}.")
    return None


def _log_tail(root: Path, service: Service, lines: int = 20) -> str:
    path = root / service.log_file
    if not path.exists():
        return ""
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def _spawn(root: Path, service: Service, command: list[str]) -> subprocess.Popen[bytes]:
    (root / service.log_file).parent.mkdir(parents=True, exist_ok=True)
    with (root / service.log_file).open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (root / service.pid_file).write_text(f"{process.pid}\n")
    return process


def _await_ready(
    root: Path, service: Service, process: subprocess.Popen[bytes], ready, seconds: float
) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready():
            return
        if process.poll() is not None:
            (root / service.pid_file).unlink(missing_ok=True)
            raise StackError(
                f"{service.name} exited with status {process.returncode}; "
                f"last lines of {service.log_file}:\n{_log_tail(root, service)}"
            )
        time.sleep(0.2)
    stop(root, service)
    raise StackError(
        f"{service.name} was not ready within {seconds:.0f}s and was stopped; "
        f"last lines of {service.log_file}:\n{_log_tail(root, service)}"
    )


def temporal_up(root: Path, ready_seconds: float = 60) -> None:
    """Start one background dev server; pick a free port only if the configured one is taken."""

    settings = _read_settings(root)
    host, port = _temporal_endpoint(settings)
    pid = running_pid(root, TEMPORAL)
    if pid is not None:
        print(f"Temporal dev server already running: pid {pid}, {host}:{port}.")
        return
    temporal = shutil.which("temporal")
    if temporal is None:
        raise StackError("the temporal CLI is not on PATH; run inside `nix develop`")
    if not _port_free(port):
        chosen = _free_port()
        settings["temporal_address"] = f"{host}:{chosen}"
        (root / SETTINGS).write_text(json.dumps(settings, indent=2) + "\n")
        print(
            f"Port {port} is in use or already answered by another server; "
            f"recorded temporal_address={host}:{chosen} in {SETTINGS}."
        )
        port = chosen
    ui_port = port + 1000 if port + 1000 <= 65535 and _port_free(port + 1000) else _free_port()
    command = [
        temporal,
        "server",
        "start-dev",
        "--port",
        str(port),
        "--ui-port",
        str(ui_port),
        "--db-filename",
        str(root / ".state/temporal.db"),
    ]
    namespace = str(settings.get("temporal_namespace", "default"))
    if namespace != "default":  # The dev server always creates "default" itself.
        command += ["--namespace", namespace]

    def ready() -> bool:
        if not _accepting(port):
            return False
        describe = [temporal, "operator", "namespace", "describe"]
        describe += ["--address", f"127.0.0.1:{port}", "--namespace", namespace]
        return subprocess.run(describe, capture_output=True, check=False).returncode == 0

    process = _spawn(root, TEMPORAL, command)
    _await_ready(root, TEMPORAL, process, ready, ready_seconds)
    print(
        f"Temporal dev server running: pid {process.pid}, {host}:{port}, "
        f"UI http://localhost:{ui_port}, log {TEMPORAL.log_file}."
    )


def worker_up(root: Path, ready_seconds: float = 120) -> None:
    """Start the worker in the background with the repository settings and a JSONL log."""

    _read_settings(root)
    pid = running_pid(root, WORKER)
    if pid is not None:
        print(f"Corsair worker already running: pid {pid}.")
        return
    uv = shutil.which("uv")
    if uv is None:
        raise StackError("uv is not on PATH; run inside `nix develop`")
    events = root / WORKER_EVENTS
    offset = events.stat().st_size if events.exists() else 0

    def ready() -> bool:
        if not events.exists():
            return False
        with events.open("rb") as handle:
            handle.seek(offset)
            return b"worker.ready" in handle.read()

    command = [
        uv,
        "run",
        "--locked",
        "--extra",
        "providers",
        "corsair",
        "worker",
        "--settings",
        str(root / SETTINGS),
        "--log-level",
        "INFO",
        "--log-file",
        str(events),
    ]
    process = _spawn(root, WORKER, command)
    _await_ready(root, WORKER, process, ready, ready_seconds)
    print(
        f"Corsair worker running: pid {process.pid}, events {WORKER_EVENTS}, "
        f"console {WORKER.log_file}. Provider credentials come from this environment."
    )


def _group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _await_exit(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _group_alive(pid):
            return True
        time.sleep(0.2)
    return not _group_alive(pid)


def stop(root: Path, service: Service) -> None:
    """Stop the recorded process group: SIGTERM, then SIGKILL, then confirm it is gone."""

    pid = running_pid(root, service)
    if pid is None:
        print(f"No {service.name} recorded as running.")
        return
    os.killpg(pid, signal.SIGTERM)
    if not _await_exit(pid, service.stop_seconds):
        os.killpg(pid, signal.SIGKILL)
        if not _await_exit(pid, 10):
            raise StackError(f"{service.name} process group {pid} survived SIGKILL")
    (root / service.pid_file).unlink(missing_ok=True)
    print(f"Stopped {service.name} (process group {pid}); confirmed no member remains.")


def temporal_down(root: Path) -> None:
    stop(root, TEMPORAL)
    settings_path = root / SETTINGS
    if settings_path.exists():
        _, port = _temporal_endpoint(json.loads(settings_path.read_text()))
        if _accepting(port):
            print(f"Note: something else still listens on port {port}; it was not started here.")


def demo_doctor(root: Path) -> None:
    """Run `corsair doctor`; before a worker exists only missing pollers may fall short."""

    uv = shutil.which("uv")
    if uv is None:
        raise StackError("uv is not on PATH; run inside `nix develop`")
    result = subprocess.run(
        [uv, "run", "--locked", "corsair", "--format", "json", "doctor"]
        + ["--settings", str(root / SETTINGS)],
        cwd=root,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise StackError(f"doctor printed no JSON report (exit {result.returncode})") from error
    for check in report["checks"]:
        print(f"  {check['status']:<5} {check['name']:<15} {check['detail']}")
    blocking = [
        check["name"]
        for check in report["checks"]
        if check["status"] != "pass"
        and not (check["status"] == "warn" and check["name"] in DEMO_TOLERATED_WARNINGS)
    ]
    if blocking:
        raise StackError(f"doctor checks failed: {', '.join(blocking)}")
    if not report["ready"]:
        print("  Not ready for investigate until `just worker-up` registers pollers.")


COMMANDS = {
    "settings-init": settings_init,
    "temporal-up": temporal_up,
    "temporal-down": temporal_down,
    "worker-up": worker_up,
    "worker-down": lambda root: stop(root, WORKER),
    "demo-doctor": demo_doctor,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        COMMANDS[args.command](args.root.resolve())
    except StackError as error:
        print(f"{args.command}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
