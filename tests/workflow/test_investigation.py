"""Actual Temporal worker tests for Corsair's investigation and batch workflows."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from corsair.contracts import (
    DIAGNOSTIC_TRUNCATION_MARKER,
    MAX_DIAGNOSTIC_TEXT_CHARS,
    TERMINAL_RESULT_MAX_BYTES,
    AuditInput,
    AuditOutput,
    BatchItem,
    BatchRequest,
    Budget,
    Disposition,
    EvidenceInput,
    ExecutionStatus,
    FixStatus,
    InvestigationResult,
    NoGroundedCandidate,
    Observation,
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    RoleOutcome,
    Submission,
    Usage,
    digest,
)
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow
from tests.workflow.temporal import (
    ActivityScenario,
    FakeActivities,
    investigation_request,
    temporal_id,
)

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


def _three_round_budget() -> Budget:
    return Budget(
        max_rounds=3,
        max_llm_calls=6,
        episode_llm_calls=2,
        max_tool_calls=3,
        max_output_tokens=256,
        max_elapsed_seconds=30,
        probe_timeout_seconds=1,
    )


def _producer_submission(output: ProducerOutput) -> Submission:
    submission = output.submission_for_verification()
    assert submission is not None
    return submission


def _maximum_round_budget() -> Budget:
    return Budget(
        max_rounds=16,
        max_llm_calls=32,
        episode_llm_calls=1,
        max_tool_calls=16,
        max_output_tokens=256,
        max_elapsed_seconds=60,
        probe_timeout_seconds=1,
    )


async def test_supported_paired_observation_records_bound_result(
    temporal_server, temporal_artifact_store
):
    request = investigation_request("supported")
    async with temporal_server.worker(temporal_artifact_store) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("supported"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.disposition is Disposition.SUPPORTED
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.result_artifact is not None
    persisted = InvestigationResult.model_validate(
        temporal_artifact_store.get_json(result.result_artifact)
    )
    assert persisted.result_artifact is None
    assert len(result.rounds) == 1
    observation = result.rounds[0].observation
    assert observation is not None
    evidence_input = activities.evidence_inputs[0]
    assert observation.source_digest == evidence_input.prepared.source.sha256
    assert observation.submission_digest == digest(evidence_input.submission)
    assert observation.control and observation.control.outcome is RoleOutcome.HELD
    assert observation.adversarial and observation.adversarial.outcome is RoleOutcome.VIOLATION
    assert observation.control.native_exit_code == 0
    assert observation.adversarial.native_exit_code == 1
    audit_packet = activities.audit_inputs[0].model_dump(mode="json")
    assert "observation" not in audit_packet
    assert "control" not in audit_packet
    assert "adversarial" not in audit_packet


async def test_held_adversarial_results_stay_inconclusive_with_revised_plans(
    temporal_server, temporal_artifact_store
):
    held = ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),) * 3)
    request = investigation_request("inconclusive", budget=_three_round_budget())
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("inconclusive"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.disposition is Disposition.INCONCLUSIVE
    assert result.disposition is not Disposition.REFUTED
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert [_producer_submission(round_.producer).plan.revision for round_ in result.rounds] == [
        1,
        2,
        3,
    ]
    parent_revisions = [
        _producer_submission(round_.producer).plan.parent_revision for round_ in result.rounds
    ]
    assert parent_revisions == [
        None,
        1,
        2,
    ]
    assert [
        item.previous.plan.revision if item.previous else None
        for item in activities.producer_inputs
    ] == [None, 1, 2]


async def test_maximum_round_result_stays_within_terminal_wire_budget(
    temporal_server, temporal_artifact_store
):
    held = ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),) * 16)
    request = investigation_request("maximum-rounds", budget=_maximum_round_budget())
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("maximum-rounds"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert len(result.rounds) == 16
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.result_artifact is not None
    record_payload = (await pydantic_data_converter.encode([activities.record_inputs[-1]]))[0]
    assert len(record_payload.data) <= TERMINAL_RESULT_MAX_BYTES
    assert len(result.model_dump_json().encode()) <= TERMINAL_RESULT_MAX_BYTES
    persisted = InvestigationResult.model_validate(
        temporal_artifact_store.get_json(result.result_artifact)
    )
    assert len(persisted.rounds) == 16


async def test_oversized_activity_error_reason_is_compacted_before_record(
    temporal_server, temporal_artifact_store
):
    scenario = ActivityScenario(
        fail_evidence_reason="native evidence failure: " + "x" * (MAX_DIAGNOSTIC_TEXT_CHARS * 2)
    )
    async with temporal_server.worker(temporal_artifact_store, scenario) as (
        task_queue,
        activities,
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request("oversized-error"),
            id=temporal_id("oversized-error"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.execution_status is ExecutionStatus.ERROR
    assert result.reason.startswith("evidence: ")
    assert result.reason.endswith(DIAGNOSTIC_TRUNCATION_MARKER)
    assert len(result.reason) == MAX_DIAGNOSTIC_TEXT_CHARS
    assert result.usage_complete is True
    assert len(result.rounds) == 1
    assert result.rounds[0].producer.submission_for_verification() is not None
    assert activities.call_counts["corsair.record"] == 1
    record_payload = await pydantic_data_converter.encode([activities.record_inputs[-1]])
    assert len(record_payload[0].data) <= (TERMINAL_RESULT_MAX_BYTES)
    assert result.result_artifact is not None
    persisted = InvestigationResult.model_validate(
        temporal_artifact_store.get_json(result.result_artifact)
    )
    assert persisted.execution_status is ExecutionStatus.ERROR
    assert persisted.reason == result.reason


async def test_prepare_block_is_blocked_and_does_not_manufacture_evidence(
    temporal_server, temporal_artifact_store
):
    blocked = ActivityScenario(block_prepare=True)
    async with temporal_server.worker(temporal_artifact_store, blocked) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request("blocked"),
            id=temporal_id("blocked"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.execution_status is ExecutionStatus.BLOCKED
    assert result.disposition is Disposition.INCONCLUSIVE
    assert result.rounds == []
    assert activities.call_counts["corsair.prepare"] == 1
    assert activities.call_counts["corsair.produce"] == 0
    assert activities.call_counts["corsair.evidence"] == 0
    assert activities.call_counts["corsair.audit"] == 0
    assert activities.call_counts["corsair.record"] == 1


async def test_producer_abstention_is_inconclusive_and_skips_target_execution(
    temporal_server, temporal_artifact_store
):
    from temporalio import activity

    class AbstainingActivities(FakeActivities):
        @activity.defn(name="corsair.produce")
        async def produce(self, request: ProducerInput) -> ProducerOutput:
            self.call_counts["corsair.produce"] += 1
            self.producer_inputs.append(request)
            self.produce_started.set()
            return ProducerOutput(
                decision=ProducerDecision(
                    root=NoGroundedCandidate(
                        reason="The admitted source does not ground an allowed payload candidate."
                    )
                ),
                usage=Usage(llm_calls=1, tool_calls=1),
            )

    activities = AbstainingActivities(temporal_artifact_store)
    identity, queue = temporal_id("abstention"), temporal_id("abstention-queue")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request(),
            id=identity,
            task_queue=queue,
            result_type=InvestigationResult,
        )

    assert result.disposition is Disposition.INCONCLUSIVE
    assert result.disposition is not Disposition.REFUTED
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.reason.startswith("Producer abstained:")
    assert result.manifest is not None
    assert len(result.rounds) == 1
    producer = result.rounds[0].producer
    assert producer.usage == Usage(llm_calls=1, tool_calls=1)
    assert producer.decision is not None
    assert isinstance(producer.decision.root, NoGroundedCandidate)
    assert activities.call_counts["corsair.evidence"] == 0
    assert activities.call_counts["corsair.audit"] == 0
    assert activities.evidence_inputs == []
    assert activities.audit_inputs == []
    assert temporal_artifact_store.reconcile(f"result.{identity}")


async def test_worker_restart_after_completed_prepare_runs_only_remaining_activities(
    temporal_server, temporal_artifact_store
):
    task_queue = temporal_id("restart")
    workflow_id = temporal_id("restart")
    first = FakeActivities(temporal_artifact_store, ActivityScenario(pause_prepare=True))
    workflow_worker = Worker(
        temporal_server.client,
        task_queue=task_queue,
        workflows=[InvestigationWorkflow, EvaluationWorkflow],
    )
    first_activity_worker = Worker(
        temporal_server.client,
        task_queue=task_queue,
        activities=first.registered(),
        graceful_shutdown_timeout=timedelta(seconds=5),
    )
    async with workflow_worker:
        async with first_activity_worker:
            handle = await temporal_server.client.start_workflow(
                InvestigationWorkflow.run,
                investigation_request("restart"),
                id=workflow_id,
                task_queue=task_queue,
                result_type=InvestigationResult,
            )
            await asyncio.wait_for(first.prepare_started.wait(), timeout=15)
            shutdown = asyncio.create_task(first_activity_worker.shutdown())
            await asyncio.sleep(0)
            first.release_prepare.set()
            await asyncio.wait_for(shutdown, timeout=15)

        assert first.call_counts["corsair.prepare"] == 1
        assert first.prepare_completed.is_set()
        assert first.call_counts["corsair.produce"] == 0
        second = FakeActivities(temporal_artifact_store)
        async with Worker(
            temporal_server.client,
            task_queue=task_queue,
            activities=second.registered(),
        ):
            result = await handle.result()

    assert result.disposition is Disposition.SUPPORTED
    assert second.call_counts["corsair.prepare"] == 0
    assert second.call_counts["corsair.produce"] == 1
    assert second.call_counts["corsair.evidence"] == 1
    assert second.call_counts["corsair.audit"] == 1
    assert second.call_counts["corsair.record"] == 1


async def test_fix_demonstration_blocked_does_not_erase_positive_result(
    temporal_server, temporal_artifact_store
):
    async with temporal_server.worker(temporal_artifact_store) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request("fixed", fixed=True),
            id=temporal_id("fixed"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.disposition is Disposition.SUPPORTED
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.fix_status is FixStatus.DEMONSTRATION_BLOCKED
    assert result.fix_observation is not None
    assert result.fix_observation.adversarial
    assert result.fix_observation.adversarial.outcome is RoleOutcome.HELD
    original = result.rounds[0].observation
    assert original is not None
    assert original.adversarial and original.adversarial.outcome is RoleOutcome.VIOLATION
    assert activities.evidence_inputs[1].fixed is True
    assert (
        result.fix_observation.source_digest
        == activities.evidence_inputs[1].prepared.fixed_source.sha256
    )


async def test_batch_returns_compact_artifact_items_and_child_failures(
    temporal_server, temporal_artifact_store
):
    request = BatchRequest(
        batch_id=temporal_id("batch"),
        requests=[investigation_request("batchok"), investigation_request("batchbad")],
        repeats=1,
        concurrency=2,
    )
    scenario = ActivityScenario(fail_record_case_ids=frozenset({"batchbad"}))
    async with temporal_server.worker(temporal_artifact_store, scenario) as (
        task_queue,
        _activities,
    ):
        items = await temporal_server.client.execute_workflow(
            EvaluationWorkflow.run,
            request,
            id=temporal_id("evaluation"),
            task_queue=task_queue,
            result_type=list[BatchItem],
        )

    assert len(items) == 2
    good, failed = items
    assert good.case_id == "batchok"
    assert good.artifact is not None and good.error is None
    assert len(good.model_dump_json()) < 400
    persisted = InvestigationResult.model_validate(temporal_artifact_store.get_json(good.artifact))
    assert persisted.case_id == good.case_id
    assert failed.case_id == "batchbad"
    assert failed.artifact is None
    assert failed.error


async def test_cancelled_episode_records_cancelled_result_before_close(
    temporal_server, temporal_artifact_store
):
    paused = ActivityScenario(pause_produce=True)
    workflow_id = temporal_id("cancel")
    async with temporal_server.worker(temporal_artifact_store, paused) as (task_queue, activities):
        handle = await temporal_server.client.start_workflow(
            InvestigationWorkflow.run,
            investigation_request("cancelled"),
            id=workflow_id,
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
        await asyncio.wait_for(activities.produce_started.wait(), timeout=15)
        await handle.cancel(reason="exercise durable cancellation record")
        result = await handle.result()
        await asyncio.wait_for(activities.recorded.wait(), timeout=15)

    cancelled = activities.record_inputs[-1]
    assert activities.produce_cancelled.is_set()
    assert result.execution_status is ExecutionStatus.CANCELLED
    assert cancelled.execution_status is ExecutionStatus.CANCELLED
    record_ref = temporal_artifact_store.reconcile(f"result.{workflow_id}")
    assert record_ref is not None
    persisted = InvestigationResult.model_validate(temporal_artifact_store.get_json(record_ref))
    assert persisted.execution_status is ExecutionStatus.CANCELLED


@pytest.mark.parametrize("phase", ["evidence", "audit"])
async def test_failed_later_activity_preserves_completed_producer_round(
    temporal_server, temporal_artifact_store, phase
):
    from temporalio import activity
    from temporalio.exceptions import ApplicationError

    class FailingActivities(FakeActivities):
        @activity.defn(name="corsair.evidence")
        async def evidence(self, request: EvidenceInput) -> Observation:
            if phase == "evidence":
                raise ApplicationError("test native operation failed", non_retryable=True)
            return await super().evidence(request)

        @activity.defn(name="corsair.audit")
        async def audit(self, request: AuditInput) -> AuditOutput:
            del request  # Typed native activity signature; this scenario fails unconditionally.
            raise ApplicationError("test audit failed after its invocation", non_retryable=True)

    activities = FailingActivities(temporal_artifact_store)
    identity, queue = temporal_id("lost-episode"), temporal_id("lost-queue")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request(),
            id=identity,
            task_queue=queue,
        )
    assert result.execution_status == ExecutionStatus.ERROR
    assert len(result.rounds) == 1
    assert _producer_submission(result.rounds[0].producer)
    assert result.rounds[0].producer.usage.llm_calls == 1
    assert result.rounds[0].producer.usage.tool_calls == 1
    assert bool(result.rounds[0].observation) == (phase == "audit")
    assert result.usage_complete == (phase == "evidence")
    assert temporal_artifact_store.reconcile(f"result.{identity}")


async def test_oversized_structured_result_fails_workflow_not_workflow_tasks(
    temporal_server, temporal_artifact_store
):
    from temporalio import activity
    from temporalio.client import WorkflowFailureError
    from temporalio.exceptions import ApplicationError

    class LargePlans(FakeActivities):
        @activity.defn(name="corsair.produce")
        async def produce(self, request: ProducerInput) -> ProducerOutput:
            producer = await super().produce(request)
            submission = producer.submission_for_verification()
            assert submission is not None
            plan = submission.plan.model_copy(update={"next_steps": ["x" * 70_000]})
            return ProducerOutput(
                submission=submission.model_copy(update={"plan": plan}),
                usage=producer.usage,
                feedback=producer.feedback,
            )

    activities = LargePlans(
        temporal_artifact_store,
        ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),)),
    )
    queue, identity = temporal_id("oversize-queue"), temporal_id("oversize-result")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        with pytest.raises(WorkflowFailureError) as rejected:
            await asyncio.wait_for(
                temporal_server.client.execute_workflow(
                    InvestigationWorkflow.run,
                    investigation_request("oversize", budget=_maximum_round_budget()),
                    id=identity,
                    task_queue=queue,
                ),
                timeout=45,
            )
    assert isinstance(rejected.value.cause, ApplicationError)
    assert rejected.value.cause.type == "TERMINAL_PAYLOAD_INVALID"
    assert activities.record_inputs == []
    assert len(activities.producer_inputs) == 16
