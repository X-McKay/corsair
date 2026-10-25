"""Replay an actual completed Corsair workflow history through Temporal's Replayer."""

from __future__ import annotations

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer

from corsair.contracts import InvestigationResult
from corsair.workflows.investigation import InvestigationWorkflow
from tests.fixtures.temporal import investigation_request, temporal_id

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


async def test_fetched_history_replays_without_repeating_completed_activities(
    temporal_server, temporal_artifact_store
):
    workflow_id = temporal_id("replay")
    async with temporal_server.worker(temporal_artifact_store) as (task_queue, activities):
        handle = await temporal_server.client.start_workflow(
            InvestigationWorkflow.run,
            investigation_request("replay"),
            id=workflow_id,
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
        result = await handle.result()
        history = await handle.fetch_history()
        scheduled = {
            event.event_id: event.activity_task_scheduled_event_attributes.activity_type.name
            for event in history.events
            if event.HasField("activity_task_scheduled_event_attributes")
        }
        completed = [
            scheduled[event.activity_task_completed_event_attributes.scheduled_event_id]
            for event in history.events
            if event.HasField("activity_task_completed_event_attributes")
        ]
        calls_before_replay = dict(activities.call_counts)

    assert result.result_artifact is not None
    assert completed == [
        "corsair.prepare",
        "corsair.produce",
        "corsair.evidence",
        "corsair.audit",
        "corsair.record",
    ]
    assert len(completed) == len(set(completed))
    replay = await Replayer(
        workflows=[InvestigationWorkflow], data_converter=pydantic_data_converter
    ).replay_workflow(history)
    assert replay.replay_failure is None
    assert dict(activities.call_counts) == calls_before_replay
