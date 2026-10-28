"""Intake-gated native Temporal children; all I/O belongs to ordinary activities."""

import asyncio
import math
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import digest
    from corsair.contracts.execution import ExecutionResult
    from corsair.contracts.intake import IntakeResult, IntakeStart
    from corsair.contracts.pipeline import IssueInvestigationRequest, IssueInvestigationResult
    from corsair.policies.pipeline import (
        charged_intake_usage,
        combine_usage,
        execution_from_intake,
        intake_stop_reason,
        remaining_budget,
    )


@workflow.defn(name="corsair.issue-investigation.v4")
class IssueInvestigationWorkflow:
    def __init__(self):
        self.phase = "pending"
        self.execution_run_id: str | None = None

    @workflow.query
    def status(self) -> dict:
        return {
            "phase": self.phase,
            "execution_run_id": self.execution_run_id,
            "schema_version": "corsair.issue-investigation-result/4",
        }

    @workflow.run
    async def run(self, request: IssueInvestigationRequest) -> IssueInvestigationResult:
        identity = workflow.info().workflow_id
        deadline = workflow.now() + timedelta(seconds=request.intake.budget.max_elapsed_seconds)
        prefix = f"issue-{digest(identity)[:24]}"
        intake_id = f"{prefix}.intake"
        result = IssueInvestigationResult(
            run_id=identity, case_id=request.case_id, request_digest=digest(request)
        )
        try:
            self.phase = "intake"
            intake = await asyncio.wait_for(
                workflow.execute_child_workflow(
                    "corsair.intake",
                    IntakeStart(run_id=intake_id, request=request.intake),
                    id=intake_id,
                    result_type=IntakeResult,
                    execution_timeout=timedelta(
                        seconds=request.intake.budget.max_elapsed_seconds + 60
                    ),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
                    parent_close_policy=workflow.ParentClosePolicy.REQUEST_CANCEL,
                ),
                timeout=max(0.0, (deadline - workflow.now()).total_seconds()),
            )
            result = result.model_copy(
                update={
                    "intake": intake,
                    "usage": charged_intake_usage(intake),
                    "usage_complete": intake.decision.status != "error",
                }
            )
            if workflow.cancellation_reason() is not None:
                raise asyncio.CancelledError
            if workflow.now() >= deadline:
                raise TimeoutError
            reason = intake_stop_reason(intake)
            execution_request = None
            if reason is not None:
                result = result.model_copy(update={"status": "stopped", "stop_reason": reason})
            else:
                self.phase = "handoff"
                try:
                    budget = remaining_budget(
                        request.intake.budget,
                        intake,
                        math.floor((deadline - workflow.now()).total_seconds()),
                    )
                except ValueError:
                    result = result.model_copy(
                        update={"status": "stopped", "stop_reason": "BUDGET_EXHAUSTED"}
                    )
                else:
                    try:
                        execution_request = execution_from_intake(
                            request, intake, intake_id, budget
                        )
                    except ValueError:
                        result = result.model_copy(
                            update={"status": "stopped", "stop_reason": "HANDOFF_INVALID"}
                        )
            if execution_request is not None:
                self.phase = "investigation"
                self.execution_run_id = f"{prefix}.execution"
                result = result.model_copy(
                    update={"execution_run_id": self.execution_run_id, "usage_complete": False}
                )
                executed = await asyncio.wait_for(
                    workflow.execute_child_workflow(
                        "corsair.investigation.v3",
                        execution_request,
                        id=self.execution_run_id,
                        result_type=ExecutionResult,
                        execution_timeout=timedelta(
                            seconds=execution_request.budget.max_elapsed_seconds + 60
                        ),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                        cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
                        parent_close_policy=workflow.ParentClosePolicy.REQUEST_CANCEL,
                    ),
                    timeout=max(0.0, (deadline - workflow.now()).total_seconds()),
                )
                if (
                    executed.run_id != self.execution_run_id
                    or executed.case_id != request.case_id
                    or executed.result_artifact is None
                ):
                    result = result.model_copy(
                        update={"status": "incomplete", "stop_reason": "EXECUTION_UNCERTAIN"}
                    )
                else:
                    result = result.model_copy(
                        update={
                            "status": "investigation_finished",
                            "stop_reason": None,
                            "execution_result": executed.result_artifact,
                            "execution_outcome": executed.outcome,
                            "execution_error": executed.error,
                            "usage": combine_usage(result.usage, executed.usage),
                            "usage_complete": executed.error
                            not in {"ACTIVITY_FAILED", "CANCELLED", "DEADLINE_EXHAUSTED"},
                        }
                    )
                if workflow.cancellation_reason() is not None:
                    raise asyncio.CancelledError
                if workflow.now() >= deadline:
                    raise TimeoutError
        except asyncio.CancelledError:
            result = result.model_copy(
                update={"status": "incomplete", "stop_reason": "CANCELLED", "usage_complete": False}
            )
        except TimeoutError:
            result = result.model_copy(
                update={
                    "status": "incomplete",
                    "stop_reason": "DEADLINE_EXHAUSTED",
                    "usage_complete": False,
                }
            )
        except ChildWorkflowError:
            result = result.model_copy(
                update={
                    "status": "incomplete",
                    "stop_reason": (
                        "DEADLINE_EXHAUSTED"
                        if workflow.now() >= deadline
                        else "EXECUTION_UNCERTAIN"
                        if self.execution_run_id is not None
                        else "INTAKE_UNCERTAIN"
                    ),
                    "usage_complete": False,
                }
            )
        self.phase = "recording"
        recorded = await asyncio.shield(
            workflow.execute_activity(
                "corsair.issue-investigation.record.v4",
                result,
                result_type=IssueInvestigationResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        )
        self.phase = "completed"
        return recorded
