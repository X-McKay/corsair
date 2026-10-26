"""Replay an actual completed Corsair workflow history through Temporal's Replayer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer

from corsair.contracts import Budget, InvestigationResult, RoleOutcome, Verdict
from corsair.workflows.investigation import InvestigationWorkflow
from tests.workflow.temporal import ActivityScenario, investigation_request, temporal_id

HISTORIES = Path(__file__).parent / "histories"

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
    # The recorded result's phase timeline rides in the record activity input; replay
    # must accept it (and histories recorded without it, below).
    assert [entry.phase for entry in result.timeline][-1] == "record"
    assert completed == [
        "corsair.prepare",
        "corsair.produce",
        "corsair.evidence",
        "corsair.audit",
        "corsair.record",
    ]
    assert len(completed) == len(set(completed))
    record = next(
        event.activity_task_scheduled_event_attributes
        for event in history.events
        if event.HasField("activity_task_scheduled_event_attributes")
        and event.activity_task_scheduled_event_attributes.activity_type.name == "corsair.record"
    )
    assert record.schedule_to_close_timeout.seconds == 90
    assert record.start_to_close_timeout.seconds == 30
    replay = await Replayer(
        workflows=[InvestigationWorkflow], data_converter=pydantic_data_converter
    ).replay_workflow(history)
    assert replay.replay_failure is None
    assert dict(activities.call_counts) == calls_before_replay


def _patches(history: WorkflowHistory) -> set[str]:
    return {
        json.loads(event.marker_recorded_event_attributes.details["patch-data"].payloads[0].data)[
            "id"
        ]
        for event in history.events
        if event.HasField("marker_recorded_event_attributes")
        and event.marker_recorded_event_attributes.marker_name == "core_patch"
    }


def _scheduled(history: WorkflowHistory) -> list[str]:
    return [
        event.activity_task_scheduled_event_attributes.activity_type.name
        for event in history.events
        if event.HasField("activity_task_scheduled_event_attributes")
    ]


def _replayer() -> Replayer:
    return Replayer(workflows=[InvestigationWorkflow], data_converter=pydantic_data_converter)


async def test_two_session_history_replays_without_repeating_completed_activities(
    temporal_server, temporal_artifact_store
):
    held = ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),))
    budget = Budget(
        max_rounds=1,
        max_llm_calls=4,
        episode_llm_calls=1,
        max_tool_calls=4,
        max_output_tokens=256,
        max_elapsed_seconds=60,
        probe_timeout_seconds=1,
    )
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, activities):
        handle = await temporal_server.client.start_workflow(
            InvestigationWorkflow.run,
            investigation_request("replay-sessions", budget=budget),
            id=temporal_id("replay-sessions"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
        result = await handle.result()
        history = await handle.fetch_history()
        calls_before_replay = dict(activities.call_counts)

    assert result.verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED
    assert calls_before_replay["corsair.produce"] == 2
    assert "independent-sessions-v1" in _patches(history)
    replay = await _replayer().replay_workflow(history)
    assert replay.replay_failure is None
    assert dict(activities.call_counts) == calls_before_replay


async def test_pre_session_history_with_a_lone_clean_negative_still_replays():
    """Recorded by the single-session workflow (before independent-sessions-v1) with
    budget left for another session. The current workflow must replay it as one
    session: no second producer command, so no non-determinism."""
    history = WorkflowHistory.from_json(
        "pre-sessions-lone-clean-negative",
        (HISTORIES / "pre-sessions-lone-clean-negative.json").read_text(),
    )
    assert "independent-sessions-v1" not in _patches(history)
    assert _scheduled(history).count("corsair.produce") == 1
    replay = await _replayer().replay_workflow(history)
    assert replay.replay_failure is None
