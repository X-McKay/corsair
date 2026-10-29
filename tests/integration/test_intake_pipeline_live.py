"""Opt-in whole production workflow: real models, Temporal, Docker and CLI."""

import json
import os
from pathlib import Path

import pytest

from corsair.adapters.sandboxing.images import discover_images
from corsair.contracts import ArtifactRef, InvestigationResult, PreparedCase
from corsair.contracts.intake_agent import ImageCandidate
from corsair.contracts.intake_pipeline import IntakeInvestigationResult
from corsair.entrypoints.cli import execute, parser
from corsair.entrypoints.requests import load_investigation_request
from corsair.entrypoints.worker import compose_worker, compose_worker_activities
from corsair.settings import load_settings
from tests.workflow.temporal import temporal_id

pytestmark = [
    pytest.mark.live,
    pytest.mark.docker,
    pytest.mark.temporal,
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest.mark.parametrize("case", ["supported", "outside", "unsupported", "binding_missing"])
async def test_live_issue_to_selected_image_and_production_agents(temporal_server, capsys, case):
    config_path = os.environ.get("CORSAIR_LIVE_CONFIG")
    if not config_path:
        pytest.skip("explicit all-role provider configuration required")
    root = Path(__file__).resolve().parents[2]
    configured = load_settings(config_path)
    request = load_investigation_request(root / "evals/fixtures/case01/request.json")
    identity = temporal_id("live-intake-pipeline")
    workspace = Path(configured.artifact_root).resolve() / identity
    workspace.mkdir(parents=True)
    selected_reference = configured.image_for(request.case.recipe.kind)
    unavailable_default = f"corsair-intake-unavailable:{identity}"
    settings = configured.model_copy(
        update={
            "source_root": str(root),
            "artifact_root": str(workspace / "artifacts"),
            "image": unavailable_default,
            "images": {request.case.recipe.kind: unavailable_default},
            "intake_images": []
            if case == "unsupported"
            else [
                ImageCandidate(
                    reference=selected_reference, language="python", execution_mode="callable"
                )
            ],
            "task_queue": temporal_id("live-intake-worker"),
            "temporal_address": temporal_server.client.service_client.config.target_host,
            "temporal_namespace": temporal_server.client.namespace,
        }
    )
    inventory = discover_images(settings)
    assert [image.reference for image in inventory.images] == (
        [] if case == "unsupported" else [selected_reference]
    )
    payload = {
        "findings": [
            {
                "summary": request.case.finding.title,
                "details": request.case.finding.description,
                "source": {"path": request.case.finding.file, "symbol": "read_file"},
            }
        ]
    }
    if case == "outside":
        payload = {
            "title": "Rename helper",
            "description": ("A cosmetic function rename only. No security defect is reported."),
        }
    settings_path = workspace / "settings.json"
    settings_path.write_text(settings.model_dump_json())
    issue_path = workspace / "issue.json"
    issue_path.write_text(json.dumps(payload))
    binding_path = workspace / "binding.json"
    binding_path.write_text(request.model_dump_json())
    arguments = ["investigate"]
    arguments.extend(
        ["--source", request.case.source.path] if case == "binding_missing" else [str(binding_path)]
    )
    arguments.extend(
        [
            "--json",
            str(issue_path),
            "--settings",
            str(settings_path),
            "--run-id",
            identity,
            "--wait",
            "--format",
            "json",
        ]
    )
    activities = compose_worker_activities(settings)
    store = activities.store
    async with compose_worker(temporal_server.client, settings, activities):
        exit_code = await execute(parser().parse_args(arguments))
        emitted = json.loads(capsys.readouterr().out)
        handle = temporal_server.client.get_workflow_handle(
            identity, result_type=IntakeInvestigationResult
        )
        result = await handle.result()
        history = await handle.fetch_history()
    (workspace / "history.json").write_text(history.to_json())
    child = (
        InvestigationResult.model_validate(store.get_json(result.investigation_result))
        if result.investigation_result is not None
        else None
    )
    summary = {
        "run_id": identity,
        "case": case,
        "config_digest": settings.identity,
        "status": result.status,
        "stop_reason": result.stop_reason,
        "intake_classification": None
        if result.intake is None
        else result.intake.decision.classification,
        "selected_image": None if result.intake is None else result.intake.decision.image_id,
        "default_image": unavailable_default,
        "execution_status": None if child is None else child.execution_status,
        "verdict": None if child is None else child.verdict,
        "models": settings.models.model_dump(),
        "usage": result.usage.model_dump(),
        "result_artifact": result.result_artifact,
    }
    (workspace / "summary.json").write_text(json.dumps(summary, default=str, indent=2))
    assert result.result_artifact is not None
    assert emitted["result_artifact"] == result.result_artifact.model_dump()
    assert store.reconcile(f"intake-investigation.{identity}") == result.result_artifact
    assert result.intake is not None and result.intake.usage.llm_calls > 0
    children = {
        event.start_child_workflow_execution_initiated_event_attributes.workflow_type.name
        for event in history.events
        if event.HasField("start_child_workflow_execution_initiated_event_attributes")
    }
    if case != "supported":
        assert exit_code == 1
        assert result.status == "stopped"
        assert (
            result.stop_reason
            == {
                "outside": "OUT_OF_SCOPE",
                "unsupported": "UNSUPPORTED",
                "binding_missing": "TARGET_BINDING_REQUIRED",
            }[case]
        )
        assert child is None and result.investigation_run_id is None
        assert children == {"corsair.intake"}
        return
    assert exit_code == 0 and result.status == "investigation_finished"
    assert children == {"corsair.intake", "corsair.investigation"}
    assert child is not None and child.execution_status == "COMPLETED"
    assert child.manifest is not None
    assert child.manifest.image_reference == selected_reference != unavailable_default
    assert (
        child.manifest.image_id == result.intake.decision.image_id == inventory.images[0].image_id
    )
    assert child.manifest.models == {
        "producer": settings.models.producer,
        "auditor": settings.models.auditor,
    }
    assert sum(item.producer.usage.llm_calls for item in child.rounds) > 0
    assert any(item.audit is not None and item.audit.usage.llm_calls > 0 for item in child.rounds)
    observations = [item.observation for item in child.rounds if item.observation is not None]
    assert child.fix_observation is not None
    observations.append(child.fix_observation)
    assert observations
    for observation in observations:
        assert observation.feedback is None and observation.cleanup_confirmed
        assert observation.control is not None and observation.adversarial is not None
        assert observation.control.target_executed and observation.adversarial.target_executed
        assert observation.artifact is not None
        bundle = store.get_json(observation.artifact)
        prepared = PreparedCase.model_validate(
            store.get_json(ArtifactRef.model_validate(bundle["prepared"]))
        )
        assert prepared.manifest == child.manifest
        for role in ("control", "adversarial"):
            raw = store.get_json(ArtifactRef.model_validate(bundle["roles"][role]))
            assert raw["image_id"] == child.manifest.image_id
            assert raw["container_id"] and raw["cleanup_confirmed"] is True
