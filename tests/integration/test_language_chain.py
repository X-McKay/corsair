"""Real language-native evidence and durable consumers; scripted ADK, not model accuracy."""

import os
from pathlib import Path

import pytest
from temporalio.worker import Worker

from corsair.adapters.inference.adk import AdkInference
from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import AssessmentOutcome, Budget, EvidenceInput, Submission
from corsair.entrypoints.requests import load_investigation_request
from corsair.evaluation.scoring import AssessmentOracle, score
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.steps.evidence import run_evidence
from corsair.steps.manifest import build_manifest
from corsair.workflows.investigation import InvestigationWorkflow
from tests.integration.test_chain import ReferenceModel
from tests.workflow.temporal import temporal_id

ROOT = Path(__file__).resolve().parents[2]


def _settings(tmp_path: Path, case_id: str) -> Settings:
    language = "NODE" if case_id.startswith("node") else "JAVA"
    if os.environ.get(f"CORSAIR_TEST_{language}") != "1":
        pytest.skip(f"set CORSAIR_TEST_{language}=1 after building its reviewed image")
    return Settings(
        source_root=str(ROOT),
        artifact_root=str(tmp_path / "artifacts"),
        node_image=os.environ.get("CORSAIR_TEST_NODE_IMAGE", "corsair-node:0.1"),
        java_image=os.environ.get("CORSAIR_TEST_JAVA_IMAGE", "corsair-java:0.1"),
    )


@pytest.mark.docker
@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["node01", "node02", "java01", "java02"])
async def test_language_reference_verifier_receipts_and_reconciliation(tmp_path, case_id):
    settings = _settings(tmp_path, case_id)
    request = load_investigation_request(ROOT / f"evals/fixtures/{case_id}/request.json")
    store = ArtifactStore(settings.artifact_root)
    sandbox = DockerSandbox(settings, store=store)
    image_id = sandbox.image_id_for(request.case.recipe)
    prepared = LocalSourceSnapshots(settings, store).prepare(
        request.case, build_manifest(request, settings, image_id)
    )
    submission = Submission.model_validate_json(
        (ROOT / f"evals/fixtures/{case_id}/reference.json").read_bytes()
    )
    operation = EvidenceInput(
        run_id=f"reference-{case_id}",
        operation_id=f"reference-{case_id}.r1",
        prepared=prepared,
        submission=submission,
        budget=request.budget,
    )
    observation = await run_evidence(operation, settings, store, sandbox=sandbox)
    assert observation.feedback is None, observation.model_dump_json()
    assert observation.cleanup_confirmed
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial
    expected = "VIOLATION" if case_id.endswith("01") else "PROPERTY_HELD"
    assert observation.adversarial.outcome.value == expected
    assert request.case.finding.line in observation.control.covered_lines
    assert request.case.finding.line in observation.adversarial.covered_lines
    assert observation.artifact is not None
    assert await run_evidence(operation, settings, store, sandbox=sandbox) == observation


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("case_id", ["node01", "node02", "java01", "java02"])
async def test_language_adk_temporal_assessment_and_external_scoring(
    temporal_server, tmp_path, case_id
):
    settings = _settings(tmp_path, case_id)
    request = load_investigation_request(ROOT / f"evals/fixtures/{case_id}/request.json")
    # Explicit one-pair conformance protocol, separate from frozen live cohort budgets.
    request = request.model_copy(update={"budget": Budget(max_rounds=1)})
    store = ArtifactStore(settings.artifact_root)
    activities = Activities(
        settings,
        store=store,
        inference=AdkInference(
            settings, store, ReferenceModel(model="scripted-language-conformance")
        ),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=DockerSandbox(settings, store=store),
    )
    queue, identity = temporal_id("language-queue"), temporal_id("language-run")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run, request, id=identity, task_queue=queue
        )
    expected = (
        AssessmentOutcome.DEMONSTRATED
        if case_id.endswith("01")
        else AssessmentOutcome.NOT_DEMONSTRATED
    )
    assert result.assessment_outcome is expected, result.model_dump_json()
    assert result.result_artifact and store.reconcile(f"result.{identity}")
    assert result.manifest and result.manifest.image_id
    scored = score(
        result,
        AssessmentOracle(schema_version="corsair.assessment-oracle/1", acceptable=[expected]),
        store,
    )
    assert scored["status"] == "pass", scored
    assert scored["evidence_valid"] is True


@pytest.mark.docker
@pytest.mark.parametrize("case_id", ["node01", "node02", "java01", "java02"])
def test_language_reference_cli_json_is_valid_and_machine_clean(tmp_path: Path, case_id: str):
    import subprocess
    import sys

    from corsair.contracts import Observation

    settings = _settings(tmp_path, case_id)
    configuration = tmp_path / "settings.json"
    configuration.write_text(settings.model_dump_json())
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "corsair.entrypoints.cli",
            "verify",
            str(ROOT / f"evals/fixtures/{case_id}/request.json"),
            str(ROOT / f"evals/fixtures/{case_id}/reference.json"),
            "--settings",
            str(configuration),
            "--format",
            "json",
            "--log-format",
            "json",
            "--no-animation",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr
    assert "\x1b" not in run.stdout
    observation = Observation.model_validate_json(run.stdout)
    assert observation.feedback is None and observation.cleanup_confirmed
    assert observation.control and observation.adversarial and observation.artifact
    assert observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial.outcome.value == (
        "VIOLATION" if case_id.endswith("01") else "PROPERTY_HELD"
    )


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
async def test_language_assessment_batch_and_rescore_use_committed_result_refs(
    temporal_server, tmp_path, capsys
):
    import json

    from corsair.entrypoints.cli import execute, parser
    from corsair.workflows.evaluation import EvaluationWorkflow

    _settings(tmp_path, "java01")
    base = _settings(tmp_path, "node01")
    queue = temporal_id("assessment-queue")
    settings = base.model_copy(
        update={
            "task_queue": queue,
            "temporal_address": temporal_server.client.service_client.config.target_host,
        }
    )
    config = tmp_path / "settings.json"
    config.write_text(settings.model_dump_json())
    report = tmp_path / "assessment-batch.json"
    store = ArtifactStore(settings.artifact_root)
    activities = Activities(
        settings,
        store=store,
        inference=AdkInference(settings, store, ReferenceModel(model="scripted-assessment-batch")),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=DockerSandbox(settings, store=store),
    )
    dataset = str(ROOT / "evals/datasets/node-java-assessments.json")
    args = parser().parse_args(
        [
            "eval",
            dataset,
            "--settings",
            str(config),
            "--run-id",
            temporal_id("assessment-batch"),
            "--concurrency",
            "2",
            "--output",
            str(report),
            "--format",
            "json",
            "--no-animation",
        ]
    )
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow, EvaluationWorkflow],
        activities=activities.registered(),
    ):
        assert await execute(args) == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured["summary"]["passed"] == 4
    saved = json.loads(report.read_text())
    assert all(row["evidence_valid"] and row["status"] == "pass" for row in saved["rows"])
    run_ids = [row["run_id"] for row in saved["rows"]]
    rescore = parser().parse_args(
        ["rescore", dataset, *run_ids, "--settings", str(config), "--format", "json"]
    )
    assert await execute(rescore) == 0
    rescored = json.loads(capsys.readouterr().out)
    assert rescored["summary"]["passed"] == 4
    assert rescored["summary"]["assessment_completed"] == 4
