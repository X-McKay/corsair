"""Real-Docker qualification for the Ruby secret-disclosure recipe.

These tests need the content-tagged ``corsair-ruby`` image (``just images-gym``) and a
Docker daemon. They mirror the Python native gates: a vulnerable tree discloses the private
fixture through path traversal, the guarded fix blocks it, an unexpected target
exception becomes ERROR (never a positive), a target that never reaches the finding line
is rejected for absent coverage, and every container is cleaned up against its identity.
Linux amd64 only.
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
    PlanRevision,
    RubyRecipe,
    RunManifest,
    Source,
    Submission,
)
from corsair.policies.verdicts import fix_status
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.integration.sandbox_seconds import assert_sandbox_seconds
from tests.integration.trusted_images import content_image, with_content_images

pytestmark = pytest.mark.docker

RUBY_KIND = "ruby.secret_disclosure/1"
RUBY_IMAGE = content_image(RUBY_KIND)

VULNERABLE = """module Attachments
  # Read a stored attachment by name under the given root.
  def self.read(root:, name:)
    File.read(File.join(root, name))
  end
end
"""

SAFE = """module Attachments
  # Read a stored attachment by name under the given root.
  def self.read(root:, name:)
    path = File.expand_path(name, root)
    prefix = root + File::SEPARATOR
    raise ArgumentError, 'attachment outside root' unless path.start_with?(prefix)
    File.read(path)
  end
end
"""

# The sink on line 4 never runs for the benign name, so the finding line is uncovered.
UNCOVERED = """module Attachments
  def self.read(root:, name:)
    return 'stored attachment' if name == 'readme.txt'
    File.read(File.join(root, name))
  end
end
"""

# The benign name reaches the finding line (4); the traversal name raises a disallowed
# exception first, so the adversarial role must be ERROR, never a positive.
RAISES = """module Attachments
  def self.read(root:, name:)
    raise RuntimeError, 'boom' unless name == 'readme.txt'
    File.read(File.join(root, name))
  end
end
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
        client.images.get(RUBY_IMAGE)
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires {RUBY_IMAGE}: {type(exc).__name__}")
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
        control_payload="readme.txt",
        exploit_payload="../private/secret.txt",
        hypothesis="File.join permits traversal outside the fixed root",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _recipe() -> RubyRecipe:
    return RubyRecipe(
        module_file="lib/attachments.rb",
        receiver="Attachments",
        function="read",
        payload_parameter="name",
        fixed_kwargs={"root": "/fixtures/allowed"},
        public_files={"readme.txt": "stored attachment"},
        expected_control="stored attachment",
        allowed_exceptions=["ArgumentError"],
    )


def _prepared(tmp_path: Path, image_id: str, body: str, *, fixed: bool = False):
    vulnerable = tmp_path / "vulnerable" / "lib"
    vulnerable.mkdir(parents=True)
    (vulnerable / "attachments.rb").write_text(body, encoding="utf-8")
    if fixed:
        fixed_dir = tmp_path / "fixed" / "lib"
        fixed_dir.mkdir(parents=True)
        (fixed_dir / "attachments.rb").write_text(SAFE, encoding="utf-8")
    case = Case(
        case_id="docker-ruby",
        finding=Finding(
            title="traversal",
            description="name reaches File.read",
            file="lib/attachments.rb",
            line=4,
            claim_scope="component",
        ),
        source=Source(path="vulnerable"),
        fixed_source=Source(path="fixed") if fixed else None,
        recipe=_recipe(),
    )
    settings = with_content_images(
        Settings(
            source_root=str(tmp_path),
            artifact_root=str(tmp_path / "artifacts"),
            runtime="runc",
        )
    )
    store = ArtifactStore(tmp_path / "artifacts")
    return settings, store, prepare_case(case, settings, store, _manifest(image_id))


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def test_real_ruby_vulnerable_discloses_and_fix_blocks(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(with_content_images(Settings()), client=client).image_id_for(RUBY_KIND)

    settings, store, prepared = _prepared(tmp_path / "vuln", image_id, VULNERABLE, fixed=True)
    verifier = EvidenceVerifier(settings, store, DockerSandbox(settings, client, store=store))
    started = time.monotonic()
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="ruby-vuln",
            operation_id="ruby-vulnerable",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    elapsed = time.monotonic() - started
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    assert observation.control.covered_lines and 4 in observation.control.covered_lines
    assert 4 in observation.adversarial.covered_lines
    assert_sandbox_seconds(observation)
    # Two short Ruby role containers; this records the per-role order of magnitude.
    # Test-side bound on the control + adversarial pair; the kernel probe timeout is separate and
    # slower hosts have taken over 20 s here, so leave generous headroom.
    assert elapsed < 60
    _assert_cleanup(client, "ruby-vulnerable")

    fixed_observation = verifier.evaluate(
        EvidenceInput(
            run_id="ruby-fixed",
            operation_id="ruby-fixed",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
            fixed=True,
        )
    )
    assert fixed_observation.cleanup_confirmed is True
    assert fixed_observation.control and fixed_observation.control.outcome.value == "PROPERTY_HELD"
    assert (
        fixed_observation.adversarial
        and fixed_observation.adversarial.outcome.value == "PROPERTY_HELD"
    )
    assert fix_status(fixed_observation).value == "DEMONSTRATION_BLOCKED"
    _assert_cleanup(client, "ruby-fixed")


def test_real_ruby_unexpected_exception_is_error_not_positive(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(with_content_images(Settings()), client=client).image_id_for(RUBY_KIND)
    settings, store, prepared = _prepared(tmp_path, image_id, RAISES)
    observation = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client, store=store)
    ).evaluate(
        EvidenceInput(
            run_id="ruby-error",
            operation_id="ruby-error",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "ERROR"
    assert observation.adversarial.outcome.value != "VIOLATION"
    _assert_cleanup(client, "ruby-error")


def test_real_ruby_absent_finding_line_coverage_is_invalid(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = DockerSandbox(with_content_images(Settings()), client=client).image_id_for(RUBY_KIND)
    settings, store, prepared = _prepared(tmp_path, image_id, UNCOVERED)
    observation = EvidenceVerifier(
        settings, store, DockerSandbox(settings, client, store=store)
    ).evaluate(
        EvidenceInput(
            run_id="ruby-cov",
            operation_id="ruby-coverage",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert observation.cleanup_confirmed is True
    # The benign name returns before the finding line (4), so the required target-line
    # coverage is absent and the control role is rejected as INVALID with no covered
    # lines, never silently accepted.
    assert observation.control and observation.control.outcome.value == "INVALID"
    assert observation.control.covered_lines == []
    _assert_cleanup(client, "ruby-coverage")
