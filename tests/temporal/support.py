"""Shared native test/probe operations; no service startup or implicit downloads."""

import asyncio
from pathlib import Path

from temporalio.api.enums.v1 import EventType
from temporalio.worker import Replayer, Worker

from corsair.workflows.fixture import FixtureInvestigation, FixtureStage
from corsair.workflows.fixture_activities import complete_fixture, prepare_fixture


def worker(client, queue):
    return Worker(client, task_queue=queue,
                  workflows=[FixtureInvestigation, FixtureStage],
                  activities=[prepare_fixture, complete_fixture])


async def save_and_replay(handle, destination):
    history = await handle.fetch_history()
    Path(destination).mkdir(parents=True, exist_ok=True)
    path = Path(destination) / f"{handle.id.replace('/', '_')}.json"
    with path.open("x", encoding="utf-8") as output:
        output.write(history.to_json())
    await Replayer(workflows=[FixtureInvestigation, FixtureStage]).replay_workflow(history)
    return history


async def wait_for_child(client, parent_id, *, parent_run_id=None, child_run_id=None):
    parent = client.get_workflow_handle(parent_id, run_id=parent_run_id)
    child = client.get_workflow_handle(parent_id + "/fixture-stage", run_id=child_run_id)
    # Poll only the native read-only query, bounded by the caller's timeout.
    while True:
        description = await parent.describe()
        if description.status.name != "RUNNING":
            raise AssertionError("Parent closed before child became ready")
        history = await parent.fetch_history()
        if any(event.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED
               for event in history.events):
            if await child.query(FixtureStage.waiting):
                return child
        await asyncio.sleep(0.05)
