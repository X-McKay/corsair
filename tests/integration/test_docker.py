from __future__ import annotations

import os
from pathlib import Path

import docker
import pytest
from docker.errors import DockerException

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import prepare_case
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Budget,
    Case,
    EvidenceInput,
    Finding,
    PlanRevision,
    PythonRecipe,
    RunManifest,
    Source,
    Submission,
)
from corsair.policies.verdicts import fix_status
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

pytestmark = pytest.mark.docker


VULNERABLE = """from pathlib import Path


def read_file(root, path):
    return (Path(root) / path).read_text()
"""

SAFE = """from pathlib import Path


def read_file(root, path):
    base = Path(root).resolve()
    candidate = (base / path).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("path escapes public fixtures")
    return candidate.read_text()
"""


def _docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get("corsair-python:0.1")
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires image: {type(exc).__name__}")
        pytest.skip(f"real Docker image unavailable: {type(exc).__name__}")
    return client


def _manifest(image_id: str) -> RunManifest:
    return RunManifest(
        package_version="0.1",
        request_digest="1" * 64,
        config_digest="2" * 64,
        producer_prompt_digest="3" * 64,
        auditor_prompt_digest="4" * 64,
        image_id=image_id,
        models={"producer": "test", "auditor": "test"},
    )


def _submission() -> Submission:
    return Submission(
        control_payload="hello.txt",
        exploit_payload="../private/secret.txt",
        hypothesis="join permits traversal",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _prepared(tmp_path: Path, image_id: str, *, safe: bool = False, fixed: bool = False):
    vulnerable = tmp_path / "vulnerable"
    vulnerable.mkdir(parents=True)
    (vulnerable / "reader.py").write_text(SAFE if safe else VULNERABLE, encoding="utf-8")
    if fixed:
        fixed_dir = tmp_path / "fixed"
        fixed_dir.mkdir()
        (fixed_dir / "reader.py").write_text(SAFE, encoding="utf-8")
    recipe = PythonRecipe(
        module_file="reader.py",
        function="read_file",
        payload_parameter="path",
        fixed_kwargs={"root": "/fixtures/allowed"},
        public_files={"hello.txt": "hello"},
        expected_control="hello",
        allowed_exceptions=["builtins.ValueError"],
    )
    case = Case(
        case_id="docker-case",
        finding=Finding(title="traversal", description="fixture read", file="reader.py", line=4),
        source=Source(path="vulnerable"),
        fixed_source=Source(path="fixed") if fixed else None,
        recipe=recipe,
    )
    settings = Settings(
        source_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        image="corsair-python:0.1",
        runtime="runc",
    )
    store = ArtifactStore(tmp_path / "artifacts")
    return settings, store, prepare_case(case, settings, store, _manifest(image_id))


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def test_real_docker_vulnerable_safe_fixed_and_cleanup(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id

    settings, store, vulnerable = _prepared(tmp_path / "vulnerable-case", image_id)
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    vulnerable_observation = verifier.evaluate(
        EvidenceInput(
            run_id="run-vulnerable",
            operation_id="docker-vulnerable",
            prepared=vulnerable,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert vulnerable_observation.cleanup_confirmed is True
    assert vulnerable_observation.control
    assert vulnerable_observation.control.outcome.value == "PROPERTY_HELD"
    assert vulnerable_observation.adversarial
    assert vulnerable_observation.adversarial.outcome.value == "VIOLATION"
    _assert_cleanup(client, "docker-vulnerable")

    safe_root = tmp_path / "safe-case"
    settings, store, safe = _prepared(safe_root, image_id, safe=True)
    safe_verifier = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client=client, store=store)
    )
    safe_observation = safe_verifier.evaluate(
        EvidenceInput(
            run_id="run-safe",
            operation_id="docker-safe",
            prepared=safe,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert safe_observation.cleanup_confirmed is True
    assert safe_observation.adversarial
    assert safe_observation.adversarial.outcome.value == "PROPERTY_HELD"
    _assert_cleanup(client, "docker-safe")

    fixed_root = tmp_path / "fixed-case"
    settings, store, prepared = _prepared(fixed_root, image_id, fixed=True)
    fixed_verifier = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client=client, store=store)
    )
    fixed_observation = fixed_verifier.evaluate(
        EvidenceInput(
            run_id="run-fixed",
            operation_id="docker-fixed",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
            fixed=True,
        )
    )
    assert fixed_observation.cleanup_confirmed is True
    assert fix_status(fixed_observation).value == "DEMONSTRATION_BLOCKED"
    _assert_cleanup(client, "docker-fixed")


@pytest.mark.parametrize(
    "body,expected_control,expected_adversarial",
    [
        (
            '    if path == "hello.txt":\n        return "hello"\n'
            '    raise RuntimeError("unexpected")\n',
            "PROPERTY_HELD",
            "ERROR",
        ),
        (
            '    return "hello" if path == "hello.txt" else "fake-secret-marker"\n',
            "PROPERTY_HELD",
            "PROPERTY_HELD",
        ),
        (
            '    return "wrong-control" if path == "hello.txt" else "safe"\n',
            "INVALID",
            "PROPERTY_HELD",
        ),
        (
            '    if path == "hello.txt":\n        return "hello"\n'
            "    import json, pytest\n"
            "    from pathlib import Path\n"
            '    Path("/work/observation.json").write_text(json.dumps({"kind": "disclosure"}))\n'
            '    pytest.fail("manufactured failure; no returned private fixture")\n',
            "PROPERTY_HELD",
            "ERROR",
        ),
        (
            '    if path == "hello.txt":\n        return "hello"\n    raise SystemExit(1)\n',
            "PROPERTY_HELD",
            "ERROR",
        ),
    ],
)
def test_native_failures_and_canned_markers_never_become_positive(
    tmp_path, body, expected_control, expected_adversarial
):
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id
    settings, store, prepared = _prepared(tmp_path, image_id)
    (tmp_path / "vulnerable/reader.py").write_text("\n\n\ndef read_file(root, path):\n" + body)
    case = Case(
        case_id="regression",
        finding=prepared.finding,
        source=Source(path="vulnerable"),
        recipe=prepared.recipe,
    )
    prepared = prepare_case(case, settings, store, prepared.manifest)
    observation = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client, store=store)
    ).evaluate(
        EvidenceInput(
            run_id="regression",
            operation_id="regression-native",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=10),
        )
    )
    assert observation.cleanup_confirmed
    assert observation.control is not None
    assert observation.adversarial is not None
    assert observation.control.outcome.value == expected_control
    assert observation.adversarial.outcome.value == expected_adversarial
    assert observation.adversarial.outcome.value != "VIOLATION"
    _assert_cleanup(client, "regression-native")


def test_native_timeout_removes_owned_container(tmp_path):
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id
    settings, store, prepared = _prepared(tmp_path, image_id)
    (tmp_path / "vulnerable/reader.py").write_text(
        "\n\n\ndef read_file(root, path):\n    while True:\n        pass\n"
    )
    case = Case(
        case_id="timeout",
        finding=prepared.finding,
        source=Source(path="vulnerable"),
        recipe=prepared.recipe,
    )
    prepared = prepare_case(case, settings, store, prepared.manifest)
    observation = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client, store=store)
    ).evaluate(
        EvidenceInput(
            run_id="timeout",
            operation_id="timeout-native",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=1),
        )
    )
    assert observation.cleanup_confirmed
    assert observation.control is not None
    assert observation.control.outcome.value == "ERROR"
    _assert_cleanup(client, "timeout-native")
