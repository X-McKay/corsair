"""Plan 1: Temporal owns rounds; normal activities own complete ADK episodes and I/O."""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import (
        AuditInput,
        AuditOutput,
        Disposition,
        EvidenceInput,
        ExecutionStatus,
        Feedback,
        FixStatus,
        InvestigationRequest,
        InvestigationResult,
        Observation,
        PreparedCase,
        ProducerInput,
        ProducerOutput,
        RoundResult,
    )
    from corsair.policy.verdicts import decide, fix_status


class BudgetExhausted(Exception):
    """No action time remains before the investigation admission deadline."""


@workflow.defn(name="corsair.investigation")
class InvestigationWorkflow:
    def __init__(self) -> None:
        self.phase = "pending"
        self.round_index = 0
        self.deadline: datetime | None = None

    @workflow.query
    def status(self) -> dict:
        return {"phase": self.phase, "round": self.round_index}

    async def _execute_bounded_activity[Result](
        self, name: str, argument: Any, result_type: type[Result], seconds: int
    ) -> Result:
        if self.deadline is None:
            raise RuntimeError("Investigation deadline has not been initialized")
        remaining = (self.deadline - workflow.now()).total_seconds()
        if remaining <= 0:
            raise BudgetExhausted
        seconds = min(seconds, max(1, math.ceil(remaining)))
        return await workflow.execute_activity(
            name,
            argument,
            result_type=result_type,
            start_to_close_timeout=timedelta(seconds=seconds),
            schedule_to_close_timeout=timedelta(seconds=seconds),
            heartbeat_timeout=timedelta(seconds=min(15, seconds)),
            retry_policy=RetryPolicy(maximum_attempts=1),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    async def _record_result(self, result: InvestigationResult) -> InvestigationResult:
        """Persist the final receipt within its separate retry/finalization allowance."""
        self.phase = "record"
        recorded = await asyncio.shield(
            workflow.execute_activity(
                "corsair.record",
                result,
                result_type=InvestigationResult,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=(
                    timedelta(seconds=90) if workflow.patched("bounded-finalization-v1") else None
                ),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        )
        self.phase = "complete"
        return recorded

    @workflow.run
    async def run(self, request: InvestigationRequest) -> InvestigationResult:
        run_id = workflow.info().workflow_id
        budget = request.budget
        started = workflow.now()
        self.deadline = started + timedelta(seconds=budget.max_elapsed_seconds)
        result = InvestigationResult(
            run_id=run_id,
            case_id=request.case.case_id,
            disposition=Disposition.INCONCLUSIVE,
            execution_status=ExecutionStatus.COMPLETED,
            reason="No admissible observation was collected.",
            fix_status=(
                FixStatus.UNVERIFIED if request.case.fixed_source else FixStatus.NOT_REQUESTED
            ),
        )
        rounds: list[RoundResult] = []
        try:
            self.phase = "prepare"
            prepared = await self._execute_bounded_activity(
                "corsair.prepare", request, PreparedCase, 120
            )
            result = result.model_copy(update={"manifest": prepared.manifest})
            calls_left, tools_left = budget.max_llm_calls, budget.max_tool_calls
            previous, feedback = None, None
            for index in range(1, budget.max_rounds + 1):
                self.round_index = index
                elapsed = (workflow.now() - started).total_seconds()
                if calls_left < 2 or tools_left < 1 or elapsed >= budget.max_elapsed_seconds:
                    result = result.model_copy(update={"reason": "Investigation budget exhausted."})
                    break
                self.phase = "producer"
                call_limit = min(budget.episode_llm_calls, calls_left - 1)
                producer = await self._execute_bounded_activity(
                    "corsair.produce",
                    ProducerInput(
                        run_id=run_id,
                        prepared=prepared,
                        budget=budget,
                        round_index=index,
                        previous=previous,
                        feedback=feedback,
                        llm_call_limit=call_limit,
                        tool_call_limit=tools_left,
                    ),
                    ProducerOutput,
                    min(300, budget.max_elapsed_seconds - int(elapsed)),
                )
                calls_left -= producer.usage.llm_calls
                tools_left -= producer.usage.tool_calls
                if producer.usage.llm_calls > call_limit or tools_left < 0:
                    raise ValueError("Producer returned usage outside its admitted sub-budget")
                round_result = RoundResult(index=index, producer=producer)
                rounds.append(round_result)
                if producer.submission is None:
                    feedback = producer.feedback or Feedback(
                        gate="producer", reason="No submission"
                    )
                    result = result.model_copy(update={"reason": feedback.reason})
                    if feedback.operational:
                        result = result.model_copy(
                            update={"execution_status": ExecutionStatus.ERROR}
                        )
                        break
                    continue
                previous = producer.submission
                self.phase = "evidence"
                observation = await self._execute_bounded_activity(
                    "corsair.evidence",
                    EvidenceInput(
                        run_id=run_id,
                        operation_id=f"{run_id}.r{index}",
                        prepared=prepared,
                        submission=previous,
                        budget=budget,
                    ),
                    Observation,
                    2 * budget.probe_timeout_seconds + 45,
                )
                round_result = round_result.model_copy(update={"observation": observation})
                rounds[-1] = round_result
                if observation.feedback is not None:
                    feedback = observation.feedback
                    result = result.model_copy(update={"reason": feedback.reason})
                    if feedback.operational:
                        result = result.model_copy(
                            update={"execution_status": ExecutionStatus.ERROR}
                        )
                        break
                    continue
                if calls_left < 1:
                    result = result.model_copy(update={"reason": "No budget remains for review."})
                    break
                self.phase = "audit"
                audit = await self._execute_bounded_activity(
                    "corsair.audit",
                    AuditInput(
                        finding=prepared.finding,
                        recipe=prepared.recipe,
                        source_excerpt=prepared.source_excerpt,
                        submission=previous,
                        max_output_tokens=budget.max_output_tokens,
                    ),
                    AuditOutput,
                    180,
                )
                calls_left -= audit.usage.llm_calls
                if audit.usage.llm_calls > 1:
                    raise ValueError("Auditor returned usage outside its one-call budget")
                round_result = round_result.model_copy(update={"audit": audit})
                rounds[-1] = round_result
                label, status, reason = decide(prepared, observation, audit)
                result = result.model_copy(
                    update={"disposition": label, "execution_status": status, "reason": reason}
                )
                if label in {Disposition.SUPPORTED, Disposition.CONDITIONAL}:
                    if prepared.fixed_source is not None:
                        self.phase = "fix"
                        fixed = await self._execute_bounded_activity(
                            "corsair.evidence",
                            EvidenceInput(
                                run_id=run_id,
                                operation_id=f"{run_id}.fix{index}",
                                prepared=prepared,
                                submission=previous,
                                budget=budget,
                                fixed=True,
                            ),
                            Observation,
                            2 * budget.probe_timeout_seconds + 45,
                        )
                        result = result.model_copy(
                            update={"fix_status": fix_status(fixed), "fix_observation": fixed}
                        )
                    break
                if status != ExecutionStatus.COMPLETED:
                    break
                feedback = Feedback(gate="review_or_reproduction", reason=reason)
        except ActivityError as exc:
            cause_type = getattr(exc.cause, "type", "")
            # Operational failures must not erase a previously admitted source observation.
            if is_cancelled_exception(exc):
                status = ExecutionStatus.CANCELLED
            elif self.phase == "prepare" and cause_type in {"PREPARE_BLOCKED", "SOURCE_DENIED"}:
                status = ExecutionStatus.BLOCKED
            else:
                status = ExecutionStatus.ERROR
            result = result.model_copy(
                update={
                    "execution_status": status,
                    "reason": f"{self.phase}: {exc.cause}",
                    "usage_complete": self.phase not in {"producer", "audit"},
                }
            )
        except BudgetExhausted:
            result = result.model_copy(
                update={"reason": "Investigation elapsed-time budget exhausted."}
            )
        except ValueError as exc:
            result = result.model_copy(
                update={"execution_status": ExecutionStatus.ERROR, "reason": str(exc)}
            )
        except asyncio.CancelledError:
            result = result.model_copy(
                update={
                    "execution_status": ExecutionStatus.CANCELLED,
                    "reason": "Run cancelled.",
                    "usage_complete": self.phase not in {"producer", "audit"},
                }
            )
            raise
        finally:
            result = result.model_copy(update={"rounds": rounds})
            result = await self._record_result(result)
        return result
