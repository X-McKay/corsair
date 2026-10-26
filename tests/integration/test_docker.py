from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path

import docker
import pytest
from docker.errors import DockerException, NotFound
from docker.models.containers import Container

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

# Operation ids become the ``corsair.operation`` container label, and the
# operation-reconciliation gate refuses any operation whose label already exists on the
# daemon. Fixed ids would let concurrent suites on one daemon block each other, so every
# id here is ``pytest-<12 hex>.<label>`` with one random prefix per test session.
SESSION_OPERATION = re.compile(r"^pytest-[0-9a-f]{12}\.[a-z0-9-]+$")


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


def _image() -> str:
    """The trusted image under test: the configured tag, or a scratch build's tag."""
    return os.environ.get("CORSAIR_TEST_IMAGE", Settings().image)


def _docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get(_image())
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires image: {type(exc).__name__}")
        pytest.skip(f"real Docker image unavailable: {type(exc).__name__}")
    return client


def _session_containers(client: docker.DockerClient, prefix: str) -> list[Container]:
    """Return only the labelled sandboxes whose operation id carries this session's prefix."""
    containers = client.containers.list(all=True, filters={"label": "corsair.security=true"})
    return [
        container
        for container in containers
        if container.labels.get("corsair.operation", "").startswith(f"{prefix}.")
    ]


def _remove_session_containers(client: docker.DockerClient, prefix: str) -> list[str]:
    """Remove this session's leaked sandboxes by immutable id; never touch another prefix."""
    leaked = []
    for container in _session_containers(client, prefix):
        leaked.append(f"{container.labels['corsair.operation']}:{container.id[:12]}")
        client.api.remove_container(container.id, force=True)
    return leaked


@pytest.fixture(scope="session")
def session_operation() -> Iterator[Callable[[str], str]]:
    """Yield a factory for session-unique operation ids and fail on leaked sandboxes.

    A fresh prefix has no containers when the session starts, so the sweep runs at
    teardown: it removes only this session's own leftovers (other suites on the daemon
    may hold their identities) and reports them as a teardown error, never silently.
    """
    prefix = f"pytest-{uuid.uuid4().hex[:12]}"
    yield lambda label: f"{prefix}.{label}"
    try:
        client = docker.from_env()
        client.ping()
    except DockerException:
        return
    leaked = _remove_session_containers(client, prefix)
    assert leaked == [], f"session sandboxes survived their tests: {leaked}"


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
        image=_image(),
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


def test_real_docker_vulnerable_safe_fixed_and_cleanup(
    tmp_path: Path, session_operation: Callable[[str], str]
) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(image=_image()), client=client).image_id

    vulnerable_operation = session_operation("docker-vulnerable")
    safe_operation = session_operation("docker-safe")
    fixed_operation = session_operation("docker-fixed")
    assert all(
        SESSION_OPERATION.fullmatch(operation)
        for operation in (vulnerable_operation, safe_operation, fixed_operation)
    )
    settings, store, vulnerable = _prepared(tmp_path / "vulnerable-case", image_id)
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    vulnerable_observation = verifier.evaluate(
        EvidenceInput(
            run_id="run-vulnerable",
            operation_id=vulnerable_operation,
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
    _assert_cleanup(client, vulnerable_operation)

    safe_root = tmp_path / "safe-case"
    settings, store, safe = _prepared(safe_root, image_id, safe=True)
    safe_verifier = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client=client, store=store)
    )
    safe_observation = safe_verifier.evaluate(
        EvidenceInput(
            run_id="run-safe",
            operation_id=safe_operation,
            prepared=safe,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert safe_observation.cleanup_confirmed is True
    assert safe_observation.adversarial
    assert safe_observation.adversarial.outcome.value == "PROPERTY_HELD"
    _assert_cleanup(client, safe_operation)

    fixed_root = tmp_path / "fixed-case"
    settings, store, prepared = _prepared(fixed_root, image_id, fixed=True)
    fixed_verifier = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client=client, store=store)
    )
    fixed_observation = fixed_verifier.evaluate(
        EvidenceInput(
            run_id="run-fixed",
            operation_id=fixed_operation,
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
            fixed=True,
        )
    )
    assert fixed_observation.cleanup_confirmed is True
    assert fix_status(fixed_observation).value == "DEMONSTRATION_BLOCKED"
    _assert_cleanup(client, fixed_operation)


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
    tmp_path, body, expected_control, expected_adversarial, session_operation
):
    client = _docker_client()
    operation_id = session_operation("regression-native")
    image_id = DockerSandbox(Settings(image=_image()), client=client).image_id
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
            operation_id=operation_id,
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
    _assert_cleanup(client, operation_id)


