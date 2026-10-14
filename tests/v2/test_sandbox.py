from __future__ import annotations

import os
from pathlib import Path

import pytest

from corsair.v2.contracts import ArtifactRef, ModelProfile, OperatorConfig, SandboxProfile
from corsair.v2.sandbox import Sandbox
from corsair.v2.storage import Store

IMAGE = "example.invalid/corsair/python@sha256:" + "a" * 64


def config(tmp_path: Path, *, gateway: str = "unit-registration") -> OperatorConfig:
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\nnetwork_policies: {}\n")
    os.chmod(policy, 0o600)
    # Identity-only unit fixture; no subprocess executes this file. Live native
    # gateway/CLI admission is tested separately and cannot use this fixture.
    cli = tmp_path / "openshell"
    cli.write_text("unit identity fixture, deliberately not an executable program\n")
    cli.chmod(0o700)
    return OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
                          sandbox=SandboxProfile(image=IMAGE, policy_path=str(policy), gateway=gateway,
                                                 cli_path=str(cli), workspace_root="/workspace"))


def test_registered_gateway_not_plaintext_or_arbitrary_url(tmp_path):
    for endpoint in ("http://127.0.0.1:17670", "https://gateway.example.invalid:443"):
        with pytest.raises(ValueError):
            config(tmp_path, gateway=endpoint)
    assert Sandbox._registered_gateway("trusted-registration") == "trusted-registration"


def test_profile_identity_is_pinned_and_unqualified_without_certificate(tmp_path):
    with Store(tmp_path / "store") as store:
        sandbox = Sandbox(config(tmp_path), store)
        identity = sandbox.profile_identity()
        assert identity["image"] == IMAGE
        assert identity["policy_sha256"]
        assert identity["sdk_version"] == "0.1.3"
        assert identity["cli_sha256"]
        assert sandbox.qualified() is False


def test_command_result_retains_full_bounded_output_outside_temporal_payload(tmp_path):
    with Store(tmp_path / "store") as store:
        sandbox = Sandbox(config(tmp_path), store)
        stdout = "x" * (20 * 1024)
        result = sandbox._command_result(operation_id="operation", sandbox_id="sandbox", status="completed",
                                          exit_code=0, stdout=stdout, stderr="err", duration_seconds=0.01)
        assert len(result.stdout.encode()) == 16 * 1024
        assert store.get(result.stdout_ref) == stdout.encode()
        assert store.get(result.stderr_ref) == b"err"


def test_deterministic_name_binds_run_and_generation_with_native_length_limit(tmp_path):
    with Store(tmp_path / "store") as store:
        sandbox = Sandbox(config(tmp_path), store)
        assert sandbox._name("Run/One", 2) == sandbox._name("Run/One", 2)
        assert sandbox._name("Run/One", 2) != sandbox._name("Run/One", 3)
        assert sandbox._name("Run/One", 2) != sandbox._name("Run/Two", 2)
        assert len(sandbox._name("Run/One", 2)) <= 19
        labels = sandbox._labels("r" * 128, 2, ArtifactRef(sha256="e" * 64, size=0))
        assert all(len(value) <= 63 for value in labels.values())


def test_missing_cli_is_explicit_error(monkeypatch):
    monkeypatch.setattr("corsair.v2.sandbox.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="CLI is unavailable"):
        Sandbox._find_cli()
