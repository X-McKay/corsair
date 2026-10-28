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

JAVA_IMAGE = "corsair-java:evolution-20261025"

VULNERABLE = """import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Gate {
    public static String read(String root, String requestedPath) throws IOException {
        return Files.readString(Path.of(root).resolve(requestedPath));
    }
}
"""

SAFE = """import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Gate {
    public static String read(String root, String requestedPath) throws IOException {
        Path base = Path.of(root).toAbsolutePath().normalize();
        Path candidate = base.resolve(requestedPath).normalize();
        if (!candidate.startsWith(base)) {
            return "blocked";
        }
        return Files.readString(candidate);
    }
}
"""

CONTROL_FAILURE = """public class Gate {
    public static String read(String root, String requestedPath) {
        return requestedPath.equals("hello.txt") ? "wrong-control" : "safe";
    }
}
"""

UNEXPECTED_EXCEPTION = """public class Gate {
    public static String read(String root, String requestedPath) {
        if (requestedPath.equals("hello.txt")) {
            return "hello";
        }
        throw new IllegalStateException("unexpected target failure");
    }
}
"""

COMPILE_FAILURE = """public class Gate {
    public static String read(String root, String requestedPath) {
        return "hello"
    }
}
"""

MISSING_METHOD = """public class Gate {
    public static String wrong(String root, String requestedPath) {
        return "hello";
    }
}
"""

MISSING_REPORT = """public class Gate {
    public static String read(String root, String requestedPath) {
        Runtime.getRuntime().halt(0);
        return "unreachable";
    }
}
"""

MISSING_COVERAGE = """import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Gate {
    public static String read(String root, String requestedPath) throws IOException {
        Files.deleteIfExists(Path.of("/work/jacoco.exec"));
        Files.createDirectory(Path.of("/work/jacoco.exec"));
        return Files.readString(Path.of(root).resolve(requestedPath));
    }
}
"""


def _java_client() -> docker.DockerClient:
    if os.getenv("CORSAIR_TEST_JAVA") != "1":
        pytest.skip("set CORSAIR_TEST_JAVA=1 after building the reviewed Java image")
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(os.getenv("CORSAIR_TEST_JAVA_IMAGE", JAVA_IMAGE))
    except DockerException as exc:
        pytest.fail(f"explicit Java native anchor requires daemon and image: {type(exc).__name__}")
    return client


def _chmod_tree(root: Path) -> None:
    for directory in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
        directory.chmod(0o555)
    for file in root.rglob("*"):
        if file.is_file():
            file.chmod(0o444)
    root.chmod(0o555)


def _job(role: str) -> dict[str, Any]:
    return {
        "schema_version": "corsair.driver-job/1",
        "operation_id": f"java-{role}-anchor",
        "role": role,
        "source_digest": "a" * 64,
        "submission_digest": "b" * 64,
        "recipe": {
            "kind": "java.secret_disclosure/1",
            "module_file": "Gate.java",
            "class_name": "Gate",
            "function": "read",
            "fixed_args": ["/fixtures/allowed"],
            "payload_index": 1,
            "public_files": {"hello.txt": "hello"},
            "expected_control": "hello",
            "private_fixture_path": "/fixtures/private/secret.txt",
            "allowed_exceptions": [],
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
    (source_root / "Gate.java").write_text(source, encoding="utf-8")
    (fixtures_root / "allowed" / "hello.txt").write_text("hello", encoding="utf-8")
    (fixtures_root / "private" / "secret.txt").write_text(
        secrets.token_urlsafe(32), encoding="utf-8"
    )
    (input_root / "job.json").write_text(json.dumps(job, separators=(",", ":")), encoding="utf-8")
    for mounted in (source_root, fixtures_root, input_root):
        _chmod_tree(mounted)
    image = os.getenv("CORSAIR_TEST_JAVA_IMAGE", JAVA_IMAGE)
    container = client.containers.create(
        image=image,
        labels={
            "corsair.security": "true",
            "corsair.operation": job.get("operation_id", "invalid"),
        },
        network_mode="none",
        read_only=True,
        user="10001:10001",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        privileged=False,
        mem_limit="512m",
        nano_cpus=1_000_000_000,
        pids_limit=64,
        working_dir="/work",
        environment={"HOME": "/tmp"},
        tmpfs={
            "/work": "rw,nosuid,nodev,noexec,size=64m,mode=0700,uid=10001,gid=10001",
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
        result = container.wait(timeout=30)
        stdout = container.logs(stdout=True, stderr=False)
        stderr = container.logs(stdout=False, stderr=True)
        (root / "native-stdout.json").write_bytes(stdout)
        (root / "native-stderr.log").write_bytes(stderr)
        (root / "native-exit.json").write_text(json.dumps(result))
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
    assert record["operation_id"] == f"java-{role}-anchor"
    assert record["role"] == role
    assert record["source_digest"] == "a" * 64
    assert record["submission_digest"] == "b" * 64
    assert record["native_exit_code"] == native_exit
    assert record["outcome"] == outcome
    assert record["observation_kind"] == observation_kind
    assert record["junit"]["status"] == junit_status
    assert record["coverage_file"] == "Gate.java"
    assert set(record["native_reports"]).issubset({"junit", "coverage"})
    if outcome in {"PROPERTY_HELD", "VIOLATION", "INVALID"}:
        assert record["junit"]["tests"] == 1
        assert record["junit"]["skipped"] == 0
        assert record["covered_lines"]


def test_real_java_native_harness_anchor(tmp_path: Path) -> None:
    client = _java_client()

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

    safe_adversarial, exit_code = _run_driver(client, tmp_path, SAFE, _job("adversarial"))
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


def test_real_java_native_harness_failures_remain_errors(tmp_path: Path) -> None:
    client = _java_client()

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

    compile_failure, exit_code = _run_driver(client, tmp_path, COMPILE_FAILURE, _job("control"))
    _assert_record(
        compile_failure,
        role="control",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert compile_failure["junit"]["tests"] == 0
    assert compile_failure["target_executed"] is False

    missing_method, exit_code = _run_driver(client, tmp_path, MISSING_METHOD, _job("control"))
    _assert_record(
        missing_method,
        role="control",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code != 0
    assert missing_method["target_executed"] is False

    missing_report, exit_code = _run_driver(client, tmp_path, MISSING_REPORT, _job("control"))
    _assert_record(
        missing_report,
        role="control",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code == 0
    assert missing_report["junit"]["tests"] == 0
    assert missing_report["target_executed"] is False

    missing_coverage, exit_code = _run_driver(client, tmp_path, MISSING_COVERAGE, _job("control"))
    _assert_record(
        missing_coverage,
        role="control",
        outcome="ERROR",
        observation_kind="execution_error",
        junit_status="ERROR",
        native_exit=exit_code,
    )
    assert exit_code == 0
    assert missing_coverage["target_executed"] is False
    assert missing_coverage["covered_lines"] == []


def test_real_java_native_harness_rejects_malformed_job(tmp_path: Path) -> None:
    client = _java_client()
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
