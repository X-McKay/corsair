"""Separate v3 durable coordination; all I/O remains in ordinary activities."""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import Usage
    from corsair.contracts.execution import (
        AuditEpisodeInput,
        ExecutePlanInput,
        ExecutionEpisode,
        ExecutionRequest,
        ExecutionResult,
        ExecutionRound,
        ExecutionRoundInput,
        ExecutionStart,
        PreparedExecution,
        ProcessObservation,
    )
    from corsair.policies.execution import plan_fits_result


def add_usage(left: Usage, right: Usage) -> Usage:
    return Usage(
        llm_calls=left.llm_calls + right.llm_calls,
        tool_calls=left.tool_calls + right.tool_calls,
        seconds=left.seconds + right.seconds,
        input_tokens=None
        if left.input_tokens is None or right.input_tokens is None
        else left.input_tokens + right.input_tokens,
        output_tokens=None
        if left.output_tokens is None or right.output_tokens is None
        else left.output_tokens + right.output_tokens,
    )


@workflow.defn(name="corsair.investigation.v3")
class ExecutionWorkflow:
    def __init__(self):
        self.phase = "pending"
        self.revision = 0
        self.deadline: datetime | None = None

    @workflow.query
    def status(self) -> dict:
        return {
            "phase": self.phase,
            "round": self.revision,
            "schema_version": "corsair.execution-result/3",
        }

    def remaining(self) -> int:
        if self.deadline is None:
            raise RuntimeError("deadline unset")
        seconds = math.floor((self.deadline - workflow.now()).total_seconds())
        if seconds <= 0:
            raise TimeoutError
        return seconds

    async def call[Result](self, name: str, argument: Any, result_type: type[Result]) -> Result:
        self.phase = name.split(".")[-2]
        return await workflow.execute_activity(
            name,
            argument,
            result_type=result_type,
            start_to_close_timeout=timedelta(seconds=self.remaining()),
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=1),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    @workflow.run
    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        identity = workflow.info().workflow_id
        self.deadline = workflow.now() + timedelta(seconds=request.budget.max_elapsed_seconds)
        result = ExecutionResult(run_id=identity, case_id=request.case_id)
        try:
            prepared = await self.call(
                "corsair.execution.prepare.v3",
                ExecutionStart(run_id=identity, request=request),
                PreparedExecution,
            )
            result = result.model_copy(
                update={
                    "prepared_artifact": prepared.artifact,
                    "identities": {
                        "request": prepared.request_digest,
                        "source": prepared.source.sha256,
                        "config": prepared.config_digest,
                        "resources": prepared.resources_digest,
                    },
                }
            )
            for revision in range(1, request.budget.max_rounds + 1):
                self.revision = revision
                llms = request.budget.max_llm_calls - result.usage.llm_calls
                tools = request.budget.max_tool_calls - result.usage.tool_calls
                if llms < 2 or tools < 6:
                    result = result.model_copy(update={"error": "BUDGET_EXHAUSTED"})
                    break
                item = ExecutionRoundInput(
                    prepared=prepared,
                    revision=revision,
                    previous=result.rounds[-1] if result.rounds else None,
                    llm_limit=min(request.budget.episode_llm_calls, llms - 1),
                    tool_limit=tools - 3,
                    seconds=self.remaining(),
                )
                output = await self.call("corsair.execution.produce.v3", item, ExecutionEpisode)
                usage = add_usage(result.usage, output.usage)
                current = ExecutionRound(
                    plan=output.plan, error=output.error, plan_artifact=output.plan_artifact
                )
                if output.plan is not None and not plan_fits_result(result, output.plan):
                    current = ExecutionRound(
                        plan_artifact=output.plan_artifact, error="RESULT_SIZE_LIMIT"
                    )
                    result = result.model_copy(
                        update={
                            "usage": usage,
                            "outcome": "INCOMPLETE",
                            "error": "RESULT_SIZE_LIMIT",
                            "rounds": [*result.rounds, current],
                        }
                    )
                    break
                result = result.model_copy(
                    update={"usage": usage, "rounds": [*result.rounds, current]}
                )
                if output.error is not None or output.plan is None:
                    continue
                plan = output.plan
                audit_input = item.model_copy(
                    update={
                        "llm_limit": min(
                            request.budget.episode_llm_calls,
                            request.budget.max_llm_calls - usage.llm_calls,
                        ),
                        "tool_limit": request.budget.max_tool_calls - usage.tool_calls,
                        "seconds": self.remaining(),
                    }
                )
                audited = await self.call(
                    "corsair.execution.audit.v3",
                    AuditEpisodeInput(round=audit_input, plan=plan),
                    ExecutionEpisode,
                )
                current = current.model_copy(
                    update={"audit": audited.audit, "error": audited.error}
                )
                result = result.model_copy(
                    update={
                        "usage": add_usage(usage, audited.usage),
                        "rounds": [*result.rounds[:-1], current],
                    }
                )
                if (
                    audited.error is not None
                    or audited.audit is None
                    or audited.audit.decision != "accepted"
                ):
                    continue
                execution_input = ExecutePlanInput(
                    prepared=prepared,
                    plan=plan,
                    audit=audited.audit,
                    timeout_seconds=self.remaining(),
                )
                observed = await self.call(
                    "corsair.execution.execute.v3", execution_input, ProcessObservation
                )
                current = current.model_copy(update={"observation": observed})
                result = result.model_copy(
                    update={"rounds": [*result.rounds[:-1], current], "outcome": observed.outcome}
                )
                if observed.error is not None:
                    result = result.model_copy(update={"error": observed.error})
                    break
                if prepared.fixed_source is not None:
                    fixed = await self.call(
                        "corsair.execution.execute.v3",
                        execution_input.model_copy(
                            update={"fixed": True, "timeout_seconds": self.remaining()}
                        ),
                        ProcessObservation,
                    )
                    current = current.model_copy(update={"fixed_observation": fixed})
                    result = result.model_copy(update={"rounds": [*result.rounds[:-1], current]})
                    if fixed.error is not None:
                        result = result.model_copy(
                            update={"outcome": "ERROR", "error": fixed.error}
                        )
                        break
                if observed.outcome == "SUCCEEDED":
                    break
        except ActivityError:
            result = result.model_copy(update={"outcome": "ERROR", "error": "ACTIVITY_FAILED"})
        except TimeoutError:
            result = result.model_copy(
                update={"outcome": "INCOMPLETE", "error": "DEADLINE_EXHAUSTED"}
            )
        except asyncio.CancelledError:
            result = result.model_copy(update={"outcome": "INCOMPLETE", "error": "CANCELLED"})
        self.phase = "recording"
        recorded = await asyncio.shield(
            workflow.execute_activity(
                "corsair.execution.record.v3",
                result,
                result_type=ExecutionResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        )
        self.phase = "completed"
        return recorded
