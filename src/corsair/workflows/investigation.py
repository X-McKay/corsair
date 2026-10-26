"""Plan 1: Temporal owns rounds; normal activities own complete ADK episodes and I/O."""

import asyncio
import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import (
        AuditDecision,
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
        Verdict,
        format_terminal_result,
    )
    from corsair.policies.verdicts import (
        SessionOutcome,
        case_verdict,
        decide,
        fix_status,
        session_verdict,
        status_outcome,
    )


# The canonical case layer aggregates independent sessions. A lone clean negative
# must never become EXPLOIT_NOT_DEMONSTRATED, so the threshold is 2 and sessions are
# capped at 2 by default. See Settings.negative_threshold / Settings.max_sessions.
NEGATIVE_THRESHOLD = 2
MAX_SESSIONS = 2

# A payload-pair proposal that was not refined by the producer on retry. It carries
# no outcome and no structural claim (a prior round may have been rejected or marked
# invalid): it only asks for a fresh source-grounded candidate.
_BLIND_RETRY_REASON = "Propose a different source-grounded candidate payload pair."


def _retry_feedback(audit: AuditOutput) -> Feedback:
    """Feedback for the next producer round after a completed round that did not
    demonstrate the exploit.

    Outcome-blind contract (ADR 0004): the producer must never learn the exploit
    outcome, so this never forwards ``decide()``'s disposition reason, which
    encodes it. The only corrective signal it may carry is the auditor's own
    rejection, which the auditor formed without seeing any run result; a round the
    auditor accepted leaves nothing the producer may see, so it retries blind.
    """
    if audit.review is not None and audit.review.decision is not AuditDecision.ACCEPT:
        return Feedback(gate="audit", reason=audit.review.reason)
    return Feedback(gate="retry", reason=_BLIND_RETRY_REASON)


# A positive demonstration is a fact that a later operational failure cannot erase.
_DEMONSTRATIONS = frozenset({Verdict.EXPLOIT_DEMONSTRATED, Verdict.COMPONENT_EXPLOIT_DEMONSTRATED})


def _session_outcome(
    prepared: PreparedCase | None,
    rounds: list[RoundResult],
    result: InvestigationResult,
) -> SessionOutcome:
    """Pure outcome of ONE session from its own rounds and terminal status.

    The last evaluated round decides a demonstration, but a later terminal
    operational failure (an ERROR/BLOCKED/CANCELLED round after it) must not be
    masked by an earlier non-decisive round: unless the earlier round positively
    demonstrated the exploit (at application or component scope), the operational
    failure carries into the outcome so the canonical result keeps its
    operational-error signal.
    """
    terminal = next(
        (r for r in reversed(rounds) if r.observation is not None and r.audit is not None),
        None,
    )
    if prepared is not None and terminal is not None:
        assert terminal.observation is not None and terminal.audit is not None
        outcome = session_verdict(prepared, terminal.observation, terminal.audit, result.fix_status)
    else:
        outcome = status_outcome(result.execution_status, result.reason)
    if (
        result.execution_status is not ExecutionStatus.COMPLETED
        and outcome.verdict not in _DEMONSTRATIONS
    ):
        outcome = status_outcome(result.execution_status, result.reason)
    return outcome


def _aggregate_case_verdict(
    prepared: PreparedCase | None,
    rounds: list[RoundResult],
    result: InvestigationResult,
    earlier: Sequence[SessionOutcome] = (),
) -> Verdict:
    """Pure aggregation of independent sessions into the canonical case verdict.

    ``earlier`` holds the outcomes of sessions that already ended; ``rounds`` and
    ``result`` describe the last session. Only ``case_verdict`` may promote clean
    negatives, so a lone clean negative stays INCONCLUSIVE.
    """
    outcomes = [*earlier, _session_outcome(prepared, rounds, result)]
    verdict, _reason = case_verdict(outcomes, NEGATIVE_THRESHOLD)
    return verdict


def _operation_prefix(run_id: str, session: int) -> str:
    """Session 1 keeps the original operation ids so earlier histories replay."""
    return run_id if session == 1 else f"{run_id}.s{session}"


class BudgetExhausted(Exception):
    """No action time remains before the investigation admission deadline."""


