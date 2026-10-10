"""Test our two safety-critical receipt/ownership decisions, not CNI enforcement."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from tests.qualification.support import Kubectl, NetworkFixture


def test_timeout_retains_partial_output_and_unknown_completion(tmp_path, monkeypatch):
    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=b"partial", stderr=b"interrupted")

    monkeypatch.setattr(subprocess, "run", expired)
    client = Kubectl(tmp_path / "unused-config", "kind-corsair", tmp_path)
    with pytest.raises(RuntimeError, match="completion unknown"):
        client.run("get", "nodes", timeout=1)
    receipt = json.loads((tmp_path / "command-0001.json").read_text())
    assert receipt["timed_out"] is True and "exit_code" not in receipt
    assert receipt["stdout"] == "partial" and receipt["stderr"] == "interrupted"
    assert receipt["elapsed_seconds"] >= 0


def test_cleanup_cannot_delete_a_replacement_namespace(tmp_path):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    client = SimpleNamespace(evidence=tmp_path, run=run, get=lambda *args: {"metadata": {"uid": "replacement"}})
    fixture = NetworkFixture(client, "replacement-guard")
    fixture.uid = "original"
    with pytest.raises(RuntimeError, match="identity changed"):
        fixture.cleanup()
    assert not any(args[0] == "delete" for args in calls)
    receipt = json.loads((fixture.evidence / "cleanup.json").read_text())
    assert receipt["uid"] == "original" and receipt["confirmed"] is False
