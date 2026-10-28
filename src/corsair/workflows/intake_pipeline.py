"""Intake-gated native Temporal children; all I/O belongs to ordinary activities."""

import asyncio
import math
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import InvestigationResult, digest
    from corsair.contracts.intake_agent import IntakeResult, IntakeStart
    from corsair.contracts.intake_pipeline import (
        IntakeInvestigationRequest,
        IntakeInvestigationResult,
    )
    from corsair.policies.intake_handoff import (
        bind_investigation,
        charged_usage,
        combine_usage,
        investigation_usage,
        remaining_budget,
        stop_reason,
    )


@workflow.defn(name="corsair.intake-investigation.v1")
class IntakeInvestigationWorkflow:
    def __init__(self):
        self.phase = "pending"
        self.investigation_run_id: str | None = None

    @workflow.query
    def status(self) -> dict:
        return {
            "phase": self.phase,
            "investigation_run_id": self.investigation_run_id,
            "schema_version": "corsair.intake-investigation-result/1",
        }

    @workflow.run
    async def run(self, request: IntakeInvestigationRequest) -> IntakeInvestigationResult:
        identity = workflow.info().workflow_id
        deadline = workflow.now() + timedelta(seconds=request.intake.budget.max_elapsed_seconds)
        prefix = f"issue-{digest(identity)[:24]}"
        intake_id = f"{prefix}.intake"
        result = IntakeInvestigationResult(run_id=identity, case_id=request.case_id)
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
                    "usage": charged_usage(intake),
                    "usage_complete": intake.decision.status != "error",
                }
            )
            if workflow.cancellation_reason() is not None:
                raise asyncio.CancelledError
            if workflow.now() >= deadline:
                raise TimeoutError
            reason = stop_reason(intake)
            if reason is None and request.binding is None:
                reason = "TARGET_BINDING_REQUIRED"
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
                        execution_request = bind_investigation(
                            request, intake, intake_id, budget.max_elapsed_seconds
                        )
                    except ValueError:
                        result = result.model_copy(
                            update={"status": "stopped", "stop_reason": "HANDOFF_INVALID"}
                        )
            if execution_request is not None:
                self.phase = "investigation"
                self.investigation_run_id = f"{prefix}.execution"
                result = result.model_copy(
                    update={
                        "investigation_run_id": self.investigation_run_id,
                        "usage_complete": False,
                    }
                )
                executed = await asyncio.wait_for(
                    workflow.execute_child_workflow(
                        "corsair.investigation",
                        execution_request,
                        id=self.investigation_run_id,
                        result_type=InvestigationResult,
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
                    executed.run_id != self.investigation_run_id
                    or executed.case_id != request.case_id
                    or executed.result_artifact is None
                ):
                    result = result.model_copy(
                        update={"status": "incomplete", "stop_reason": "INVESTIGATION_UNCERTAIN"}
                    )
                else:
                    result = result.model_copy(
                        update={
                            "status": "investigation_finished",
                            "stop_reason": None,
                            "investigation_result": executed.result_artifact,
                            "investigation_disposition": executed.disposition,
                            "investigation_execution_status": executed.execution_status,
                            "usage": combine_usage(result.usage, investigation_usage(executed)),
                            "usage_complete": executed.usage_complete,
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
                        else "INVESTIGATION_UNCERTAIN"
                        if self.investigation_run_id is not None
                        else "INTAKE_UNCERTAIN"
                    ),
                    "usage_complete": False,
                }
            )
        self.phase = "recording"
        recorded = await asyncio.shield(
            workflow.execute_activity(
                "corsair.intake-investigation.record.v1",
                result,
                result_type=IntakeInvestigationResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        )
        self.phase = "completed"
        return recorded
