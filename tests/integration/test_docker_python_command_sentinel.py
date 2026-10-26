"""Real-Docker evidence for the python.command_sentinel/1 recipe.

Build the trusted image first (``just images`` rebuilds ``corsair-python:0.1`` from the
current driver; set ``CORSAIR_TEST_IMAGE`` to use a differently tagged scratch build).
These cases cover the recipe's four native outcomes: a genuine control/violation
differential, a non-executing adversarial payload, a disallowed target exception, and
absent relevant coverage.
"""

from __future__ import annotations

import os
import time
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
    Observation,
    PlanRevision,
    PythonCommandSentinel,
    RunManifest,
    Source,
    Submission,
)
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

pytestmark = pytest.mark.docker

SENTINEL = "/work/corsair-sentinel"

# shell=True lets a ';' in the path run an injected command.
CMDI_VULNERABLE = (
    "import subprocess\n\n\n"
    "def count_lines(path):\n"
    '    cmd = "wc -l " + path\n'
    "    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout\n"
)
# shell=False passes the whole string as one argv entry; the ';' cannot inject.
CMDI_SAFE = (
    "import subprocess\n\n\n"
    "def count_lines(path):\n"
    '    argv = ["wc", "-l", path]\n'
    "    return subprocess.run(argv, shell=False, capture_output=True, text=True).stdout\n"
)
# control payload returns; any other payload raises a disallowed exception, no sentinel.
RAISES = (
    "def count_lines(path):\n"
    "    if path == 'ok':\n"
    "        return 'fine'\n"
    "    raise RuntimeError(path)\n"
)


def _image() -> str:
    return os.environ.get("CORSAIR_TEST_IMAGE", Settings().image)


def _docker_client() -> docker.DockerClient:
    image = _image()
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get(image)
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires image {image}: {type(exc).__name__}")
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


def _submission(control: str, exploit: str) -> Submission:
    return Submission(
        control_payload=control,
        exploit_payload=exploit,
        hypothesis="whether the caller value reaches command or code execution",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _evaluate(
    tmp_path: Path,
    client: docker.DockerClient,
    *,
    body: str,
    line: int,
    operation_id: str,
) -> tuple[Observation, str]:
    image_id = DockerSandbox(Settings(image=_image()), client=client).image_id
    source = tmp_path / "source"
    source.mkdir(parents=True)
    (source / "app.py").write_text(body, encoding="utf-8")
    settings = Settings(
        source_root=str(tmp_path), artifact_root=str(tmp_path / "art"), image=_image()
    )
    store = ArtifactStore(tmp_path / "art")
    recipe = PythonCommandSentinel(
        module_file="app.py",
        function="count_lines",
        payload_parameter="path",
        sentinel_path=SENTINEL,
        public_files={"hello.txt": "hello"},
    )
    case = Case(
        case_id="sentinel",
        finding=Finding(title="cmdi", description="execution", file="app.py", line=line),
        source=Source(path="source"),
        recipe=recipe,
    )
    prepared = prepare_case(case, settings, store, _manifest(image_id))
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    started = time.monotonic()
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="run",
            operation_id=operation_id,
            prepared=prepared,
            submission=_submission("ok", f"x; touch {SENTINEL}"),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    elapsed = time.monotonic() - started
    _assert_cleanup(client, operation_id)
    return observation, f"{elapsed:.2f}s for both roles"


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def test_vulnerable_source_holds_control_and_violates_on_sentinel(tmp_path: Path) -> None:
    client = _docker_client()
    observation, timing = _evaluate(
        tmp_path, client, body=CMDI_VULNERABLE, line=4, operation_id="sentinel-vuln"
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert observation.control.native_exit_code == 0
    assert observation.adversarial.native_exit_code != 0
    print(f"command_sentinel vulnerable: {timing}")


def test_non_executing_payload_holds_on_both_roles(tmp_path: Path) -> None:
    client = _docker_client()
    observation, timing = _evaluate(
        tmp_path, client, body=CMDI_SAFE, line=4, operation_id="sentinel-safe"
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "PROPERTY_HELD"
    print(f"command_sentinel safe: {timing}")


def test_disallowed_target_exception_is_error_not_violation(tmp_path: Path) -> None:
    client = _docker_client()
    observation, _ = _evaluate(
        tmp_path, client, body=RAISES, line=1, operation_id="sentinel-raises"
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "ERROR"
    assert observation.adversarial.outcome.value != "VIOLATION"


def test_absent_relevant_coverage_is_invalid(tmp_path: Path) -> None:
    client = _docker_client()
    # Line 2 is a blank line between the import and the def: never executed, so the
    # declared finding line is not covered and the control role is INVALID.
    body = (
        "import subprocess\n\n\n"
        "def count_lines(path):\n"
        "    return subprocess.run('true', shell=True).returncode\n"
    )
    observation, _ = _evaluate(tmp_path, client, body=body, line=2, operation_id="sentinel-nocover")
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "INVALID"
