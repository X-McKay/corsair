"""Real-Docker qualification for the Java secret-disclosure recipe (Linux amd64).

These tests require a reachable Docker daemon and the content-tagged ``corsair-java`` image
built from ``deploy/java/Dockerfile`` (``just images-gym``). They exercise the trusted Java driver
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
from tests.integration.sandbox_seconds import assert_sandbox_seconds
from tests.integration.trusted_images import content_image, content_images

pytestmark = pytest.mark.docker

JAVA_KIND = "java.secret_disclosure/1"
# A scratch build of deploy/java/Dockerfile can be qualified without retagging the
# released image, e.g. CORSAIR_TEST_JAVA_IMAGE=corsair-java:fix.
JAVA_IMAGE = os.environ.get("CORSAIR_TEST_JAVA_IMAGE") or content_image(JAVA_KIND)
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

# The vulnerable loader in the default package (no package declaration), as a top-level
# source file directly under its source root. JaCoCo names the default package "", so
# the driver must not query it as dirname's ".". The parse sink is line 11.
DEFAULT_PACKAGE_MODULE = "src/XmlLoader.java"
DEFAULT_PACKAGE = """import java.io.ByteArrayInputStream;
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
        client.images.get(JAVA_IMAGE)
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


def _images() -> dict[str, str]:
    """The default recipe-kind image map with ``JAVA_IMAGE`` for the Java kind."""
    return {**content_images(), JAVA_KIND: JAVA_IMAGE}


def _image_id(client: docker.DockerClient) -> str:
    return DockerSandbox(Settings(images=_images()), client=client).image_id_for(JAVA_KIND)


def _write_tree(root: Path, body: str, module: str) -> None:
    target = root / module
    target.parent.mkdir(parents=True)
    target.write_text(body, encoding="utf-8")


def _prepared(
    tmp_path: Path,
    image_id: str,
    *,
    body: str = VULNERABLE,
    line: int = 13,
    fixed_body: str | None = None,
    module: str = MODULE,
    entry_class: str = "com.example.XmlLoader",
    source_root: str = "src/main/java",
):
    source_dir = tmp_path / "vulnerable"
    source_dir.mkdir(parents=True)
    _write_tree(source_dir, body, module)
    if fixed_body is not None:
        fixed_dir = tmp_path / "fixed"
        fixed_dir.mkdir()
        _write_tree(fixed_dir, fixed_body, module)
    recipe = JavaRecipe(
        module_file=module,
        entry_class=entry_class,
        method="loadTitle",
        source_roots=[source_root],
        public_files={"hello.txt": "hello"},
        expected_control="hello",
        allowed_exceptions=["org.xml.sax.SAXParseException"],
    )
    case = Case(
        case_id="docker-java-case",
        finding=Finding(title="xxe", description="entity expansion", file=module, line=line),
        source=Source(path="vulnerable"),
        fixed_source=Source(path="fixed") if fixed_body is not None else None,
        recipe=recipe,
    )
    settings = Settings(
        source_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        runtime="runc",
        images=_images(),
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
    image_id = _image_id(client)

    settings, store, vulnerable = _prepared(tmp_path / "vuln", image_id, fixed_body=FIXED)
    observation = _evaluate(settings, store, vulnerable, client, "java-vulnerable")
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert 13 in observation.adversarial.covered_lines
    assert_sandbox_seconds(observation)
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


def test_real_docker_java_default_package_class_is_covered(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    # A class with no package declaration sits in JaCoCo's default package, named "".
    # Its covered lines must still bind both roles to the finding line, giving the same
    # healthy-control/violation differential as the packaged layout.
    settings, store, prepared = _prepared(
        tmp_path,
        image_id,
        body=DEFAULT_PACKAGE,
        line=11,
        module=DEFAULT_PACKAGE_MODULE,
        entry_class="XmlLoader",
        source_root="src",
    )
    observation = _evaluate(settings, store, prepared, client, "java-default-package")
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert 11 in observation.control.covered_lines
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert 11 in observation.adversarial.covered_lines
    _assert_cleanup(client, "java-default-package")


def test_real_docker_java_unexpected_exception_is_operational(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
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
    image_id = _image_id(client)
    # Line 1 (the package declaration) is never executed, so the vulnerable run cannot
    # bind the demonstration to the finding line: the observation stays invalid.
    settings, store, prepared = _prepared(tmp_path, image_id, line=1)
    observation = _evaluate(settings, store, prepared, client, "java-no-coverage")
    assert observation.cleanup_confirmed is True
    assert observation.adversarial and observation.adversarial.outcome.value == "INVALID"
    _assert_cleanup(client, "java-no-coverage")


def test_real_docker_java_compile_failure_is_operational(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, body=DOES_NOT_COMPILE)
    observation = _evaluate(settings, store, prepared, client, "java-compile-fail")
    assert observation.cleanup_confirmed is True
    # A source tree that does not compile is operational, never a clean negative.
    assert observation.control and observation.control.outcome.value in {"ERROR", "INVALID"}
    assert not observation.control.target_executed
    _assert_cleanup(client, "java-compile-fail")
