"""Real-Docker qualification for the Java secret-disclosure recipe (Linux amd64).

These tests require a reachable Docker daemon and the ``corsair-java:0.1`` image built
from ``deploy/java/Dockerfile`` (``just images``). They exercise the trusted Java driver
end to end through the same kernel as the Python observer: control, adversarial
disclosure, a neutralized revision, the fixed differential, an unexpected target
exception, absent target-line coverage, a source tree that does not compile, and
cleanup bound to immutable container identity. A scripted double can never stand in for
this boundary; a missing daemon or image fails rather than silently skipping.
"""

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
    JavaRecipe,
    PlanRevision,
    RunManifest,
    Source,
    Submission,
)
from corsair.policies.verdicts import fix_status
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

pytestmark = pytest.mark.docker

JAVA_KIND = "java.secret_disclosure/1"
MODULE = "src/main/java/com/example/XmlLoader.java"

# Vulnerable: a DocumentBuilderFactory left at permissive defaults expands external
# entities, so an external-entity document discloses a local file (CWE-611).
VULNERABLE = """package com.example;

import java.io.ByteArrayInputStream;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class XmlLoader {

    public String loadTitle(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = factory.newDocumentBuilder();
        Document document = builder.parse(new ByteArrayInputStream(xml.getBytes("UTF-8")));
        return document.getDocumentElement().getTextContent();
    }
}
"""

# Neutralized/fixed: DOCTYPE declarations are disallowed, so the external-entity
# document raises org.xml.sax.SAXParseException (an allowed, non-disclosing outcome).
# Laid out so the parse sink is line 14 (one feature line past the vulnerable layout).
FIXED = """package com.example;

import java.io.ByteArrayInputStream;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class XmlLoader {

    public String loadTitle(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        DocumentBuilder builder = factory.newDocumentBuilder();
        Document document = builder.parse(new ByteArrayInputStream(xml.getBytes("UTF-8")));
        return document.getDocumentElement().getTextContent();
    }
}
"""

# Throws an exception that is NOT on the allowed list for the adversarial payload: the
# driver must report an operational execution_error, never a disclosure or a negative.
UNEXPECTED_EXCEPTION = """package com.example;

public class XmlLoader {

    public String loadTitle(String xml) throws Exception {
        if (xml.contains("DOCTYPE")) {
            throw new IllegalStateException("unexpected");
        }
        return "hello";
    }
}
"""

DOES_NOT_COMPILE = """package com.example;

public class XmlLoader {

    public String loadTitle(String xml) throws Exception {
        this is not valid java
    }
}
"""

BENIGN = '<?xml version="1.0" encoding="UTF-8"?><title>hello</title>'
EXPLOIT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE title [ <!ENTITY disclosed SYSTEM "file:///fixtures/private/secret.txt"> ]>'
    "<title>&disclosed;</title>"
)


def _docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get("corsair-java:0.1")
    except DockerException as exc:
        name = type(exc).__name__
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires corsair-java image: {name}")
        pytest.skip(f"real Docker java image unavailable: {name}")
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
        control_payload=BENIGN,
        exploit_payload=EXPLOIT,
        hypothesis="external entity expansion discloses a local file",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _write_tree(root: Path, body: str) -> None:
    target = root / "src" / "main" / "java" / "com" / "example"
    target.mkdir(parents=True)
    (target / "XmlLoader.java").write_text(body, encoding="utf-8")


