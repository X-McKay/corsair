"""Plan 1: Temporal owns rounds; normal activities own complete ADK episodes and I/O."""

import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import (
        MAX_TERMINAL_TIMELINE,
        AuditDecision,
        AuditInput,
        AuditOutput,
        Budget,
        Disposition,
        EvidenceInput,
        ExecutionStatus,
        Feedback,
        FixStatus,
        InvestigationRequest,
        InvestigationResult,
        Observation,
        PhaseTransition,
        PreparedCase,
        ProducerInput,
        ProducerOutput,
        RoundResult,
        Submission,
        Verdict,
        format_terminal_result,
    )
    from corsair.policies.operations import operation_prefix, round_operation_id
    from corsair.policies.time_bounds import (
        AUDITOR_ACTIVITY_SECONDS,
        PREPARE_ACTIVITY_SECONDS,
        RECORD_ATTEMPT_SECONDS,
        RECORD_FINALIZATION_SECONDS,
        evidence_activity_seconds,
        heartbeat_seconds,
        producer_activity_seconds,
    )
    from corsair.policies.verdicts import (
        SessionOutcome,
        case_verdict,
        decide,
        distinct_clean_negatives,
        fix_status,
        status_outcome,
        terminal_outcome,
        terminal_round,
    )


# The canonical case layer aggregates independent sessions. A lone clean negative
# must never become EXPLOIT_NOT_DEMONSTRATED. The threshold and the session cap are
# the admitted policy recorded in PreparedCase.manifest by the prepare activity, so
# scheduling and aggregation read the same replayed values, never worker Settings.
# Histories recorded before those fields existed decode to these defaults.
DEFAULT_NEGATIVE_THRESHOLD = 2

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
    Control-role or coverage facts are excluded too: given that a retry follows
    only a non-decisive round, reporting a healthy control would reveal the
    exploit outcome by elimination (ADR 0005).
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

    The last evaluated round decides a demonstration and names the session's
    candidate, but a later terminal operational failure (an ERROR/BLOCKED/CANCELLED
    round after it) must not be masked by an earlier non-decisive round: unless the
    earlier round positively demonstrated the exploit (at application or component
    scope), the operational failure carries into the outcome so the canonical result
    keeps its operational-error signal.
    """
    terminal = terminal_round(rounds)
    if prepared is not None and terminal is not None:
        outcome = terminal_outcome(prepared, terminal, result.fix_status)
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
    negative_threshold: int = DEFAULT_NEGATIVE_THRESHOLD,
) -> Verdict:
    """Pure aggregation of independent sessions into the canonical case verdict.

    ``earlier`` holds the outcomes of sessions that already ended; ``rounds`` and
    ``result`` describe the last session. Only ``case_verdict`` may promote clean
    negatives, so a lone clean negative stays INCONCLUSIVE.
    """
    outcomes = [*earlier, _session_outcome(prepared, rounds, result)]
    verdict, _reason = case_verdict(outcomes, negative_threshold)
    return verdict


def _submission_or_feedback(producer: ProducerOutput) -> Submission | Feedback:
    """A non-abstaining producer episode admits either a submission to verify or the
    feedback that ends the round without one."""
    submission = producer.submission_for_verification()
    if submission is not None:
        return submission
    return producer.feedback or Feedback(gate="producer", reason="No submission")


def _fold_decision(
    result: InvestigationResult,
    prepared: PreparedCase,
    observation: Observation,
    audit: AuditOutput,
) -> tuple[InvestigationResult, Disposition, ExecutionStatus]:
    """Fold one evaluated round (observation and audit) into the result by ``decide``."""
    label, status, reason = decide(prepared, observation, audit)
    folded = result.model_copy(
        update={"disposition": label, "execution_status": status, "reason": reason}
    )
    return folded, label, status


def _clean_negatives_admit_another_session(
    outcome: SessionOutcome,
    finished: Sequence[SessionOutcome],
    threshold: int,
    session: int,
    max_sessions: int,
    *,
    distinct: bool,
) -> bool:
    """Another session runs only while every earlier one ended in a clean negative and
    the threshold of clean negatives on distinct candidates is still unmet but
    reachable; any other outcome is already final for case_verdict.

    ``distinct`` is False only when replaying a history recorded before
    distinct-candidates-v1, which counted every clean session."""
    if distinct:
        clean = distinct_clean_negatives([*finished, outcome])
    else:
        clean = sum(o.clean_negative for o in finished) + outcome.clean_negative
    if not outcome.clean_negative or clean >= threshold:
        return False
    # The remaining sessions must still be able to reach the threshold.
    return clean + (max_sessions - session) >= threshold


@dataclass
class _Session:
    """One independent session: rounds, submission and feedback start blind."""

    index: int
    prefix: str
    rounds: list[RoundResult] = field(default_factory=list)
    previous: Submission | None = None
    feedback: Feedback | None = None

    def amend_last(self, **update: Any) -> None:
        self.rounds[-1] = self.rounds[-1].model_copy(update=update)


@dataclass
class _Run:
    """Deterministic state of one investigation; sessions share the root LLM/tool
    budget and the elapsed deadline, only rounds restart per session."""

    run_id: str
    budget: Budget
    started: datetime
    result: InvestigationResult
    prepared: PreparedCase | None = None
    calls_left: int = 0
    tools_left: int = 0
    sessions: list[_Session] = field(default_factory=list)
    finished: list[SessionOutcome] = field(default_factory=list)

    def note(self, **update: Any) -> None:
        self.result = self.result.model_copy(update=update)

    def exhausted(self, elapsed: float) -> bool:
        return (
            self.calls_left < 2 or self.tools_left < 1 or elapsed >= self.budget.max_elapsed_seconds
        )

    @property
    def rounds(self) -> list[RoundResult]:
        return [round_result for session in self.sessions for round_result in session.rounds]


class BudgetExhausted(Exception):
    """No action time remains before the investigation admission deadline."""


@workflow.defn(name="corsair.investigation")
class InvestigationWorkflow:
    def __init__(self) -> None:
        self._phase = "pending"
        self.session_index = 0
        self.round_index = 0
        self.max_sessions = 0
        self.max_rounds = 0
        self.gate: str | None = None
        self.started: datetime | None = None
        self.deadline: datetime | None = None
        self.timeline: list[dict[str, str | int | None]] = []

    @property
    def phase(self) -> str:
        return self._phase

    @phase.setter
    def phase(self, value: str) -> None:
        """Record each transition at deterministic workflow time.

        The status query and the recorded result keep only the most recent
        MAX_TERMINAL_TIMELINE transitions. They are presentation state that never feeds
        a command or a verdict; in the result they ride in the record activity's input,
        which replay does not compare, so recorded histories replay unchanged.
        """
        self._phase = value
        # Unit tests drive finalization outside a workflow loop, where there is no clock.
        at = workflow.now().isoformat() if workflow.in_workflow() else None
        self.timeline.append(
            {"phase": value, "session": self.session_index, "round": self.round_index, "at": at}
        )
        del self.timeline[:-MAX_TERMINAL_TIMELINE]

    @workflow.query
    def status(self) -> dict:
        """Workflow-owned progress metadata only: no model, source or payload content."""
        return {
            "phase": self.phase,
            "session": self.session_index,
            "round": self.round_index,
            "max_sessions": self.max_sessions,
            "max_rounds": self.max_rounds,
            "gate": self.gate,
            "started": self.started.isoformat() if self.started else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "timeline": list(self.timeline),
        }

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
            heartbeat_timeout=timedelta(seconds=heartbeat_seconds(seconds)),
            retry_policy=RetryPolicy(maximum_attempts=1),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    async def _record_result(self, result: InvestigationResult) -> InvestigationResult:
        """Persist the final receipt within its separate retry/finalization allowance."""
        self.phase = "record"
        try:
            timeline = [PhaseTransition.model_validate(entry) for entry in self.timeline]
            result = format_terminal_result(result.model_copy(update={"timeline": timeline}))
        except ValueError:
            # An unbounded validation exception must not become another failure payload.
            raise ApplicationError(
                "Terminal result failed schema or wire-budget validation; "
                "referenced native evidence remains in the artifact store.",
                type="TERMINAL_PAYLOAD_INVALID",
                non_retryable=True,
            ) from None
        record = workflow.start_activity(
            "corsair.record",
            result,
            result_type=InvestigationResult,
            start_to_close_timeout=timedelta(seconds=RECORD_ATTEMPT_SECONDS),
            schedule_to_close_timeout=(
                timedelta(seconds=RECORD_FINALIZATION_SECONDS)
                if workflow.patched("bounded-finalization-v1")
                else None
            ),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        try:
            recorded = await asyncio.shield(record)
        except asyncio.CancelledError:
            # The terminal decision was made before the cancel arrived and the shield
            # kept the record activity running: await that same activity so the run
            # closes with its committed result.{run_id} rather than none.
            if not workflow.patched("record-survives-cancel-v1"):
                raise
            recorded = await record
        self.phase = "complete"
        return recorded

    def _reject(self, state: _Run, session: _Session, feedback: Feedback) -> bool:
        """Carry a round's rejection to the next round; an operational one ends the session."""
        session.feedback = feedback
        self.gate = feedback.gate
        state.note(reason=feedback.reason)
        if feedback.operational:
            state.note(execution_status=ExecutionStatus.ERROR)
            return False
        return True

    async def _produce(
        self, state: _Run, prepared: PreparedCase, session: _Session, index: int, elapsed: float
    ) -> ProducerOutput:
        """One producer episode within the remaining shared budget, charged on return."""
        budget = state.budget
        call_limit = min(budget.episode_llm_calls, state.calls_left - 1)
        producer = await self._execute_bounded_activity(
            "corsair.produce",
            ProducerInput(
                run_id=state.run_id,
                prepared=prepared,
                budget=budget,
                round_index=index,
                previous=session.previous,
                feedback=session.feedback,
                llm_call_limit=call_limit,
                tool_call_limit=state.tools_left,
            ),
            ProducerOutput,
            producer_activity_seconds(budget, elapsed),
        )
        state.calls_left -= producer.usage.llm_calls
        state.tools_left -= producer.usage.tool_calls
        if producer.usage.llm_calls > call_limit or state.tools_left < 0:
            raise ValueError("Producer returned usage outside its admitted sub-budget")
        return producer

    async def _evidence(
        self,
        state: _Run,
        prepared: PreparedCase,
        submission: Submission,
        operation_id: str,
        fixed: bool = False,
    ) -> Observation:
        """One trusted evidence run of the submission on the vulnerable or fixed revision."""
        # The default converter serializes every field, so fixed=False matches the
        # vulnerable-revision payload that omitted it.
        evidence = EvidenceInput(
            run_id=state.run_id,
            operation_id=operation_id,
            prepared=prepared,
            submission=submission,
            budget=state.budget,
            fixed=fixed,
        )
        return await self._execute_bounded_activity(
            "corsair.evidence", evidence, Observation, evidence_activity_seconds(state.budget)
        )

    async def _audit(
        self, state: _Run, prepared: PreparedCase, submission: Submission
    ) -> AuditOutput:
        """One blind audit episode within the remaining shared budget, charged on return."""
        budget = state.budget
        audit_llm_call_limit, audit_tool_call_limit = 1, 0
        if workflow.patched("auditor-runtime-budget-v1"):
            audit_llm_call_limit = min(2, state.calls_left)
            audit_tool_call_limit = min(4, state.tools_left)
            audit_request: AuditInput | dict[str, Any] = AuditInput(
                finding=prepared.finding,
                recipe=prepared.recipe,
                source_excerpt=prepared.source_excerpt,
                submission=submission,
                line_provenance=prepared.line_provenance,
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
                "submission": submission,
                "max_output_tokens": budget.max_output_tokens,
            }
        audit = await self._execute_bounded_activity(
            "corsair.audit",
            audit_request,
            AuditOutput,
            AUDITOR_ACTIVITY_SECONDS,
        )
        state.calls_left -= audit.usage.llm_calls
        state.tools_left -= audit.usage.tool_calls
        if (
            audit.usage.llm_calls > audit_llm_call_limit
            or audit.usage.tool_calls > audit_tool_call_limit
            or state.calls_left < 0
            or state.tools_left < 0
        ):
            raise ValueError("Auditor returned usage outside its admitted sub-budget")
        return audit

    async def _run_round(
        self, state: _Run, prepared: PreparedCase, session: _Session, index: int
    ) -> bool:
        """One producer, evidence, audit (and fix) round; True when another round follows."""
        elapsed = (workflow.now() - state.started).total_seconds()
        if state.exhausted(elapsed):
            state.note(reason="Investigation budget exhausted.")
            return False
        self.phase = "producer"
        producer = await self._produce(state, prepared, session, index, elapsed)
        session.rounds.append(RoundResult(index=index, session=session.index, producer=producer))
        abstention = producer.abstention_reason()
        if abstention is not None:
            if workflow.patched("producer-abstention-v1"):
                state.note(reason=f"Producer abstained: {abstention}")
                return False
            return self._reject(state, session, Feedback(gate="producer", reason=abstention))
        step = _submission_or_feedback(producer)
        if isinstance(step, Feedback):
            return self._reject(state, session, step)
        session.previous = step
        self.phase = "evidence"
        operation_id = round_operation_id(state.run_id, session.index, index)
        observation = await self._evidence(state, prepared, step, operation_id)
        session.amend_last(observation=observation)
        if observation.feedback is not None:
            return self._reject(state, session, observation.feedback)
        if state.calls_left < 1:
            state.note(reason="No budget remains for review.")
            return False
        self.phase = "audit"
        audit = await self._audit(state, prepared, step)
        session.amend_last(audit=audit)
        state.result, label, status = _fold_decision(state.result, prepared, observation, audit)
        if label in {Disposition.SUPPORTED, Disposition.CONDITIONAL}:
            if prepared.fixed_source is not None:
                self.phase = "fix"
                fixed = await self._evidence(
                    state, prepared, step, f"{session.prefix}.fix{index}", fixed=True
                )
                state.note(fix_status=fix_status(fixed), fix_observation=fixed)
            return False
        if status != ExecutionStatus.COMPLETED:
            return False
        session.feedback = _retry_feedback(audit)
        self.gate = session.feedback.gate
        return True

    def _another_session(self, state: _Run, prepared: PreparedCase, session: _Session) -> bool:
        """Admit the next session and record this one's outcome as finished."""
        outcome = _session_outcome(prepared, session.rounds, state.result)
        manifest = prepared.manifest
        if not _clean_negatives_admit_another_session(
            outcome,
            state.finished,
            manifest.negative_threshold,
            session.index,
            manifest.max_sessions,
            distinct=workflow.patched("distinct-candidates-v1"),
        ):
            return False
        elapsed = (workflow.now() - state.started).total_seconds()
        if state.exhausted(elapsed) or not workflow.patched("independent-sessions-v1"):
            return False
        state.finished.append(outcome)
        return True

    @workflow.run
    async def run(self, request: InvestigationRequest) -> InvestigationResult:
        run_id = workflow.info().workflow_id
        budget = request.budget
        started = workflow.now()
        self.started = started
        self.max_rounds = budget.max_rounds
        self.deadline = started + timedelta(seconds=budget.max_elapsed_seconds)
        state = _Run(
            run_id=run_id,
            budget=budget,
            started=started,
            result=InvestigationResult(
                run_id=run_id,
                case_id=request.case.case_id,
                disposition=Disposition.INCONCLUSIVE,
                execution_status=ExecutionStatus.COMPLETED,
                reason="No admissible observation was collected.",
                scope=request.case.finding.claim_scope,
                fix_status=(
                    FixStatus.UNVERIFIED if request.case.fixed_source else FixStatus.NOT_REQUESTED
                ),
            ),
        )
        try:
            self.phase = "prepare"
            prepared = await self._execute_bounded_activity(
                "corsair.prepare", request, PreparedCase, PREPARE_ACTIVITY_SECONDS
            )
            state.prepared = prepared
            state.note(manifest=prepared.manifest)
            state.calls_left, state.tools_left = budget.max_llm_calls, budget.max_tool_calls
            max_sessions = prepared.manifest.max_sessions
            self.max_sessions = max_sessions
            for index in range(1, max_sessions + 1):
                self.session_index = index
                session = _Session(index, operation_prefix(run_id, index))
                state.sessions.append(session)
                if index > 1:
                    # Fresh, blind session: nothing from an earlier one is carried
                    # over (no submission, feedback, operation id or outcome).
                    state.note(
                        disposition=Disposition.INCONCLUSIVE,
                        reason="No admissible observation was collected.",
                    )
                for round_index in range(1, budget.max_rounds + 1):
                    self.round_index = round_index
                    if not await self._run_round(state, prepared, session, round_index):
                        break
                if index == max_sessions or not self._another_session(state, prepared, session):
                    break
        except ActivityError as exc:
            cause_type = getattr(exc.cause, "type", "")
            # Operational failures must not erase a previously admitted source observation.
            if is_cancelled_exception(exc):
                status = ExecutionStatus.CANCELLED
            elif self.phase == "prepare" and cause_type in {"PREPARE_BLOCKED", "SOURCE_DENIED"}:
                status = ExecutionStatus.BLOCKED
            else:
                status = ExecutionStatus.ERROR
            state.note(
                execution_status=status,
                reason=f"{self.phase}: {exc.cause}",
                usage_complete=self.phase not in {"producer", "audit"},
            )
        except BudgetExhausted:
            state.note(reason="Investigation elapsed-time budget exhausted.")
        except ValueError as exc:
            state.note(execution_status=ExecutionStatus.ERROR, reason=str(exc))
        except asyncio.CancelledError:
            state.note(
                execution_status=ExecutionStatus.CANCELLED,
                reason="Run cancelled.",
                usage_complete=self.phase not in {"producer", "audit"},
            )
            raise
        finally:
            state.note(rounds=state.rounds)
            prepared_case = state.prepared
            state.note(
                verdict=_aggregate_case_verdict(
                    prepared_case,
                    state.sessions[-1].rounds if state.sessions else [],
                    state.result,
                    state.finished,
                    prepared_case.manifest.negative_threshold
                    if prepared_case is not None
                    else DEFAULT_NEGATIVE_THRESHOLD,
                )
            )
            state.result = await self._record_result(state.result)
        return state.result
