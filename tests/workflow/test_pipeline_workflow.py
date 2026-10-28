"""Actual Temporal child scheduling/gates with explicit test-only child substitutes."""

import asyncio
from contextlib import suppress
from datetime import timedelta

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer, Worker

from corsair.contracts import Usage, digest
from corsair.contracts.execution import ExecutionRequest, ExecutionResult
from corsair.contracts.intake import IntakeDecision, IntakeResult, IntakeStart
from tests.unit.test_pipeline import supported
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


@workflow.defn(name="corsair.intake", sandboxed=False)
class TestIntakeChild:
    @workflow.run
    async def run(self, start: IntakeStart) -> IntakeResult:
        _, result = supported()
        assert result.proposal is not None
        from corsair.contracts.intake import JsonIssueInput

        assert isinstance(start.request.input, JsonIssueInput)
        assert isinstance(start.request.input.payload, dict)
        label = start.request.input.payload["test_decision"]
        assert isinstance(label, str)
        if label == "suppress_intake":
            with suppress(asyncio.CancelledError):
                await workflow.wait_condition(lambda: False)
        if label == "wait_intake":
            await workflow.wait_condition(lambda: False)
        if label == "fail_intake":
            from temporalio.exceptions import ApplicationError

            raise ApplicationError("synthetic intake failure", non_retryable=True)
        decisions = {
            "supported": result.decision,
            "suppress_intake": IntakeDecision(status="error", error_code="MODEL_FAILED"),
            "suppress_execution": result.decision,
            "wait_execution": result.decision,
            "fail_execution": result.decision,
            "budget": result.decision,
            "unsupported": IntakeDecision(
                status="completed", classification="in_scope_not_supported"
            ),
            "outside": IntakeDecision(status="completed", classification="out_of_scope"),
            "input": IntakeDecision(status="needs_input"),
            "error": IntakeDecision(status="error", error_code="MODEL_FAILED"),
        }
        return result.model_copy(
            update={
                "run_id": start.run_id,
                "decision": decisions[label],
                "identities": {"request": digest(start.request)},
                "proposal": result.proposal.model_copy(
                    update={"issue": result.proposal.issue.model_copy(update={"title": label})}
                ),
                "usage": Usage(llm_calls=16) if label == "budget" else result.usage,
            }
        )


@workflow.defn(name="corsair.investigation.v3", sandboxed=False)
class TestExecutionChild:
    @workflow.run
    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        if request.issue.title == "suppress_execution":
            with suppress(asyncio.CancelledError):
                await workflow.wait_condition(lambda: False)
        if request.issue.title == "wait_execution":
            await workflow.wait_condition(lambda: False)
        if request.issue.title == "fail_execution":
            from temporalio.exceptions import ApplicationError

            raise ApplicationError("synthetic execution failure", non_retryable=True)
        assert request.image.image_id == "sha256:" + "1" * 64
        assert request.source.expected_digest == "2" * 64
        assert request.budget.max_llm_calls == 14 and request.budget.max_tool_calls == 21
        _, intake = supported()
        return ExecutionResult(
            run_id=workflow.info().workflow_id,
            case_id=request.case_id,
            outcome="SUCCEEDED",
            result_artifact=intake.result_artifact,
            usage=Usage(llm_calls=2, tool_calls=4),
        )


@activity.defn(name="corsair.issue-investigation.record.v4")
async def record_pipeline(result):
    return result