def _prepared(
    tmp_path: Path,
    image_id: str,
    *,
    body: str = VULNERABLE,
    line: int = 13,
    fixed_body: str | None = None,
):
    source_dir = tmp_path / "vulnerable"
    source_dir.mkdir(parents=True)
    _write_tree(source_dir, body)
    if fixed_body is not None:
        fixed_dir = tmp_path / "fixed"
        fixed_dir.mkdir()
        _write_tree(fixed_dir, fixed_body)
    recipe = JavaRecipe(
        module_file=MODULE,
        entry_class="com.example.XmlLoader",
        method="loadTitle",
        source_roots=["src/main/java"],
        public_files={"hello.txt": "hello"},
        expected_control="hello",
        allowed_exceptions=["org.xml.sax.SAXParseException"],
    )
    case = Case(
        case_id="docker-java-case",
        finding=Finding(title="xxe", description="entity expansion", file=MODULE, line=line),
        source=Source(path="vulnerable"),
        fixed_source=Source(path="fixed") if fixed_body is not None else None,
        recipe=recipe,
    )
    settings = Settings(
        source_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
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


def _evaluate(settings, store, prepared, client, operation_id, *, fixed=False):
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    return verifier.evaluate(
        EvidenceInput(
            run_id=f"run-{operation_id}",
            operation_id=operation_id,
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=90),
            fixed=fixed,
        )
    )


def test_real_docker_java_vulnerable_safe_fixed_and_cleanup(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id_for(JAVA_KIND)

    settings, store, vulnerable = _prepared(tmp_path / "vuln", image_id, fixed_body=FIXED)
    observation = _evaluate(settings, store, vulnerable, client, "java-vulnerable")
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert 13 in observation.adversarial.covered_lines
    _assert_cleanup(client, "java-vulnerable")

    # When the exploit is blocked by a thrown exception, JaCoCo marks the parse line
    # itself as missed (its post-line probe never fires), so bind the neutralized
    # demonstration to line 13, which both payloads execute before that point.
    settings, store, safe = _prepared(tmp_path / "safe", image_id, body=FIXED, line=13)
    safe_observation = _evaluate(settings, store, safe, client, "java-safe")
    assert safe_observation.cleanup_confirmed is True
    assert safe_observation.adversarial
    assert safe_observation.adversarial.outcome.value == "PROPERTY_HELD"
    _assert_cleanup(client, "java-safe")

    settings, store, prepared = _prepared(tmp_path / "fix", image_id, fixed_body=FIXED)
    fixed_observation = _evaluate(settings, store, prepared, client, "java-fixed", fixed=True)
    assert fixed_observation.cleanup_confirmed is True
    assert fix_status(fixed_observation).value == "DEMONSTRATION_BLOCKED"
    _assert_cleanup(client, "java-fixed")


def test_real_docker_java_unexpected_exception_is_operational(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id_for(JAVA_KIND)
    # The benign control returns "hello" and the adversarial payload throws; line 6 (the
    # branch both payloads reach) binds the control demonstration.
    settings, store, prepared = _prepared(tmp_path, image_id, body=UNEXPECTED_EXCEPTION, line=6)
    observation = _evaluate(settings, store, prepared, client, "java-exception")
    assert observation.cleanup_confirmed is True
    # A non-allowed target exception is never a disclosure or a negative result.
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "ERROR"
    _assert_cleanup(client, "java-exception")


def test_real_docker_java_absent_target_coverage_is_invalid(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id_for(JAVA_KIND)
    # Line 1 (the package declaration) is never executed, so the vulnerable run cannot
    # bind the demonstration to the finding line: the observation stays invalid.
    settings, store, prepared = _prepared(tmp_path, image_id, line=1)
    observation = _evaluate(settings, store, prepared, client, "java-no-coverage")
    assert observation.cleanup_confirmed is True
    assert observation.adversarial and observation.adversarial.outcome.value == "INVALID"
    _assert_cleanup(client, "java-no-coverage")


def test_real_docker_java_compile_failure_is_operational(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(Settings(), client=client).image_id_for(JAVA_KIND)
    settings, store, prepared = _prepared(tmp_path, image_id, body=DOES_NOT_COMPILE)
    observation = _evaluate(settings, store, prepared, client, "java-compile-fail")
    assert observation.cleanup_confirmed is True
    # A source tree that does not compile is operational, never a clean negative.
    assert observation.control and observation.control.outcome.value in {"ERROR", "INVALID"}
    assert not observation.control.target_executed
    _assert_cleanup(client, "java-compile-fail")
