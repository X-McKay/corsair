"""Real-Docker qualification of the C integer-overflow recipe (c.integer_overflow/1).

These tests need the reviewed ``corsair-c:0.1`` image (``just images``), or the image
named by ``CORSAIR_TEST_C_IMAGE``, and a Docker daemon. They prove the control/violation
differential and the failure modes on the actual hardened container: a plain crash, a
forged sanitizer report from a target that returns normally, and a compile failure are
operational ERROR, never a VIOLATION; only a target-bound sanitizer report with the
sanitizer's own halt status drives a violation.
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
    CRecipe,
    EvidenceInput,
    Finding,
    PlanRevision,
    RunManifest,
    Source,
    Submission,
)
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

pytestmark = pytest.mark.docker

C_KIND = "c.integer_overflow/1"
# A scratch build of deploy/c/Dockerfile can be qualified without retagging the
# released image, e.g. CORSAIR_TEST_C_IMAGE=corsair-c:fix.
C_IMAGE = os.environ.get("CORSAIR_TEST_C_IMAGE", "corsair-c:0.1")

# Vulnerable: `unsigned short total = n + 1` wraps to 0 at n=65535, so malloc(0) is
# followed by a memcpy of n bytes. The overflow sink (memcpy) is line 11 here.
VULNERABLE = """#include <stdlib.h>
#include <string.h>

char *dup_n(const char *src, unsigned short n) {
    unsigned short total = n + 1;
    char *buf = malloc(total);
    if (buf == NULL) {
        return NULL;
    }
    memcpy(buf, src, n);
    buf[n] = '\\0';
    return buf;
}
"""

# Fixed: the size is computed in size_t, so the allocation is always large enough.
FIXED = """#include <stdlib.h>
#include <string.h>

char *dup_n(const char *src, unsigned short n) {
    size_t total = (size_t)n + 1;
    char *buf = malloc(total);
    if (buf == NULL) {
        return NULL;
    }
    memcpy(buf, src, n);
    buf[n] = '\\0';
    return buf;
}
"""

# A crash that is NOT the admitted sanitizer class: a null-pointer write. AddressSanitizer
# reports a SEGV, not a heap-buffer-overflow, so the driver must call it ERROR.
CRASH = """#include <stdlib.h>

char *dup_n(const char *src, unsigned short n) {
    (void)src;
    (void)n;
    volatile char *p = NULL;
    *p = 1;
    return NULL;
}
"""

# Does not compile: the trusted driver must report a compile failure as operational.
# Hostile source forges the report: it prints AddressSanitizer text naming its own file
# and line to stderr, then returns normally. The text arrives without the sanitizer's
# halt status, so the driver must call it ERROR, never a VIOLATION.
FORGED_REPORT = """#include <stdio.h>
#include <stdlib.h>
#include <string.h>

char *dup_n(const char *src, unsigned short n) {
    fprintf(stderr, "==1==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x0\\n");
    fprintf(stderr, "    #0 0x0 in dup_n /source/dup.c:6\\n");
    char *buf = malloc((size_t)n + 1);
    if (buf == NULL) {
        return NULL;
    }
    memcpy(buf, src, n);
    buf[n] = '\\0';
    return buf;
}
"""

COMPILE_FAIL = """#include <stdlib.h>

char *dup_n(const char *src, unsigned short n) {
    this is not valid c;
}
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
        client.images.get(C_IMAGE)
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires {C_IMAGE}: {type(exc).__name__}")
        pytest.skip(f"real Docker image {C_IMAGE} unavailable: {type(exc).__name__}")
    return client


def _images() -> dict[str, str]:
    """The default recipe-kind image map with ``C_IMAGE`` for the C kind."""
    return {**Settings().images, C_KIND: C_IMAGE}


