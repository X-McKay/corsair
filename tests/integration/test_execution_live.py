"""Explicit live-chain attempt; completion of the test is not reproduction success."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from temporalio.worker import Worker

from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source
from corsair.contracts.execution import ExecutionRequest
from corsair.contracts.intake import Issue
from corsair.entrypoints.api import start_execution
from corsair.settings import load_settings
from corsair.steps.execution import ExecutionActivities
from corsair.workflows.execution import ExecutionWorkflow
from tests.workflow.temporal import temporal_id

pytestmark = [
    pytest.mark.live,
    pytest.mark.docker,
    pytest.mark.temporal,
    pytest.mark.asyncio(loop_scope="module"),
]


async def test_live_v3_attempt_preserves_actual_result(temporal_server):
    configured = os.environ.get("CORSAIR_LIVE_CONFIG")
    if configured is None:
        pytest.skip("explicit live configuration required")
    root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (root / "evals/fixtures/execution-roles/producer-traversal/input.json").read_bytes()
    )
    settings = load_settings(configured)
    with TemporaryDirectory(prefix="execution-live-", dir=root / ".work") as directory:
        repository = Path(directory) / "repository"
        repository.mkdir()
        for path, content in payload["source"].items():
            (repository / path).write_text(content)
        settings = settings.model_copy(
            update={"source_root": directory, "task_queue": temporal_id("live-v3")}
        )
        store = ArtifactStore(settings.artifact_root)
        image = next(
            image for image in discover_images(settings).images if image.language == "python"
        )
        request = ExecutionRequest(
            case_id="synthetic-traversal",
            issue=Issue.model_validate(payload["issue"]),
            source=Source(path=str(repository)),
            image=image,
            budget={"max_rounds": 1, "episode_llm_calls": 2, "max_elapsed_seconds": 180},
        )
        activities = ExecutionActivities(settings, store)
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[ExecutionWorkflow],
            activities=activities.registered(),
        ):
            handle = await start_execution(
                temporal_server.client, request, settings, run_id=temporal_id("live-v3")
            )
            result = await handle.result()
        assert result.result_artifact is not None
        assert result.result_artifact == store.reconcile(f"execution-result.{result.run_id}")
        assert result.security_assessment == "UNRESOLVED"
        report = {
            "cohort": "full-live-chain-attempt",
            "outcome": result.outcome,
            "error": result.error,
            "round_errors": [item.error for item in result.rounds],
            "audits": [
                None if item.audit is None else item.audit.model_dump() for item in result.rounds
            ],
            "execution_observed": any(item.observation is not None for item in result.rounds),
            "result_artifact": result.result_artifact.model_dump(),
            "run_id": result.run_id,
            "cost_usd": None,
        }
        (Path(settings.artifact_root) / "live-chain.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
