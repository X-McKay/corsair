"""Actual Temporal worker tests for Corsair's investigation and batch workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

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
    PlanRevision,
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    ProducerProposal,
    RoleOutcome,
    Scope,
    Submission,
    Usage,
    Verdict,
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


def _audit_input(
    *, llm_call_limit: int | None = None, tool_call_limit: int | None = None
) -> AuditInput:
    request = investigation_request()
    limits = {}
    if llm_call_limit is not None:
        limits["llm_call_limit"] = llm_call_limit
    if tool_call_limit is not None:
        limits["tool_call_limit"] = tool_call_limit
    return AuditInput(
        finding=request.case.finding,
        recipe=request.case.recipe,
        source_excerpt="4: return payload\n",
        submission=Submission(
            control_payload="hello.txt",
            exploit_payload="../private/secret.txt",
            hypothesis="The configured target returns an attacker-controlled payload.",
            plan=PlanRevision(
                revision=1,
                objective="exercise the submitted control and adversarial payload pair",
                next_steps=["submit the pair to trusted evidence collection"],
                reason="the submitted source configuration admits this pair",
            ),
        ),
        max_output_tokens=256,
        **limits,
    )


async def test_audit_input_episode_limits_are_bounded_and_allow_exhausted_admission():
    defaults = _audit_input()

    assert defaults.llm_call_limit == 2
    assert defaults.tool_call_limit == 4
    assert _audit_input(llm_call_limit=0, tool_call_limit=0).model_dump(
        include={"llm_call_limit", "tool_call_limit"}
    ) == {"llm_call_limit": 0, "tool_call_limit": 0}
    with pytest.raises(ValueError):
        _audit_input(llm_call_limit=3)
    with pytest.raises(ValueError):
        _audit_input(tool_call_limit=-1)
    await asyncio.sleep(0)


async def test_native_auditor_does_not_overrun_exhausted_loader_budget():
    """Run the native ADK runner directly; no Temporal service or live model."""

    from corsair.adapters.inference.adk import run_auditor
    from corsair.settings import ModelSettings
    from tests.unit.adk import ScriptedLlm, text_response, tool_response

    audit_input = _audit_input(llm_call_limit=1, tool_call_limit=0)
    model = ScriptedLlm(
        model="scripted",
        responses=[
            tool_response("load_skill", {"skill_name": "semantic-review"}),
            text_response(
                '{"decision":"ACCEPT","rule":"independent-evidence-review",'
                '"reason":"the packet is semantically coherent"}'
            ),
        ],
    )

    output = await run_auditor(audit_input, ModelSettings(), model)

    assert output.usage.llm_calls <= audit_input.llm_call_limit
    assert output.usage.tool_calls <= audit_input.tool_call_limit
    assert len(model.requests) <= audit_input.llm_call_limit


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


async def test_auditor_receives_only_remaining_root_budgets(
    temporal_server, temporal_artifact_store
):
    held = ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),) * 3)
    request = investigation_request("remaining-auditor-budget", budget=_three_round_budget())
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("remaining-auditor-budget"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.execution_status is ExecutionStatus.COMPLETED
    assert [
        (request.llm_call_limit, request.tool_call_limit) for request in activities.audit_inputs
    ] == [(2, 2), (2, 1), (1, 0)]


async def test_producer_and_auditor_share_the_request_output_cap(
    temporal_server, temporal_artifact_store
):
    """Both roles get the request's own per-request output cap, reasoning included:
    the auditor's cap is not a separate, smaller value than the producer's."""

    budget = _three_round_budget().model_copy(update={"max_output_tokens": 3072})
    request = investigation_request("shared-output-cap", budget=budget)
    async with temporal_server.worker(temporal_artifact_store) as (task_queue, activities):
        await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("shared-output-cap"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert activities.producer_inputs and activities.audit_inputs
    assert {item.budget.max_output_tokens for item in activities.producer_inputs} == {3072}
    assert {item.max_output_tokens for item in activities.audit_inputs} == {3072}


async def test_auditor_usage_cannot_exceed_its_admitted_remaining_budget(
    temporal_server, temporal_artifact_store
):
    from temporalio import activity

    class OverBudgetAuditorActivities(FakeActivities):
        @activity.defn(name="corsair.audit")
        async def audit(self, request: AuditInput) -> AuditOutput:
            self.call_counts["corsair.audit"] += 1
            self.audit_inputs.append(request)
            return AuditOutput(
                usage=Usage(
                    llm_calls=request.llm_call_limit + 1,
                    tool_calls=request.tool_call_limit + 1,
                )
            )

    activities = OverBudgetAuditorActivities(temporal_artifact_store)
    identity, queue = temporal_id("over-budget-audit"), temporal_id("over-budget-audit-queue")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request("over-budget-audit"),
            id=identity,
            task_queue=queue,
            result_type=InvestigationResult,
        )

    assert activities.call_counts["corsair.audit"] == 1
    assert [
        (request.llm_call_limit, request.tool_call_limit) for request in activities.audit_inputs
    ] == [(1, 0)]
    assert result.execution_status is ExecutionStatus.ERROR
    assert result.reason == "Auditor returned usage outside its admitted sub-budget"
    assert result.rounds[0].audit is None


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
    # A blocked prepare (source admission or the pre-model target_binding gate) is an
    # honest UNABLE_TO_RUN carrying the activity's reason, at zero model cost.
    assert result.verdict is Verdict.UNABLE_TO_RUN
    assert "test source admission was blocked" in result.reason
    assert result.rounds == []
    assert activities.call_counts["corsair.prepare"] == 1
    assert activities.call_counts["corsair.produce"] == 0
    assert activities.call_counts["corsair.evidence"] == 0
    assert activities.call_counts["corsair.audit"] == 0
    assert activities.call_counts["corsair.record"] == 1


class _ImageOnlySandbox:
    image_id = "sha256:" + "a" * 64


async def _run_with_real_prepare(
    temporal_server, tmp_path, module: str
) -> tuple[InvestigationResult, FakeActivities]:
    """Real source admission and pre-model gates; offline fakes for every later step."""
    from corsair.adapters.scm.local import LocalSourceSnapshots
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.settings import Settings
    from corsair.steps.activities import Activities

    (tmp_path / "admitted").mkdir()
    (tmp_path / "admitted" / "reader.py").write_text(module, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    request = investigation_request("line-less")
    case = request.case.model_copy(
        update={"finding": request.case.finding.model_copy(update={"line": None})}
    )
    request = request.model_copy(update={"case": case})
    fakes = FakeActivities(store)
    prepare = Activities(
        settings,
        store=store,
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_ImageOnlySandbox(),  # ty: ignore[invalid-argument-type]
    ).prepare
    queue = temporal_id("line-less-queue")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=[prepare, fakes.produce, fakes.evidence, fakes.audit, fakes.record],
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("line-less"),
            task_queue=queue,
            result_type=InvestigationResult,
        )
    return result, fakes


async def test_a_line_less_finding_with_a_resolvable_function_now_runs(temporal_server, tmp_path):
    """A scanner that named only the function: prepare binds the line from the recipe
    function in trusted code, and the same exact-line gates then decide the case."""
    from corsair.contracts import LineProvenance

    module = (
        "from pathlib import Path\n\n\n"
        "def read_payload(root, path):\n"
        "    return (Path(root) / path).read_text()\n"
    )
    result, fakes = await _run_with_real_prepare(temporal_server, tmp_path, module)

    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.verdict is Verdict.EXPLOIT_DEMONSTRATED
    [producer_input] = fakes.producer_inputs
    assert producer_input.prepared.finding.line == 5
    assert producer_input.prepared.line_provenance is LineProvenance.RECIPE_FUNCTION
    assert fakes.evidence_inputs[0].prepared.finding.line == 5
    [audit_input] = fakes.audit_inputs
    assert audit_input.finding.line == 5
    assert audit_input.line_provenance is LineProvenance.RECIPE_FUNCTION


async def test_a_line_less_finding_that_cannot_bind_is_still_unable_to_run(
    temporal_server, tmp_path
):
    module = "def read_payload(root, path): return path\n"
    result, fakes = await _run_with_real_prepare(temporal_server, tmp_path, module)

    assert result.execution_status is ExecutionStatus.BLOCKED
    assert result.verdict is Verdict.UNABLE_TO_RUN
    assert "target_binding line_missing" in result.reason
    assert fakes.call_counts["corsair.produce"] == 0
    assert fakes.call_counts["corsair.evidence"] == 0


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
    assert result.rounds[0].producer.submission_for_verification() is not None
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
                decision=ProducerDecision(
                    root=ProducerProposal(submission=submission.model_copy(update={"plan": plan}))
                ),
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


def _two_session_budget(rounds: int = 1) -> Budget:
    """Room for every round of both sessions: one producer and one audit call each."""
    return Budget(
        max_rounds=rounds,
        max_llm_calls=4 * rounds,
        episode_llm_calls=1,
        max_tool_calls=4 * rounds,
        max_output_tokens=256,
        max_elapsed_seconds=60,
        probe_timeout_seconds=1,
    )


_HELD = (RoleOutcome.HELD, RoleOutcome.HELD)
_DEMONSTRATED = (RoleOutcome.HELD, RoleOutcome.VIOLATION)


async def test_two_independent_clean_negative_sessions_are_exploit_not_demonstrated(
    temporal_server, temporal_artifact_store
):
    workflow_id = temporal_id("two-negatives")
    held = ActivityScenario(outcomes=(_HELD,) * 2)
    request = investigation_request("two-negatives", budget=_two_session_budget(rounds=2))
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, activities):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=workflow_id,
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED
    assert result.disposition is Disposition.INCONCLUSIVE
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert [(item.session, item.index) for item in result.rounds] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]
    assert [item.operation_id for item in activities.evidence_inputs] == [
        f"{workflow_id}.r1",
        f"{workflow_id}.r2",
        f"{workflow_id}.s2.r1",
        f"{workflow_id}.s2.r2",
    ]
    # The second session is blind: its first round carries nothing from the first.
    first_round, carried, fresh, _ = activities.producer_inputs
    assert first_round.previous is None and first_round.feedback is None
    assert carried.previous is not None and carried.feedback is not None
    assert fresh.round_index == 1
    assert fresh.previous is None and fresh.feedback is None
    persisted = InvestigationResult.model_validate(
        temporal_artifact_store.get_json(result.result_artifact)
    )
    assert persisted.verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED


async def test_second_session_demonstration_is_exploit_demonstrated(
    temporal_server, temporal_artifact_store
):
    workflow_id = temporal_id("second-demonstrates")
    scenario = ActivityScenario(outcomes=(_HELD,), later_session_outcomes=(_DEMONSTRATED,))
    request = investigation_request("second-demonstrates", fixed=True, budget=_two_session_budget())
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=workflow_id,
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.EXPLOIT_DEMONSTRATED
    assert result.disposition is Disposition.SUPPORTED
    assert result.fix_status is FixStatus.DEMONSTRATION_BLOCKED
    assert [item.operation_id for item in acts.evidence_inputs] == [
        f"{workflow_id}.r1",
        f"{workflow_id}.s2.r1",
        f"{workflow_id}.s2.fix1",
    ]


async def test_second_session_fault_is_error_not_a_second_clean_negative(
    temporal_server, temporal_artifact_store
):
    scenario = ActivityScenario(
        outcomes=(_HELD,), later_session_outcomes=((RoleOutcome.HELD, RoleOutcome.ERROR),)
    )
    request = investigation_request("second-faults", budget=_two_session_budget())
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("second-faults"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.ERROR
    assert acts.call_counts["corsair.evidence"] == 2


async def test_non_clean_first_session_does_not_start_a_second_session(
    temporal_server, temporal_artifact_store
):
    scenario = ActivityScenario(outcomes=((RoleOutcome.VIOLATION, RoleOutcome.VIOLATION),))
    request = investigation_request("no-second", budget=_two_session_budget())
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("no-second"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.INCONCLUSIVE
    assert [item.session for item in result.rounds] == [1]
    assert acts.call_counts["corsair.produce"] == 1


async def test_exhausted_root_budget_leaves_a_lone_clean_negative_inconclusive(
    temporal_server, temporal_artifact_store
):
    """Sessions share the root budget; no admissible second session means no LNE."""
    held = ActivityScenario(outcomes=(_HELD,) * 3)
    request = investigation_request("lone-negative", budget=_three_round_budget())
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("lone-negative"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.INCONCLUSIVE
    assert {item.session for item in result.rounds} == {1}
    assert all(".s" not in item.operation_id for item in acts.evidence_inputs)


async def test_component_demonstration_survives_a_crashed_fixed_revision_run(
    temporal_server, temporal_artifact_store
):
    request = investigation_request("component-fix-crash", fixed=True)
    finding = request.case.finding.model_copy(update={"claim_scope": Scope.APPLICATION})
    request = request.model_copy(
        update={"case": request.case.model_copy(update={"finding": finding})}
    )
    scenario = ActivityScenario(fail_fixed_evidence=True)
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("component-fix-crash"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.execution_status is ExecutionStatus.ERROR
    assert result.verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED
    assert [item.fixed for item in acts.evidence_inputs] == [False, True]


def _sessions_budget(sessions: int) -> Budget:
    """One round per session, with room for each session's producer and audit call."""
    return Budget(
        max_rounds=1,
        max_llm_calls=2 * sessions,
        episode_llm_calls=1,
        max_tool_calls=2 * sessions,
        max_output_tokens=256,
        max_elapsed_seconds=60,
        probe_timeout_seconds=1,
    )


