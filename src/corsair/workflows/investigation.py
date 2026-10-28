"""Plan 1: Temporal owns rounds; normal activities own complete ADK episodes and I/O."""

import asyncio
import json
import math
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import (
        AssessmentOutcome,
        AuditInput,
        AuditOutput,
        Disposition,
        EvidenceInput,
        ExecutionStatus,
        Feedback,
        FixStatus,
        InvestigationRequest,
        InvestigationResult,
        NoGroundedCandidate,
        Observation,
        PreparedCase,
        ProducerInput,
        ProducerOutput,
        RoundResult,
        Submission,
        digest,
        format_terminal_result,
    )
    from corsair.policies.verdicts import assessment_outcome, decide, fix_status


class BudgetExhausted(Exception):
    """No action time remains before the investigation admission deadline."""


def _mechanical_follow_up(gate: str) -> Feedback:
    """Return finite producer feedback without exposing a prior security outcome."""
    new_candidate = (
        "Generate a new source-grounded payload candidate within the remaining admitted budget."
    )
    reasons = {
        "producer-grounding": new_candidate,
        "candidate-distinctness": (
            "Generate a candidate with an adversarial payload different from every prior "
            "admitted candidate."
        ),
        "evidence-retry": new_candidate,
        "audit-retry": new_candidate,
        "assessment-continue": (
            "Generate a meaningfully different source-grounded payload candidate within the "
            "remaining admitted budget."
        ),
    }
    return Feedback(gate=gate, reason=reasons[gate])


