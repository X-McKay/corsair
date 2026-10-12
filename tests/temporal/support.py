"""Shared native test/probe operations; no service startup or implicit downloads."""

import asyncio
import json
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from temporalio.api.enums.v1 import EventType
from temporalio.worker import Replayer, Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
from temporalio.workflow import SandboxImportNotificationPolicy

from corsair.workflows.fixture import FixtureInvestigation, FixtureStage
from corsair.workflows.fixture_activities import complete_fixture, prepare_fixture

# Server-side bound for native test runs, so a stuck run closes rather than staying open.
EXECUTION_TIMEOUT = timedelta(seconds=60)


def workflow_runner():
    """Default sandbox, warning on late imports and on modules passed through unintentionally."""
    policy = (SandboxImportNotificationPolicy.WARN_ON_DYNAMIC_IMPORT
              | SandboxImportNotificationPolicy.WARN_ON_UNINTENTIONAL_PASSTHROUGH)
    return SandboxedWorkflowRunner(restrictions=SandboxRestrictions.default.with_import_notification_policy(policy))


def fixture_memo(request):
    payload = json.dumps(asdict(request), sort_keys=True).encode("utf-8")
    return {"case": request.scenario, "mode": "durable", "input_digest": sha256(payload).hexdigest()}


def worker(client, queue):
    return Worker(client, task_queue=queue,
                  workflows=[FixtureInvestigation, FixtureStage],
                  activities=[prepare_fixture, complete_fixture],
                  workflow_runner=workflow_runner())


async def save_and_replay(handle, destination):
    history = await handle.fetch_history()
    Path(destination).mkdir(parents=True, exist_ok=True)
    path = Path(destination) / f"{handle.id.replace('/', '_')}.json"
    with path.open("x", encoding="utf-8") as output:
        output.write(history.to_json())
    await Replayer(workflows=[FixtureInvestigation, FixtureStage],
                   workflow_runner=workflow_runner()).replay_workflow(history)
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