async def _run_policy(server, store, label, scenario, sessions_budget):
    async with server.worker(store, scenario) as (task_queue, activities):
        result = await server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request(label, budget=_sessions_budget(sessions_budget)),
            id=temporal_id(label),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
    return result, activities


async def test_admitted_threshold_three_is_not_met_by_the_default_two_sessions(
    temporal_server, temporal_artifact_store
):
    scenario = ActivityScenario(outcomes=(_HELD,), negative_threshold=3, max_sessions=2)
    result, acts = await _run_policy(
        temporal_server, temporal_artifact_store, "threshold-three", scenario, 3
    )

    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.manifest is not None
    assert (result.manifest.negative_threshold, result.manifest.max_sessions) == (3, 2)
    # Two sessions can never reach three clean negatives, so the second is not spent.
    assert acts.call_counts["corsair.produce"] == 1


async def test_admitted_session_cap_one_schedules_exactly_one_session(
    temporal_server, temporal_artifact_store
):
    scenario = ActivityScenario(outcomes=(_HELD,), max_sessions=1)
    result, acts = await _run_policy(
        temporal_server, temporal_artifact_store, "cap-one", scenario, 3
    )

    assert result.verdict is Verdict.INCONCLUSIVE
    assert {item.session for item in result.rounds} == {1}
    assert acts.call_counts["corsair.produce"] == 1