def _adversarial_payload_digest(submission: Submission) -> str:
    """Return the canonical identity for an adversarial payload attempt only."""
    payload = json.dumps(
        submission.exploit_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return digest(payload)


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
        try:
            result = format_terminal_result(result)
        except ValueError:
            # An unbounded validation exception must not become another failure payload.
            raise ApplicationError(
                "Terminal result failed schema or wire-budget validation; "
                "referenced native evidence remains in the artifact store.",
                type="TERMINAL_PAYLOAD_INVALID",
                non_retryable=True,
            ) from None
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
        outcomes_enabled = workflow.patched("assessment-outcomes-v1")
        result = InvestigationResult(
            schema_version="corsair.result/2" if outcomes_enabled else "corsair.result/1",
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
        protocol_complete = False
        protocol_unresolved = False
        retained_held_pair = False
        try:
            self.phase = "prepare"
            prepared = await self._execute_bounded_activity(
                "corsair.prepare", request, PreparedCase, 120
            )
            result = result.model_copy(update={"manifest": prepared.manifest})
            calls_left, tools_left = budget.max_llm_calls, budget.max_tool_calls
            previous, feedback = None, None
            admitted_adversarial_payloads: set[str] = set()
            for index in range(1, budget.max_rounds + 1):
                self.round_index = index
                elapsed = (workflow.now() - started).total_seconds()
                if calls_left < 2 or tools_left < 1 or elapsed >= budget.max_elapsed_seconds:
                    result = result.model_copy(update={"reason": "Investigation budget exhausted."})
                    if outcomes_enabled:
                        protocol_complete = True
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
                decision = producer.decision
                if decision is not None and isinstance(decision.root, NoGroundedCandidate):
                    if outcomes_enabled:
                        protocol_unresolved = True
                        feedback = _mechanical_follow_up("producer-grounding")
                        result = result.model_copy(
                            update={"reason": f"Producer abstained: {decision.root.reason}"}
                        )
                        continue
                    if workflow.patched("producer-abstention-v1"):
                        result = result.model_copy(
                            update={"reason": f"Producer abstained: {decision.root.reason}"}
                        )
                        break
                    feedback = Feedback(gate="producer", reason=decision.root.reason)
                    result = result.model_copy(update={"reason": feedback.reason})
                    continue
                submission = producer.submission_for_verification()
                if submission is None:
                    feedback = producer.feedback or Feedback(
                        gate="producer", reason="No submission"
                    )
                    result = result.model_copy(update={"reason": feedback.reason})
                    if outcomes_enabled:
                        protocol_unresolved = True
                        if feedback.operational:
                            result = result.model_copy(
                                update={"execution_status": ExecutionStatus.ERROR}
                            )
                            break
                        feedback = _mechanical_follow_up("producer-grounding")
                        continue
                    if feedback.operational:
                        result = result.model_copy(
                            update={"execution_status": ExecutionStatus.ERROR}
                        )
                        break
                    continue
                payload_digest = _adversarial_payload_digest(submission)
                if outcomes_enabled and payload_digest in admitted_adversarial_payloads:
                    protocol_unresolved = True
                    feedback = _mechanical_follow_up("candidate-distinctness")
                    result = result.model_copy(
                        update={"reason": "Producer repeated an admitted adversarial payload."}
                    )
                    continue
                admitted_adversarial_payloads.add(payload_digest)
                previous = submission
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
                    if outcomes_enabled:
                        protocol_unresolved = True
                        if feedback.operational:
                            result = result.model_copy(
                                update={"execution_status": ExecutionStatus.ERROR}
                            )
                            break
                        feedback = _mechanical_follow_up("evidence-retry")
                        continue
                    if feedback.operational:
                        result = result.model_copy(
                            update={"execution_status": ExecutionStatus.ERROR}
                        )
                        break
                    continue
                if calls_left < 1:
                    result = result.model_copy(update={"reason": "No budget remains for review."})
                    if outcomes_enabled:
                        protocol_unresolved = True
                    break
                self.phase = "audit"
                audit_llm_call_limit, audit_tool_call_limit = 1, 0
                if workflow.patched("auditor-runtime-budget-v1"):
                    audit_llm_call_limit = min(2, calls_left)
                    audit_tool_call_limit = min(4, tools_left)
                    audit_request: AuditInput | dict[str, Any] = AuditInput(
                        finding=prepared.finding,
                        recipe=prepared.recipe,
                        source_excerpt=prepared.source_excerpt,
                        submission=previous,
                        max_output_tokens=budget.max_output_tokens,
                        llm_call_limit=audit_llm_call_limit,
                        tool_call_limit=audit_tool_call_limit,
                    )
                else:
                    # Default-valued Pydantic fields serialize into Temporal payloads.
                    # Retain this exact pre-limit command shape for old histories.
                    audit_request = {
                        "finding": prepared.finding,
                        "recipe": prepared.recipe,
                        "source_excerpt": prepared.source_excerpt,
                        "submission": previous,
                        "max_output_tokens": budget.max_output_tokens,
                    }
                audit = await self._execute_bounded_activity(
                    "corsair.audit",
                    audit_request,
                    AuditOutput,
                    180,
                )
                calls_left -= audit.usage.llm_calls
                tools_left -= audit.usage.tool_calls
                if (
                    audit.usage.llm_calls > audit_llm_call_limit
                    or audit.usage.tool_calls > audit_tool_call_limit
                    or calls_left < 0
                    or tools_left < 0
                ):
                    raise ValueError("Auditor returned usage outside its admitted sub-budget")
                round_result = round_result.model_copy(update={"audit": audit})
                rounds[-1] = round_result
                label, status, reason = decide(prepared, observation, audit)
                result = result.model_copy(
                    update={"disposition": label, "execution_status": status, "reason": reason}
                )
                if outcomes_enabled:
                    outcome = assessment_outcome(prepared, observation, audit)
                    if outcome is AssessmentOutcome.DEMONSTRATED:
                        result = result.model_copy(update={"assessment_outcome": outcome})
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
                    if outcome is AssessmentOutcome.NOT_DEMONSTRATED:
                        retained_held_pair = True
                    else:
                        protocol_unresolved = True
                    if status != ExecutionStatus.COMPLETED:
                        break
                    feedback = _mechanical_follow_up("assessment-continue")
                    continue
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
            else:
                if outcomes_enabled:
                    protocol_complete = True
            if (
                outcomes_enabled
                and protocol_complete
                and not protocol_unresolved
                and retained_held_pair
                and result.assessment_outcome is None
            ):
                result = result.model_copy(
                    update={
                        "assessment_outcome": AssessmentOutcome.NOT_DEMONSTRATED,
                        "reason": (
                            "Completed the bounded assessment protocol without demonstrating "
                            "exploitability within the assessed scope."
                        ),
                    }
                )
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
                update={
                    "execution_status": ExecutionStatus.ERROR,
                    "reason": "Investigation elapsed-time budget exhausted.",
                }
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
            if outcomes_enabled and result.execution_status is not ExecutionStatus.COMPLETED:
                result = result.model_copy(update={"assessment_outcome": None})
            result = result.model_copy(update={"rounds": rounds})
            result = await self._record_result(result)
        return result