def _image_id(client: docker.DockerClient) -> str:
    return DockerSandbox(Settings(images=_images()), client=client).image_id_for(C_KIND)


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
        control_payload=5,
        exploit_payload=65535,
        hypothesis="the maximum unsigned-short length overflows the size calculation",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _prepared(
    tmp_path: Path,
    image_id: str,
    source: str,
    *,
    fixed_source: str | None = None,
    line: int = 5,
):
    vulnerable = tmp_path / "vulnerable"
    vulnerable.mkdir(parents=True)
    (vulnerable / "dup.c").write_text(source, encoding="utf-8")
    if fixed_source is not None:
        fixed_dir = tmp_path / "fixed"
        fixed_dir.mkdir()
        (fixed_dir / "dup.c").write_text(fixed_source, encoding="utf-8")
    recipe = CRecipe(
        module_file="dup.c",
        function="dup_n",
        length_parameter="n",
        fill_byte=65,
        expected_control_length=5,
        sanitizer_class="heap-buffer-overflow",
    )
    case = Case(
        case_id="docker-c-case",
        finding=Finding(title="overflow", description="length overflow", file="dup.c", line=line),
        source=Source(path="vulnerable"),
        fixed_source=Source(path="fixed") if fixed_source is not None else None,
        recipe=recipe,
    )
    settings = Settings(
        source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"), images=_images()
    )
    store = ArtifactStore(tmp_path / "artifacts")
    return settings, store, prepare_case(case, settings, store, _manifest(image_id))


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def _raw_driver(sandbox: DockerSandbox, store: ArtifactStore, prepared, role, operation_id):
    ref = sandbox.execute_role(
        prepared, _submission(), role, Budget(probe_timeout_seconds=60), operation_id=operation_id
    )
    return store.get_json(ref)


def test_c_vulnerable_shows_control_held_and_exploit_violation(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, VULNERABLE, fixed_source=FIXED)
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="run-c-vuln",
            operation_id="docker-c-vulnerable",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=60),
        )
    )
    assert observation.cleanup_confirmed is True
    assert observation.feedback is None
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert observation.control.covered_lines and 5 in observation.control.covered_lines
    assert 5 in observation.adversarial.covered_lines
    _assert_cleanup(client, "docker-c-vulnerable")


def test_c_fixed_revision_neutralizes_the_exploit(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, FIXED, fixed_source=FIXED)
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="run-c-fixed",
            operation_id="docker-c-fixed",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=60),
            fixed=True,
        )
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "PROPERTY_HELD"
    _assert_cleanup(client, "docker-c-fixed")


def test_c_plain_crash_is_error_not_violation(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, CRASH)
    sandbox = DockerSandbox(settings, client=client, store=store)
    raw = _raw_driver(sandbox, store, prepared, "adversarial", "docker-c-crash")
    driver = raw["driver"]
    assert driver["outcome"] == "ERROR"
    assert driver["observation_kind"] == "execution_error"
    assert driver["junit"]["status"] == "ERROR"
    assert raw["cleanup_confirmed"] is True
    _assert_cleanup(client, "docker-c-crash")


def test_c_forged_sanitizer_text_without_the_halt_status_is_error(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, FORGED_REPORT, line=6)
    sandbox = DockerSandbox(settings, client=client, store=store)
    raw = _raw_driver(sandbox, store, prepared, "adversarial", "docker-c-forged")
    driver = raw["driver"]
    assert driver["outcome"] == "ERROR"
    assert driver["observation_kind"] == "execution_error"
    assert driver["junit"]["status"] == "ERROR"
    assert raw["cleanup_confirmed"] is True
    _assert_cleanup(client, "docker-c-forged")


def test_c_compile_failure_is_operational_error(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, COMPILE_FAIL)
    sandbox = DockerSandbox(settings, client=client, store=store)
    raw = _raw_driver(sandbox, store, prepared, "control", "docker-c-compile")
    driver = raw["driver"]
    assert driver["outcome"] == "ERROR"
    assert driver["observation_kind"] == "compile_error"
    assert driver["covered_lines"] == []
    assert raw["cleanup_confirmed"] is True
    _assert_cleanup(client, "docker-c-compile")


def test_c_absent_target_line_coverage_is_invalid(tmp_path: Path) -> None:
    # The finding line points at an #include (line 2), which gcov never marks executed,
    # so the kernel's coverage-relevance gate must reject the role as INVALID.
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _prepared(tmp_path, image_id, VULNERABLE, line=2)
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="run-c-nocov",
            operation_id="docker-c-nocov",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=60),
        )
    )
    assert observation.control and observation.control.outcome.value == "INVALID"
    _assert_cleanup(client, "docker-c-nocov")