@workflow.defn(name="corsair.investigation")
class InvestigationWorkflow:
    def __init__(self) -> None:
        self.phase = "pending"
        self.session_index = 0
        self.round_index = 0
        self.deadline: datetime | None = None

    @workflow.query
    def status(self) -> dict:
        return {"phase": self.phase, "session": self.session_index, "round": self.round_index}

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
        result = InvestigationResult(
            run_id=run_id,
            case_id=request.case.case_id,
            disposition=Disposition.INCONCLUSIVE,
            execution_status=ExecutionStatus.COMPLETED,
            reason="No admissible observation was collected.",
            scope=request.case.finding.claim_scope,
            fix_status=(
                FixStatus.UNVERIFIED if request.case.fixed_source else FixStatus.NOT_REQUESTED
            ),
        )
        rounds: list[RoundResult] = []
        session_rounds: list[RoundResult] = []
        finished: list[SessionOutcome] = []
        prepared: PreparedCase | None = None
        try:
            self.phase = "prepare"
            prepared = await self._execute_bounded_activity(
                "corsair.prepare", request, PreparedCase, 120
            )
            result = result.model_copy(update={"manifest": prepared.manifest})
            # Sessions share the root LLM/tool budget and the elapsed deadline; only
            # rounds restart per session.
            calls_left, tools_left = budget.max_llm_calls, budget.max_tool_calls
            for session in range(1, MAX_SESSIONS + 1):
                self.session_index = session
                prefix = _operation_prefix(run_id, session)
                session_rounds = []
                if session > 1:
                    # Fresh, blind session: nothing from an earlier one is carried
                    # over (no submission, feedback, operation id or outcome).
                    result = result.model_copy(
                        update={
                            "disposition": Disposition.INCONCLUSIVE,
                            "reason": "No admissible observation was collected.",
                        }
                    )
                previous, feedback = None, None
                for index in range(1, budget.max_rounds + 1):
                    self.round_index = index
                    elapsed = (workflow.now() - started).total_seconds()
                    if calls_left < 2 or tools_left < 1 or elapsed >= budget.max_elapsed_seconds:
                        result = result.model_copy(
                            update={"reason": "Investigation budget exhausted."}
                        )
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
                    round_result = RoundResult(index=index, session=session, producer=producer)
                    session_rounds.append(round_result)
                    rounds.append(round_result)
                    decision = producer.decision
                    if decision is not None and isinstance(decision.root, NoGroundedCandidate):
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
                        if feedback.operational:
                            result = result.model_copy(
                                update={"execution_status": ExecutionStatus.ERROR}
                            )
                            break
                        continue
                    previous = submission
                    self.phase = "evidence"
                    observation = await self._execute_bounded_activity(
                        "corsair.evidence",
                        EvidenceInput(
                            run_id=run_id,
                            operation_id=f"{prefix}.r{index}",
                            prepared=prepared,
                            submission=previous,
                            budget=budget,
                        ),
                        Observation,
                        2 * budget.probe_timeout_seconds + 45,
                    )
                    round_result = round_result.model_copy(update={"observation": observation})
                    session_rounds[-1] = round_result
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
                        result = result.model_copy(
                            update={"reason": "No budget remains for review."}
                        )
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
                    session_rounds[-1] = round_result
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
                                    operation_id=f"{prefix}.fix{index}",
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
                    feedback = _retry_feedback(audit)
                # Another session runs only while every earlier one ended in an
                # independent clean negative and the threshold is still unmet; any
                # other outcome is already final for case_verdict.
                if session == MAX_SESSIONS:
                    break
                outcome = _session_outcome(prepared, session_rounds, result)
                clean = sum(o.clean_negative for o in finished) + outcome.clean_negative
                if not outcome.clean_negative or clean >= NEGATIVE_THRESHOLD:
                    break
                elapsed = (workflow.now() - started).total_seconds()
                if calls_left < 2 or tools_left < 1 or elapsed >= budget.max_elapsed_seconds:
                    break
                if not workflow.patched("independent-sessions-v1"):
                    break
                finished.append(outcome)
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
            result = result.model_copy(
                update={
                    "verdict": _aggregate_case_verdict(prepared, session_rounds, result, finished)
                }
            )
            result = await self._record_result(result)
        return result
