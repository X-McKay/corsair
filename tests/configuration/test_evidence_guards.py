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


def test_admission_refuses_a_replaced_cluster_before_kubernetes_access(tmp_path, monkeypatch):
    from tests.qualification import support
    (tmp_path / '.state/kind').mkdir(parents=True)
    (tmp_path / '.state/kind/owner.json').write_text(json.dumps({'container_id': 'original'}))
    monkeypatch.setattr(support, 'ROOT', tmp_path)
    calls = []
    def native(argv):
        calls.append(argv)
        return SimpleNamespace(stdout='replacement\n')
    client = SimpleNamespace(native=native)
    with pytest.raises(RuntimeError, match='identity changed'):
        support.require_owned_cluster(client)
    assert len(calls) == 1 and calls[0][2] == 'inspect'


def test_offline_chart_evidence_never_contains_secret_values():
    from deploy.openshell.artifacts import reviewed_render
    import yaml
    source = 'kind: Secret\ndata: {key: private-value}\nstringData: {other: private-text}\n---\nkind: ConfigMap\ndata: {config: harmless}\n'
    rendered = reviewed_render(source)
    assert 'private-value' not in rendered and 'private-text' not in rendered
    documents = list(yaml.safe_load_all(rendered))
    assert documents[0]['data']['key'] == '<redacted>'
    assert documents[1]['data']['config'] == 'harmless'