async def test_admitted_threshold_and_cap_three_require_three_clean_sessions(
    temporal_server, temporal_artifact_store
):
    workflow_id = temporal_id("three-of-three")
    scenario = ActivityScenario(outcomes=(_HELD,), negative_threshold=3, max_sessions=3)
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, acts):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            investigation_request("three-of-three", budget=_sessions_budget(3)),
            id=workflow_id,
            task_queue=task_queue,
            result_type=InvestigationResult,
        )

    assert result.verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED
    assert [item.operation_id for item in acts.evidence_inputs] == [
        f"{workflow_id}.r1",
        f"{workflow_id}.s2.r1",
        f"{workflow_id}.s3.r1",
    ]


async def test_two_clean_sessions_under_threshold_three_stay_non_decisive(
    temporal_server, temporal_artifact_store
):
    # Two clean sessions under threshold three stay non-decisive when the root
    # budget admits no third session.
    scenario = ActivityScenario(outcomes=(_HELD,), negative_threshold=3, max_sessions=3)
    result, acts = await _run_policy(
        temporal_server, temporal_artifact_store, "three-starved", scenario, 2
    )

    assert result.verdict is Verdict.INCONCLUSIVE
    assert acts.call_counts["corsair.produce"] == 2


_STATUS_KEYS = {
    "phase",
    "session",
    "round",
    "max_sessions",
    "max_rounds",
    "gate",
    "started",
    "deadline",
    "timeline",
}