@pytest.mark.parametrize(
    "label,reason",
    [
        ("outside", "OUT_OF_SCOPE"),
        ("unsupported", "UNSUPPORTED"),
        ("input", "NEEDS_INPUT"),
        ("error", "INTAKE_ERROR"),
        ("supported", None),
        ("budget", "BUDGET_EXHAUSTED"),
    ],
)
async def test_parent_gates_children_and_preserves_shared_budget(temporal_server, label, reason):
    from corsair.contracts.intake import JsonIssueInput
    from corsair.workflows.pipeline import IssueInvestigationWorkflow

    request, _ = supported()
    request = request.model_copy(
        update={
            "intake": request.intake.model_copy(
                update={"input": JsonIssueInput(payload={"test_decision": label})}
            )
        }
    )
    queue = temporal_id("pipeline")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[IssueInvestigationWorkflow, TestIntakeChild, TestExecutionChild],
        activities=[record_pipeline],
    ):
        handle = await temporal_server.client.start_workflow(
            IssueInvestigationWorkflow.run,
            request,
            id=temporal_id("pipeline-run"),
            task_queue=queue,
            execution_timeout=timedelta(seconds=60),
        )
        result = await handle.result()
        history = await handle.fetch_history()
    initiated = [
        event.start_child_workflow_execution_initiated_event_attributes.workflow_type.name
        for event in history.events
        if event.HasField("start_child_workflow_execution_initiated_event_attributes")
    ]
    assert initiated[0] == "corsair.intake"
    assert result.stop_reason == reason
    if reason is not None:
        assert result.status == "stopped" and result.execution_run_id is None
        assert initiated == ["corsair.intake"]
    else:
        assert initiated == ["corsair.intake", "corsair.investigation.v3"]
        assert result.status == "investigation_finished" and result.execution_outcome == "SUCCEEDED"
        assert result.usage.llm_calls == 4 and result.usage.tool_calls == 7
        assert result.security_assessment == "UNRESOLVED"
    await Replayer(
        workflows=[IssueInvestigationWorkflow], data_converter=pydantic_data_converter
    ).replay_workflow(history)


@pytest.mark.parametrize("stage", ["intake", "execution"])
@pytest.mark.parametrize("action", ["wait", "suppress", "fail"])
async def test_parent_preserves_child_failure_and_cancellation(temporal_server, stage, action):
    import asyncio

    from corsair.contracts.intake import JsonIssueInput
    from corsair.workflows.pipeline import IssueInvestigationWorkflow

    request, _ = supported()
    request = request.model_copy(
        update={
            "intake": request.intake.model_copy(
                update={"input": JsonIssueInput(payload={"test_decision": f"{action}_{stage}"})}
            )
        }
    )
    queue = temporal_id("pipeline-failure")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[IssueInvestigationWorkflow, TestIntakeChild, TestExecutionChild],
        activities=[record_pipeline],
    ):
        handle = await temporal_server.client.start_workflow(
            IssueInvestigationWorkflow.run,
            request,
            id=temporal_id("pipeline-run"),
            task_queue=queue,
            execution_timeout=timedelta(seconds=30),
        )
        if action in {"wait", "suppress"}:
            for _ in range(200):
                status = await handle.query("status")
                if status["phase"] == ("intake" if stage == "intake" else "investigation"):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("parent did not reach expected child phase")
            await handle.cancel()
        result = await handle.result()
        assert result.status == "incomplete" and not result.usage_complete
        assert result.stop_reason == (
            "CANCELLED" if action in {"wait", "suppress"} else f"{stage.upper()}_UNCERTAIN"
        )
        history = await handle.fetch_history()
        await Replayer(
            workflows=[IssueInvestigationWorkflow], data_converter=pydantic_data_converter
        ).replay_workflow(history)


@pytest.mark.parametrize("label", ["wait_intake", "suppress_intake", "suppress_execution"])
async def test_parent_deadline_cancels_waiting_child(temporal_server, label):
    from corsair.contracts import Budget
    from corsair.contracts.intake import JsonIssueInput
    from corsair.workflows.pipeline import IssueInvestigationWorkflow

    request, _ = supported()
    request = request.model_copy(
        update={
            "intake": request.intake.model_copy(
                update={
                    "input": JsonIssueInput(payload={"test_decision": label}),
                    "budget": Budget(max_elapsed_seconds=31),
                }
            )
        }
    )
    queue = temporal_id("pipeline-deadline")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[IssueInvestigationWorkflow, TestIntakeChild, TestExecutionChild],
        activities=[record_pipeline],
    ):
        handle = await temporal_server.client.start_workflow(
            IssueInvestigationWorkflow.run,
            request,
            id=temporal_id("pipeline-deadline"),
            task_queue=queue,
            execution_timeout=timedelta(seconds=60),
        )
        result = await handle.result()
        assert result.status == "incomplete" and result.stop_reason == "DEADLINE_EXHAUSTED"
        assert not result.usage_complete
        assert (result.execution_run_id is None) == (label != "suppress_execution")
        history = await handle.fetch_history()
        if label == "wait_intake":
            assert any(
                e.HasField("child_workflow_execution_canceled_event_attributes")
                for e in history.events
            )
        else:
            assert any(
                e.HasField("child_workflow_execution_completed_event_attributes")
                for e in history.events
            )
        await Replayer(
            workflows=[IssueInvestigationWorkflow], data_converter=pydantic_data_converter
        ).replay_workflow(history)
