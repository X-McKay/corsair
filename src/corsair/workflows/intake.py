"""Deterministic bounded intake coordination; no execution adapter imports."""

import asyncio
import math
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts.intake import (
        ErrorCode,
        IntakeDecision,
        IntakeResult,
        IntakeStart,
        PreparedIntake,
    )


@workflow.defn(name="corsair.intake")
class IntakeWorkflow:
    @workflow.run
    async def run(self, start: IntakeStart) -> IntakeResult:
        deadline = workflow.now() + timedelta(seconds=start.request.budget.max_elapsed_seconds)
        result = IntakeResult(
            run_id=start.run_id,
            decision=IntakeDecision(status="error", error_code="INSPECTION_FAILED"),
        )
        try:
            prepared = await workflow.execute_activity(
                "corsair.intake.prepare",
                start,
                result_type=PreparedIntake,
                start_to_close_timeout=timedelta(
                    seconds=min(90, start.request.budget.max_elapsed_seconds)
                ),
                heartbeat_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(maximum_attempts=1),
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
            remaining = math.floor((deadline - workflow.now()).total_seconds())
            if remaining <= 0:
                raise TimeoutError
            prepared = prepared.model_copy(update={"episode_seconds": remaining})
            result = await workflow.execute_activity(
                "corsair.intake.analyze",
                prepared,
                result_type=IntakeResult,
                start_to_close_timeout=timedelta(seconds=remaining),
                heartbeat_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(maximum_attempts=1),
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
        except ActivityError as error:
            cause = error.cause
            error_type = cause.type if isinstance(cause, ApplicationError) else "INSPECTION_FAILED"
            if error_type == "OUTSIDE_SCOPE_POLICY":
                decision = IntakeDecision(
                    status="completed",
                    classification="out_of_scope",
                    reason_codes=["OUTSIDE_SCOPE_POLICY"],
                )
            else:
                allowed: set[ErrorCode] = {
                    "ISSUE_FETCH_FAILED",
                    "SOURCE_DENIED",
                    "IMAGE_CHECK_FAILED",
                }
                code = next((code for code in allowed if code == error_type), "INSPECTION_FAILED")
                decision = IntakeDecision(status="error", error_code=code)
            result = result.model_copy(update={"decision": decision})
        except (asyncio.CancelledError, TimeoutError):
            pass
        return await asyncio.shield(
            workflow.execute_activity(
                "corsair.intake.record",
                result,
                result_type=IntakeResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        )
