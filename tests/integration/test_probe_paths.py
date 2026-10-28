"""Native reproduction of a model path-composition error; no target runs on the host."""

from pathlib import Path

import pytest

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import EvidenceInput, RoleOutcome, Submission
from corsair.entrypoints.requests import load_investigation_request
from corsair.steps.evidence import run_evidence
from corsair.steps.manifest import build_manifest
from tests.integration.test_language_chain import ROOT, _settings


@pytest.mark.docker
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("../fixtures/private/secret.txt", RoleOutcome.ERROR),
        ("../private/secret.txt", RoleOutcome.VIOLATION),
    ],
)
async def test_java_relative_payload_composition_is_not_error_repair(
    tmp_path: Path, payload: str, expected: RoleOutcome
):
    settings = _settings(tmp_path, "java01")
    request = load_investigation_request(ROOT / "evals/fixtures/java01/request.json")
    store = ArtifactStore(settings.artifact_root)
    sandbox = DockerSandbox(settings, store=store)
    prepared = LocalSourceSnapshots(settings, store).prepare(
        request.case, build_manifest(request, settings, sandbox.image_id_for(request.case.recipe))
    )
    reference = Submission.model_validate_json(
        (ROOT / "evals/fixtures/java01/reference.json").read_bytes()
    )
    submission = Submission.model_validate({**reference.model_dump(), "exploit_payload": payload})
    operation = EvidenceInput(
        run_id="java-path-regression",
        operation_id="java-path-regression.r1",
        prepared=prepared,
        submission=submission,
        budget=request.budget,
    )
    observation = await run_evidence(operation, settings, store, sandbox=sandbox)
    assert observation.cleanup_confirmed and observation.artifact
    assert observation.control and observation.control.outcome is RoleOutcome.HELD
    assert observation.control.target_executed
    assert observation.adversarial and observation.adversarial.outcome is expected
    if expected is RoleOutcome.ERROR:
        # Keep the failed native execution explicit; never normalize it into a safe hold.
        assert not observation.adversarial.target_executed
        assert observation.adversarial.native_exit_code != 0
    else:
        assert observation.adversarial.target_executed
        assert request.case.finding.line in observation.adversarial.covered_lines
        assert observation.feedback is None
    # Reconciliation returns the exact immutable receipt, not a different repaired payload.
    assert await run_evidence(operation, settings, store, sandbox=sandbox) == observation
