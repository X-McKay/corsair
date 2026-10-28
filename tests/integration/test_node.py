from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

import docker
import pytest
from docker.errors import DockerException, NotFound
from docker.types import LogConfig

pytestmark = pytest.mark.docker

NODE_IMAGE = "corsair-node:evolution-20261025"

VULNERABLE = """import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

export async function readFileAt(root, requestedPath) {
  return readFile(join(root, requestedPath), 'utf8');
}
"""

SAFE = """import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';

export async function readFileAt(root, requestedPath) {
  const base = resolve(root);
  const candidate = resolve(base, requestedPath);
  if (candidate !== base && !candidate.startsWith(`${base}${sep}`)) {
    throw new RangeError('path escapes public fixtures');
  }
  return readFile(candidate, 'utf8');
}
"""

CONTROL_FAILURE = """export function readFileAt(root, requestedPath) {
  return requestedPath === 'hello.txt' ? 'wrong-control' : 'safe';
}
"""

UNEXPECTED_EXCEPTION = """export function readFileAt(root, requestedPath) {
  if (requestedPath === 'hello.txt') {
    return 'hello';
  }
  throw new SyntaxError('unexpected target failure');
}
"""

FAKE_MARKER = """import { writeFile } from 'node:fs/promises';

export async function readFileAt(root, requestedPath) {
  if (requestedPath === 'hello.txt') {
    return 'hello';
  }
  await writeFile('/work/observation.json', JSON.stringify({ kind: 'disclosure' }));
  throw new Error('target-created marker is not evidence');
}
"""

SECRET_LOGGING = """import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

export async function readFileAt(root, requestedPath) {
  if (requestedPath === 'hello.txt') {
    return 'hello';
  }
  console.log(await readFile(join(root, requestedPath), 'utf8'));
  return 'safe';
}
"""

MISSING_REPORT = """export function readFileAt() {
  process.exit(0);
}
"""


def _node_client() -> docker.DockerClient:
    if os.getenv("CORSAIR_TEST_NODE") != "1":
        pytest.skip("set CORSAIR_TEST_NODE=1 after building the reviewed Node image")
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(os.getenv("CORSAIR_TEST_NODE_IMAGE", NODE_IMAGE))
    except DockerException as exc:
        pytest.fail(f"explicit Node native anchor requires daemon and image: {type(exc).__name__}")
    return client


def _chmod_tree(root: Path) -> None:
    for directory in sorted((entry for entry in root.rglob("*") if entry.is_dir()), reverse=True):
        directory.chmod(0o555)
    for file in root.rglob("*"):
        if file.is_file():
            file.chmod(0o444)
    root.chmod(0o555)


def _job(role: str, allowed_exceptions: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "corsair.driver-job/1",
        "operation_id": f"node-{role}-anchor",
        "role": role,
        "source_digest": "a" * 64,
        "submission_digest": "b" * 64,
        "recipe": {
            "kind": "javascript.secret_disclosure/1",
            "module_file": "reader.mjs",
            "function": "readFileAt",
            "fixed_args": ["/fixtures/allowed"],
            "payload_index": 1,
            "public_files": {"hello.txt": "hello"},
            "expected_control": "hello",
            "private_fixture_path": "/fixtures/private/secret.txt",
            "allowed_exceptions": allowed_exceptions or [],
        },
        "payload": "hello.txt" if role == "control" else "../private/secret.txt",
    }


