"""Recipe-free entrypoints and activities admit the current environment explicitly."""

from unittest.mock import AsyncMock

import pytest

from corsair.contracts.execution import ExecutionRequest
from corsair.contracts.intake import ImageInventory
from corsair.entrypoints.api import start_execution
from corsair.entrypoints.cli import parser
from corsair.entrypoints.requests import load_execution_request
from corsair.policies.execution import admit_execution_image
from corsair.settings import Settings
from tests.unit.execution import round_input


def test_new_request_has_no_recipe_and_uses_relative_sources(tmp_path):
    request = round_input().prepared.request
    file = tmp_path / "request.json"
    file.write_text(request.model_dump_json())
    result = load_execution_request(file)
    assert result.source.path == str(tmp_path / "repository")
    assert "recipe" not in ExecutionRequest.model_fields
    assert parser().parse_args(["investigate", str(file)]).command == "investigate"


def test_unavailable_or_changed_image_is_not_admitted():
    request = round_input().prepared.request
    with pytest.raises(ValueError):
        admit_execution_image(request, ImageInventory())
    admit_execution_image(request, ImageInventory(images=[request.image]))


@pytest.mark.asyncio
async def test_api_starts_separate_versioned_workflow():
    client = AsyncMock()
    request = round_input().prepared.request
    await start_execution(client, request, Settings(), run_id="test")
    arguments = client.start_workflow.call_args
    assert arguments.args[0].__qualname__ == "ExecutionWorkflow.run"
    assert arguments.args[1] == request


@pytest.mark.asyncio
async def test_cancelled_execution_waits_for_bounded_cleanup(tmp_path, monkeypatch):
    import asyncio
    import threading
    import time

    from corsair.adapters.inference.execution import execution_resources_digest
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.execution import ExecutePlanInput, PlanAudit, ProcessObservation
    from corsair.steps.execution import ExecutionActivities
    from tests.unit.execution import plan

    started = threading.Event()
    cleaned = threading.Event()
    settings = Settings(artifact_root=str(tmp_path))
    prepared = round_input().prepared.model_copy(
        update={
            "config_digest": settings.identity,
            "resources_digest": execution_resources_digest(),
        }
    )

    def execute(_self, _prepared, _plan, identity, **_kwargs):
        started.set()
        time.sleep(0.05)
        cleaned.set()
        return ProcessObservation(
            operation_id=identity,
            source_digest=prepared.source.sha256,
            image_id=prepared.request.image.image_id,
            plan_digest="0" * 64,
        )

    monkeypatch.setattr("corsair.steps.execution.DockerExecutor.execute", execute)
    store = ArtifactStore(tmp_path)
    prepared = prepared.model_copy(update={"artifact": store.put_json(prepared)})
    activities = ExecutionActivities(settings, store)
    task = asyncio.create_task(
        activities.execute(
            ExecutePlanInput(
                prepared=prepared,
                plan=plan(),
                audit=PlanAudit(decision="accepted"),
                timeout_seconds=5,
            )
        )
    )
    await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
