"""Provider navigation and passive composition are executable contracts."""

import importlib
import socket
import subprocess
from pathlib import Path

from corsair.ports.sandbox import Sandboxes
from corsair.ports.scm import SourceControl

ROOT = Path(__file__).resolve().parents[1] / "src/corsair/adapters"


def test_provider_implementations_live_under_capability_directories():
    for relative in (
        "scm/github.py",
        "scm/azure_devops.py",
        "scm/git.py",
        "sandbox/docker.py",
        "sandbox/openshell.py",
    ):
        assert (ROOT / relative).is_file()


def test_provider_factories_are_passive_and_implement_the_existing_ports(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("provider import or construction performed I/O")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    with monkeypatch.context() as files:
        files.setattr(Path, "read_text", denied)
        files.setattr(Path, "read_bytes", denied)
        for module in (
            "corsair.adapters.scm.github",
            "corsair.adapters.scm.azure_devops",
            "corsair.adapters.sandbox.openshell",
        ):
            importlib.reload(importlib.import_module(module))
        from corsair.adapters.sandbox import sandboxes
        from corsair.adapters.scm import source_control

        scm: SourceControl = source_control()
        assert callable(scm.acquire)
        backend = sandboxes("openshell")
        assert backend.provider == "openshell"
        assert isinstance(backend, Sandboxes)