def test_native_timeout_removes_owned_container(tmp_path, session_operation):
    client = _docker_client()
    operation_id = session_operation("timeout-native")
    image_id = DockerSandbox(Settings(image=_image()), client=client).image_id
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
            operation_id=operation_id,
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=1),
        )
    )
    assert observation.cleanup_confirmed
    assert observation.control is not None
    assert observation.control.outcome.value == "ERROR"
    _assert_cleanup(client, operation_id)


@pytest.mark.docker
@pytest.mark.long_probe
def test_real_docker_probe_deadline_can_exceed_120_seconds(
    tmp_path: Path, session_operation: Callable[[str], str]
) -> None:
    if os.environ.get("CORSAIR_TEST_LONG_PROBE") != "1":
        pytest.skip("set CORSAIR_TEST_LONG_PROBE=1 to run the 121-second Docker regression")
    client = _docker_client()
    image = _image()
    image_id = DockerSandbox(Settings(image=image), client=client).image_id
    settings, store, prepared = _prepared(tmp_path, image_id)
    settings = settings.model_copy(update={"image": image})
    prepared = prepared.model_copy(
        update={
            "manifest": prepared.manifest.model_copy(update={"config_digest": settings.identity})
        }
    )
    (tmp_path / "vulnerable/reader.py").write_text(
        "\n\nimport time\n\n\ndef read_file(root, path):\n"
        "    time.sleep(121)\n"
        '    return "hello"\n',
        encoding="utf-8",
    )
    case = Case(
        case_id="long-probe",
        finding=prepared.finding,
        source=Source(path="vulnerable"),
        recipe=prepared.recipe,
    )
    prepared = prepare_case(case, settings, store, prepared.manifest)
    sandbox = DockerSandbox(settings, client=client, store=store)
    operation_id = session_operation("long-probe-native")

    started = time.monotonic()
    raw_ref = sandbox.execute_role(
        prepared,
        _submission(),
        "control",
        Budget(probe_timeout_seconds=180),
        operation_id=operation_id,
    )
    elapsed = time.monotonic() - started

    raw = store.get_json(raw_ref)
    assert raw["cleanup_confirmed"] is True
    assert raw["docker_exit_code"] == 0
    assert raw["driver"]["native_exit_code"] == 0
    assert raw["driver"]["outcome"] == "PROPERTY_HELD"
    assert elapsed > 120
    assert elapsed < 180
    _assert_cleanup(client, operation_id)


def test_session_sweep_removes_only_this_sessions_sandboxes(session_operation) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(image=_image()), client=client).image_id
    own = session_operation("sweep-probe")
    prefix = own.rsplit(".", 1)[0]
    other = f"pytest-{uuid.uuid4().hex[:12]}.sweep-probe"
    assert SESSION_OPERATION.fullmatch(own) and SESSION_OPERATION.fullmatch(other)
    created = {
        operation: client.containers.create(
            image=image_id,
            labels={"corsair.security": "true", "corsair.operation": operation},
            network_mode="none",
            command=["true"],
        )
        for operation in (own, other)
    }
    try:
        assert [c.id for c in _session_containers(client, prefix)] == [created[own].id]
        assert _remove_session_containers(client, prefix) == [f"{own}:{created[own].id[:12]}"]
        _assert_cleanup(client, own)
        # Another session's identically labelled sandbox is still held, never swept.
        held = client.containers.list(all=True, filters={"label": f"corsair.operation={other}"})
        assert [c.id for c in held] == [created[other].id]
    finally:
        for container in created.values():
            with suppress(NotFound):
                client.api.remove_container(container.id, force=True)