async def test_status_query_reports_bounds_deadline_and_phase_timeline(
    temporal_server, temporal_artifact_store
):
    request = investigation_request("statusquery")
    async with temporal_server.worker(temporal_artifact_store) as (task_queue, _activities):
        handle = await temporal_server.client.start_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("statusquery"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
        result = await handle.result()
        status = await handle.query(InvestigationWorkflow.status)

    assert result.disposition is Disposition.SUPPORTED
    assert set(status) == _STATUS_KEYS
    assert (status["phase"], status["session"], status["round"]) == ("complete", 1, 1)
    assert status["max_rounds"] == request.budget.max_rounds
    assert result.manifest is not None
    assert status["max_sessions"] == result.manifest.max_sessions
    assert status["gate"] is None
    started = datetime.fromisoformat(status["started"])
    deadline = datetime.fromisoformat(status["deadline"])
    assert (deadline - started).total_seconds() == request.budget.max_elapsed_seconds
    assert [entry["phase"] for entry in status["timeline"]] == [
        "prepare",
        "producer",
        "evidence",
        "audit",
        "record",
        "complete",
    ]
    assert [(entry["session"], entry["round"]) for entry in status["timeline"]][1:4] == [(1, 1)] * 3
    moments = [datetime.fromisoformat(entry["at"]) for entry in status["timeline"]]
    assert moments == sorted(moments) and moments[0] >= started


async def test_status_query_reports_the_last_feedback_gate_per_round(
    temporal_server, temporal_artifact_store
):
    held = ActivityScenario(outcomes=((RoleOutcome.HELD, RoleOutcome.HELD),) * 3)
    request = investigation_request("statusgate", budget=_three_round_budget())
    async with temporal_server.worker(temporal_artifact_store, held) as (task_queue, _activities):
        handle = await temporal_server.client.start_workflow(
            InvestigationWorkflow.run,
            request,
            id=temporal_id("statusgate"),
            task_queue=task_queue,
            result_type=InvestigationResult,
        )
        await handle.result()
        status = await handle.query(InvestigationWorkflow.status)

    assert status["gate"] in {"audit", "retry"}
    assert (status["round"], status["max_rounds"]) == (3, 3)
    producers = [entry["round"] for entry in status["timeline"] if entry["phase"] == "producer"]
    assert producers == [1, 2, 3]


async def test_batch_status_query_reports_running_and_error_counts(
    temporal_server, temporal_artifact_store
):
    request = BatchRequest(
        batch_id=temporal_id("batchstatus"),
        requests=[investigation_request("statusok"), investigation_request("statusbad")],
        repeats=1,
        concurrency=2,
    )
    scenario = ActivityScenario(fail_record_case_ids=frozenset({"statusbad"}))
    async with temporal_server.worker(temporal_artifact_store, scenario) as (task_queue, _):
        handle = await temporal_server.client.start_workflow(
            EvaluationWorkflow.run,
            request,
            id=temporal_id("batchstatus"),
            task_queue=task_queue,
            result_type=list[BatchItem],
        )
        await handle.result()
        status = await handle.query(EvaluationWorkflow.status)

    assert status == {"completed": 2, "total": 2, "running": 0, "errors": 1}
