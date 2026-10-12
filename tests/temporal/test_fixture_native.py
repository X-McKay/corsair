"""Real history/replay/cancellation and graceful worker replacement on owned service."""

import asyncio
from uuid import uuid4

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import CancelledError

from corsair.workflows.fixture import FixtureInvestigation, FixtureStage
from corsair.workflows.fixture_contracts import FixtureRequest
from tests.temporal.support import save_and_replay, wait_for_child, worker


@pytest.mark.parametrize("scenario,outcome,prepare_attempts,operation_attempts", [
    ("success", "completed", 1, 1), ("transient", "completed", 3, 1),
    ("permanent", "failed", 1, 0), ("unknown", "unknown", 1, 1),
])
def test_native_parent_child_failure_retry_and_replay(
    temporal_address, request, scenario, outcome, prepare_attempts, operation_attempts,
):
    async def check():
        client = await Client.connect(temporal_address)
        identity = "corsair-fixture-" + str(uuid4())
        async with worker(client, identity):
            handle = await client.start_workflow(
                FixtureInvestigation.run, FixtureRequest(identity, "fixture", scenario),
                id=identity, task_queue=identity,
            )
            result = await asyncio.wait_for(handle.result(), timeout=30)
            assert (result.outcome, result.prepare_attempts, result.operation_attempts) == (
                outcome, prepare_attempts, operation_attempts,
            )
            assert result.value == ("fixture" if outcome == "completed" else None)
            assert result.cleanup == "not_required"
        destination = request.config.getoption("--temporal-evidence-dir")
        await save_and_replay(handle, destination)
        child = client.get_workflow_handle(identity + "/fixture-stage")
        history = await save_and_replay(child, destination)
        scheduled = [e.activity_task_scheduled_event_attributes.activity_type.name
                     for e in history.events
                     if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED]
        assert scheduled == (["prepare_fixture"] if scenario == "permanent"
                             else ["prepare_fixture", "complete_fixture"])
    asyncio.run(check())


def test_native_parent_cancels_waiting_child(temporal_address, request):
    async def check():
        client = await Client.connect(temporal_address)
        identity = "corsair-cancel-" + str(uuid4())
        async with worker(client, identity):
            parent = await client.start_workflow(
                FixtureInvestigation.run, FixtureRequest(identity, "fixture", wait_for_release=True),
                id=identity, task_queue=identity,
            )
            child = await asyncio.wait_for(wait_for_child(client, identity), 30)
            await parent.cancel()
            with pytest.raises(WorkflowFailureError) as failure:
                await asyncio.wait_for(parent.result(), 30)
            assert isinstance(failure.value.cause, CancelledError)
            with pytest.raises(WorkflowFailureError) as child_failure:
                await asyncio.wait_for(child.result(), 30)
            assert isinstance(child_failure.value.cause, CancelledError)
        destination = request.config.getoption("--temporal-evidence-dir")
        await save_and_replay(parent, destination)
        history = await save_and_replay(child, destination)
        assert not any(e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
                       and e.activity_task_scheduled_event_attributes.activity_type.name == "complete_fixture"
                       for e in history.events)
    asyncio.run(check())


def test_native_worker_replacement_reuses_completed_activity(temporal_address, request):
    async def check():
        client = await Client.connect(temporal_address)
        identity = "corsair-replace-" + str(uuid4())
        async with worker(client, identity):
            parent = await client.start_workflow(
                FixtureInvestigation.run, FixtureRequest(identity, "fixture", wait_for_release=True),
                id=identity, task_queue=identity,
            )
            child = await asyncio.wait_for(wait_for_child(client, identity), 30)
        # A fresh Worker has no cached workflow instance; native history restores it.
        async with worker(client, identity):
            await child.signal(FixtureStage.release)
            result = await asyncio.wait_for(parent.result(), 30)
            assert result.value == "fixture"
            assert (result.prepare_attempts, result.operation_attempts) == (1, 1)
        destination = request.config.getoption("--temporal-evidence-dir")
        await save_and_replay(parent, destination)
        history = await save_and_replay(child, destination)
        assert sum(e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
                   for e in history.events) == 2
    asyncio.run(check())
