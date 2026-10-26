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


async def test_recorded_activity_options_match_the_time_bound_policy():
    """The single time-bound policy reproduces every option a recorded history holds.

    Moving the activity bounds into ``policies.time_bounds`` must not change one
    scheduled command; a deliberate change needs a ``workflow.patched`` gate.
    """
    from corsair.policies import time_bounds

    history = WorkflowHistory.from_json(
        "pre-sessions-lone-clean-negative",
        (HISTORIES / "pre-sessions-lone-clean-negative.json").read_text(),
    )
    started = next(
        event.workflow_execution_started_event_attributes
        for event in history.events
        if event.HasField("workflow_execution_started_event_attributes")
    )
    budget = Budget.model_validate(json.loads(started.input.payloads[0].data)["budget"])
    remaining = budget.max_elapsed_seconds
    expected = {
        "corsair.prepare": (min(time_bounds.PREPARE_ACTIVITY_SECONDS, remaining),) * 2,
        "corsair.produce": (time_bounds.producer_activity_seconds(budget, 0),) * 2,
        "corsair.evidence": (time_bounds.evidence_activity_seconds(budget),) * 2,
        "corsair.audit": (min(time_bounds.AUDITOR_ACTIVITY_SECONDS, remaining),) * 2,
        "corsair.record": (
            time_bounds.RECORD_ATTEMPT_SECONDS,
            time_bounds.RECORD_FINALIZATION_SECONDS,
        ),
    }
    recorded = {}
    for event in history.events:
        if event.HasField("activity_task_scheduled_event_attributes"):
            options = event.activity_task_scheduled_event_attributes
            recorded[options.activity_type.name] = (
                options.start_to_close_timeout.seconds,
                options.schedule_to_close_timeout.seconds,
            )
            if options.activity_type.name != "corsair.record":
                assert options.heartbeat_timeout.seconds == time_bounds.heartbeat_seconds(
                    options.start_to_close_timeout.seconds
                )
    assert recorded == expected
    replay = await _replayer().replay_workflow(history)
    assert replay.replay_failure is None