def _run_driver(
    client: docker.DockerClient,
    tmp_path: Path,
    source: str,
    job: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    root = tmp_path / secrets.token_hex(8)
    source_root = root / "source"
    fixtures_root = root / "fixtures"
    input_root = root / "input"
    source_root.mkdir(parents=True)
    (fixtures_root / "allowed").mkdir(parents=True)
    (fixtures_root / "private").mkdir(parents=True)
    input_root.mkdir(parents=True)
    (source_root / "reader.mjs").write_text(source, encoding="utf-8")
    (fixtures_root / "allowed" / "hello.txt").write_text("hello", encoding="utf-8")
    (fixtures_root / "private" / "secret.txt").write_text(
        secrets.token_urlsafe(32), encoding="utf-8"
    )
    (input_root / "job.json").write_text(json.dumps(job, separators=(",", ":")), encoding="utf-8")
    for mounted in (source_root, fixtures_root, input_root):
        _chmod_tree(mounted)
    image = os.getenv("CORSAIR_TEST_NODE_IMAGE", NODE_IMAGE)
    container = client.containers.create(
        image=image,
        labels={
            "corsair.security": "true",
            "corsair.operation": job.get("operation_id", "invalid"),
        },
        network_mode="none",
        read_only=True,
        user="1000:1000",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        privileged=False,
        mem_limit="128m",
        nano_cpus=1_000_000_000,
        pids_limit=64,
        working_dir="/work",
        environment={"HOME": "/tmp", "NODE_NO_WARNINGS": "1"},
        tmpfs={
            "/work": "rw,nosuid,nodev,noexec,size=64m,mode=0700,uid=1000,gid=1000",
            "/tmp": "rw,nosuid,nodev,noexec,size=32m,mode=1777",
        },
        log_config=LogConfig(type="json-file", config={"max-size": "128k", "max-file": "1"}),
        volumes={
            str(source_root): {"bind": "/source", "mode": "ro"},
            str(fixtures_root): {"bind": "/fixtures", "mode": "ro"},
            str(input_root): {"bind": "/input", "mode": "ro"},
        },
    )
    try:
        container.start()
        result = container.wait(timeout=20)
        stdout = container.logs(stdout=True, stderr=False)
        (root / "native-stdout.json").write_bytes(stdout)
        (root / "native-stderr.log").write_bytes(container.logs(stdout=False, stderr=True))
        lines = [line for line in stdout.decode("utf-8").splitlines() if line]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert isinstance(result["StatusCode"], int)
        assert record["native_exit_code"] == result["StatusCode"]
        return record, result["StatusCode"]
    finally:
        immutable_id = container.id
        container.remove(force=True)
        with pytest.raises(NotFound):
            client.api.inspect_container(immutable_id)


def _assert_record(
    record: dict[str, Any],
    *,
    role: str,
    outcome: str,
    observation_kind: str,
    junit_status: str,
    native_exit: int,
) -> None:
    assert record["schema_version"] == "corsair.driver/1"
    assert record["operation_id"] == f"node-{role}-anchor"
    assert record["role"] == role
    assert record["source_digest"] == "a" * 64
    assert record["submission_digest"] == "b" * 64
    assert record["outcome"] == outcome
    assert record["observation_kind"] == observation_kind
    assert record["native_exit_code"] == native_exit
    assert record["junit"]["status"] == junit_status
    assert record["junit"]["tests"] == 1
    assert record["junit"]["skipped"] == 0
    if junit_status == "PASS":
        assert record["junit"]["failures"] == 0
        assert record["junit"]["errors"] == 0
    elif junit_status == "FAILURE":
        assert record["junit"]["failures"] == 1
        assert record["junit"]["errors"] == 0
    else:
        assert record["junit"]["failures"] + record["junit"]["errors"] == 1
    assert record["coverage_file"] == "reader.mjs"


def test_real_node_native_harness_anchor(tmp_path: Path) -> None:
    client = _node_client()

    control, exit_code = _run_driver(client, tmp_path, VULNERABLE, _job("control"))
    _assert_record(
        control,
        role="control",
        outcome="PROPERTY_HELD",
        observation_kind="held",
        junit_status="PASS",
        native_exit=exit_code,
    )
    assert exit_code == 0
    assert control["target_executed"] is True
    assert control["covered_lines"]

    disclosure, exit_code = _run_driver(client, tmp_path, VULNERABLE, _job("adversarial"))
    _assert_record(
        disclosure,
        role="adversarial",
        outcome="VIOLATION",
        observation_kind="disclosure",
        junit_status="FAILURE",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert disclosure["target_executed"] is True
    assert disclosure["covered_lines"]

    safe_control, exit_code = _run_driver(client, tmp_path, SAFE, _job("control"))
    _assert_record(
        safe_control,
        role="control",
        outcome="PROPERTY_HELD",
        observation_kind="held",
        junit_status="PASS",
        native_exit=exit_code,
    )
    assert exit_code == 0

    safe_adversarial, exit_code = _run_driver(
        client, tmp_path, SAFE, _job("adversarial", ["RangeError"])
    )
    _assert_record(
        safe_adversarial,
        role="adversarial",
        outcome="PROPERTY_HELD",
        observation_kind="held",
        junit_status="PASS",
        native_exit=exit_code,
    )
    assert exit_code == 0

    invalid_control, exit_code = _run_driver(client, tmp_path, CONTROL_FAILURE, _job("control"))
    _assert_record(
        invalid_control,
        role="control",
        outcome="INVALID",
        observation_kind="invalid_control",
        junit_status="INVALID",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert invalid_control["target_executed"] is True


def test_real_node_native_harness_failures_never_become_disclosures(tmp_path: Path) -> None:
    client = _node_client()

    unexpected, exit_code = _run_driver(client, tmp_path, UNEXPECTED_EXCEPTION, _job("adversarial"))
    _assert_record(
        unexpected,
        role="adversarial",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert unexpected["target_executed"] is False

    marker, exit_code = _run_driver(client, tmp_path, FAKE_MARKER, _job("adversarial"))
    _assert_record(
        marker,
        role="adversarial",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert marker["target_executed"] is False

    logged, exit_code = _run_driver(client, tmp_path, SECRET_LOGGING, _job("adversarial"))
    _assert_record(
        logged,
        role="adversarial",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert logged["target_executed"] is False

    missing, exit_code = _run_driver(client, tmp_path, MISSING_REPORT, _job("control"))
    assert missing["outcome"] == "ERROR"
    assert missing["observation_kind"] == "execution_error"
    assert missing["junit"]["status"] == "ERROR"
    assert missing["junit"]["tests"] == 0
    assert missing["native_exit_code"] == exit_code
    assert missing["target_executed"] is False


def test_real_node_native_harness_rejects_malformed_job(tmp_path: Path) -> None:
    client = _node_client()
    record, exit_code = _run_driver(client, tmp_path, VULNERABLE, {"invalid": "job"})

    assert exit_code == 2
    assert record == {
        "schema_version": "corsair.driver/1",
        "operation_id": "",
        "role": "",
        "source_digest": "",
        "submission_digest": "",
        "native_exit_code": 2,
        "outcome": "INVALID",
        "observation_kind": "execution_error",
        "target_executed": False,
        "covered_lines": [],
        "coverage_file": "",
        "junit": {"status": "INVALID", "tests": 0, "failures": 0, "errors": 0, "skipped": 0},
    }
