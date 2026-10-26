"""Runtime procedure provenance at the existing manifest consumer boundary."""

from pathlib import Path

from corsair.agents.resources import runtime_skill_digest
from corsair.contracts import InvestigationRequest, digest
from corsair.settings import Settings
from corsair.steps import manifest


def test_manifest_binds_procedure_resources_and_changes_when_skill_content_changes(
    tmp_path: Path,
    monkeypatch,
):
    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    )
    settings = Settings(artifact_root=str(tmp_path))
    before = manifest.build_manifest(request, settings, "sha256:" + "a" * 64)
    for role in ("producer", "auditor"):
        assert before.capabilities[role]["runtime_skills_digest"] == runtime_skill_digest(role)
    monkeypatch.setattr(
        manifest, "runtime_skill_digest", lambda role: digest({"role": role, "changed": True})
    )
    after = manifest.build_manifest(request, settings, "sha256:" + "a" * 64)
    assert digest(before.capabilities) != digest(after.capabilities)
    assert before.request_digest == after.request_digest
    assert before.config_digest == after.config_digest


def test_manifest_producer_capability_is_exactly_the_source_reads(tmp_path: Path):
    """Deliberate identity change: the producer's preloaded procedure has no loader."""
    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    )
    built = manifest.build_manifest(
        request, Settings(artifact_root=str(tmp_path)), "sha256:" + "a" * 64
    )
    producer = built.capabilities["producer"]
    assert producer["tools"] == ["read_file", "list_files"]
    assert producer["runtime_skills_digest"] == runtime_skill_digest("producer")
