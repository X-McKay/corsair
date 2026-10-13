"""E2E-0 composition: identification, planning, authoring, frozen execution, assessment, gates.

Each stage reuses its own factory and typed contract; routing is a total match on the previous
stage's status, every abstention stops the run with its reason, and nothing loops between
stages. Environment evidence is operator-supplied (IDEA-0004). The gate verdict is computed
from the frozen evidence whether or not the assessment agent completes. ``run_chain`` holds the
routing for every mode over injected stage and revision ports; ``run_direct`` binds them in-process
and the durable chain (``corsair.workflows.chain``) binds child workflows and activities.
"""

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Awaitable, Callable, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.agents.evidence_assessment.agent import assessment_prompt, create_evidence_assessment_agent
from corsair.agents.evidence_assessment.contracts import WINDOW_LINES, AssessmentInput, EvidenceAssessment
from corsair.agents.evidence_assessment.tools import AssessmentDependencies
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.issue_analysis.identification import create_issue_identification_agent, identification_prompt
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.issue_analysis.tools import FixtureDependencies
from corsair.agents.source.contracts import Contract
from corsair.agents.source.tools import READ_LINE_LIMIT
from corsair.agents.test_authoring.agent import authoring_prompt, create_test_authoring_agent
from corsair.agents.test_authoring.contracts import TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.tools import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.agent import PlanningDependencies, create_test_planning_agent, planning_prompt
from corsair.agents.test_planning.contracts import EnvironmentEvidence, ReadyTestPlan, TestPlanningInput
from corsair.core.disposition import AssessmentEvidence, EnvironmentIdentity, GateResult, ObservationPlan, assess
from corsair.nodes.witness import WitnessEvidence, witness_evidence
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun, TestRunner, WitnessRequest

from .evidence import evidence_items, freeze, observation_plan, run_evidence, witness_request

Stage = Literal["identification", "planning", "authoring", "execution", "assessment"]
AgentStage = Literal["identification", "planning", "authoring", "assessment"]
Purpose = Literal["development", "baseline", "candidate"]


class StageLimits(Contract):
    """One stage run's caps, derived from its own input and recorded in its receipt (SPEC-0043)."""
    request_limit: int = Field(strict=True, gt=0)
    tool_calls_limit: int = Field(strict=True, ge=0)
    total_tokens_limit: int = Field(strict=True, gt=0)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    # Derivation: windows needed to read the stage's readable inputs once, plus input-sized work calls.
    read_windows: int = Field(strict=True, ge=0)
    work_tool_calls: int = Field(strict=True, ge=0)

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class StageBudget(Contract):
    """Operator-owned per-stage ceilings and derivation; the provider configuration owns the response cap.

    A run's tool calls are its read windows plus its work calls plus ``slack_tool_calls``; requests are
    those calls plus the output request and its retries plus one; tokens are ``tokens_per_request`` per
    request. Each is capped by the ceiling here, so a derived cap never exceeds what the operator admitted.
    """
    request_limit: int = Field(strict=True, gt=0, le=64)
    tool_calls_limit: int = Field(strict=True, ge=0, le=48)
    total_tokens_limit: int = Field(strict=True, gt=0, le=262144)
    timeout_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)
    slack_tool_calls: int = Field(default=2, strict=True, ge=0, le=8)
    tokens_per_request: int = Field(default=12000, strict=True, gt=0, le=32768)

    def limits(self, read_windows: int, work_tool_calls: int, output_retries: int) -> StageLimits:
        tools = min(read_windows + work_tool_calls + self.slack_tool_calls, self.tool_calls_limit)
        requests = min(tools + output_retries + 2, self.request_limit)
        return StageLimits(request_limit=requests, tool_calls_limit=tools,
                           total_tokens_limit=min(requests * self.tokens_per_request, self.total_tokens_limit),
                           timeout_seconds=self.timeout_seconds, read_windows=read_windows,
                           work_tool_calls=work_tool_calls)


class CompositionBudget(Contract):
    identification: StageBudget = StageBudget(request_limit=20, tool_calls_limit=16, total_tokens_limit=128000,
                                              timeout_seconds=300, tokens_per_request=8000)
    planning: StageBudget = StageBudget(request_limit=20, tool_calls_limit=16, total_tokens_limit=160000,
                                        timeout_seconds=600, tokens_per_request=10000)
    authoring: StageBudget = StageBudget(request_limit=32, tool_calls_limit=28, total_tokens_limit=262144,
                                         timeout_seconds=900, slack_tool_calls=2, tokens_per_request=12000)
    assessment: StageBudget = StageBudget(request_limit=32, tool_calls_limit=28, total_tokens_limit=262144,
                                          timeout_seconds=600, tokens_per_request=10000)
    dev_runs: int = Field(default=3, strict=True, ge=1, le=5)
    output_retries: int = Field(default=1, strict=True, ge=0, le=1)
    admission_refusals: int = Field(default=1, strict=True, ge=0, le=2)


Limit = Literal["request_limit", "tool_calls_limit", "total_tokens_limit", "timeout_seconds"]


class BudgetExhausted(Contract):
    """The typed outcome of a stage that ended on one of its own caps instead of returning its output."""
    status: Literal["budget_exhausted"] = "budget_exhausted"
    stage: Literal["identification", "planning", "authoring", "assessment"]
    limit: Limit
    cap: float
    limits: StageLimits


def _windows(contents, window: int = READ_LINE_LIMIT) -> int:
    return sum(-(-len(content.splitlines()) // window) or 1 for content in contents)


def stage_limits(stage: "AgentStage", inputs: Any, budget: "CompositionBudget") -> StageLimits:
    """Caps from the task: each readable input once in tool windows, plus the stage's own work calls."""
    match stage:
        case "identification" | "planning":
            reads, work = _windows(source.content for source in inputs.source_files), 0
        case "authoring":
            # Per development run: up to two writes of each planned test path and the run itself; plus each
            # admission refusal the author may act on.
            paths = {inputs.plan.control.test_path, inputs.plan.security.test_path}
            reads = _windows(source.content for source in inputs.source_files)
            work = budget.dev_runs * (2 * len(paths) + 1) + budget.admission_refusals
        case "assessment":
            reads, work = _windows((item.content for item in inputs.items), WINDOW_LINES), 0
    return getattr(budget, stage).limits(reads, work, budget.output_retries)


def exhaustion(stage: "AgentStage", limits: StageLimits, usage: RunUsage | None,
               failure: BaseException | None) -> BudgetExhausted | None:
    """Which cap ended a stage that returned no output; None when it failed for another reason."""
    if failure is None:
        return None
    kind = failure.kind if isinstance(failure, RecordedFailure) else type(failure).__name__
    limit: Limit | None = None
    if kind == "TimeoutError":
        limit = "timeout_seconds"
    elif kind == "UsageLimitExceeded":
        limit = next((name for name in ("tool_calls_limit", "total_tokens_limit", "request_limit")
                      if name in str(failure)), "request_limit")
    elif usage is not None and usage.tool_calls >= limits.tool_calls_limit:
        # Its tools were withdrawn at the cap and it could not complete its output without them.
        limit = "tool_calls_limit"
    if limit is None:
        return None
    return BudgetExhausted(stage=stage, limit=limit, cap=getattr(limits, limit), limits=limits)


@dataclass(frozen=True)
class StageModels:
    """One explicit model per stage; the same instance may serve several stages."""
    identification: Model
    planning: Model
    authoring: Model
    assessment: Model


class Runners(Protocol):
    """Operator-owned: a fresh-workspace runner for authoring development runs and for each frozen revision."""
    def __call__(self, purpose: Purpose) -> TestRunner: ...


@dataclass(frozen=True)
class FixtureCase:
    """Operator inputs: the issue over the baseline revision's saved source, and hand-supplied environment facts."""
    issue: IssueAnalysisInput
    environment: EnvironmentEvidence
    environment_identity: EnvironmentIdentity
    # Operator-known digest of each revision's captured source; a run from any other source is refused.
    revision_sources: dict[Literal["baseline", "candidate"], str]
    # Operator-approved probe target and planned effect file; without it no witness is requested.
    witness_envelope: WitnessRequest | None = None


@dataclass(frozen=True)
class StageAttempt:
    stage: Stage
    output: Any
    usage: RunUsage | None  # None: not observed, as for a durable stage that closed without returning
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: BaseException | None
    limits: StageLimits | None = None  # None: refused before its limits were derived
    exhausted: BudgetExhausted | None = None


@dataclass(frozen=True)
class FrozenExecution:
    revision: Literal["baseline", "candidate"]
    operation: UUID
    observed: NativeTestRun | None
    failure: BaseException | None


@dataclass(frozen=True)
class DirectRun:
    """Everything the run produced; ``stopped_at`` names the stage whose outcome ended it, if any."""
    stopped_at: Stage | None
    reason: str
    attempts: tuple[StageAttempt, ...]
    identification: IssueIdentification | None = None
    plan: ReadyTestPlan | None = None
    patch: TestPatch | None = None
    observation_plan: ObservationPlan | None = None
    executions: tuple[FrozenExecution, ...] = ()
    gate: GateResult | None = None
    assessment: EvidenceAssessment | None = None
    witnesses: tuple[WitnessEvidence, ...] = ()
    limitations: tuple[str, ...] = field(default=())


class RecordedFailure(Exception):
    """A failure observed in another process, kept as its native type name and message; never re-raised there."""
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# Mode ports: a stage invoker returns the attempt it made; a revision executor runs one frozen revision
# once and raises if nothing was observed. Neither retries.
StageInvoker = Callable[[AgentStage, Any], Awaitable[StageAttempt]]


class RevisionExecutor(Protocol):
    async def __call__(self, revision: Literal["baseline", "candidate"], patch: ApprovedPatch, *, control_test_id: str,
                       security_test_id: str, discovery_command: tuple[str, ...], operation: UUID,
                       witness: WitnessRequest | None = None) -> NativeTestRun: ...


AGENTS = {"identification": create_issue_identification_agent, "planning": create_test_planning_agent,
          "authoring": create_test_authoring_agent, "assessment": create_evidence_assessment_agent}


def stage_call(stage: AgentStage, inputs: Any, budget: CompositionBudget, runner: TestRunner | None) -> tuple[str, Any]:
    """Prompt and dependencies for one stage; the mode supplies the authoring stage's development runner."""
    match stage:
        case "identification":
            return identification_prompt(inputs), FixtureDependencies(inputs)
        case "planning":
            return planning_prompt(inputs), PlanningDependencies(inputs)
        case "authoring":
            return authoring_prompt(inputs), AuthoringDependencies(inputs, runner, AuthoringBudget(
                dev_runs=budget.dev_runs, admission_refusals=budget.admission_refusals))
        case "assessment":
            return assessment_prompt(inputs), AssessmentDependencies(inputs)


async def _invoke(stage: AgentStage, agent: Agent[Any, Any], prompt: str, deps: Any, limits: StageLimits) -> StageAttempt:
    usage, messages, output, failure = RunUsage(), [], None, None
    started = perf_counter()
    try:
        with capture_run_messages() as messages:
            async with asyncio.timeout(limits.timeout_seconds):
                output = (await agent.run(prompt, deps=deps, usage=usage, usage_limits=limits.usage_limits())).output
    except Exception as exc:
        failure = exc
    return StageAttempt(stage, output, usage, tuple(messages), perf_counter() - started, failure, limits,
                        exhaustion(stage, limits, usage, failure))


# Recorded on every run that reaches the gates, because nothing below observes them.
UNOBSERVED = ("The witness probe runs inside the test interpreter: it is operator-owned and tamper-evident, not "
              "tamper-proof against hostile test code.",
              "Sandbox events are observed only as permission errors raised on the witness path; policy or resource "
              "events elsewhere are not observed.",
              "Environment identity is the operator's declaration for both revisions, not an observed image or "
              "dependency digest.")


async def run_direct(case: FixtureCase, models: StageModels, runners: Runners,
                     budget: CompositionBudget = CompositionBudget()) -> DirectRun:
    """One E2E-0 investigation over a baseline and candidate revision; never retries a stage."""
    async def invoke(stage: AgentStage, inputs: Any) -> StageAttempt:
        agent = AGENTS[stage](getattr(models, stage), output_retries=budget.output_retries)
        prompt, deps = stage_call(stage, inputs, budget, runners("development") if stage == "authoring" else None)
        return await _invoke(stage, agent, prompt, deps, stage_limits(stage, inputs, budget))

    async def execute(revision, patch, **request) -> NativeTestRun:
        return runners(revision).run(patch, **request)
    return await run_chain(case, invoke, execute, new_operation=uuid4)


async def run_chain(case: FixtureCase, invoke: StageInvoker, execute: RevisionExecutor, *,
                    new_operation: Callable[[], UUID]) -> DirectRun:
    """Mode-independent routing: each stage at most once, revisions once each, gates over frozen evidence."""
    attempts: list[StageAttempt] = []
    issue, environment = case.issue, case.environment

    async def _stage(stage: AgentStage, inputs: Any) -> Any:
        attempts.append(await invoke(stage, inputs))
        return attempts[-1].output

    def stop(stage: Stage, reason: str, **values) -> DirectRun:
        return DirectRun(stopped_at=stage, reason=reason, attempts=tuple(attempts), **values)

    def failure_of(stage: Stage) -> str:
        exhausted = attempts[-1].exhausted
        if exhausted is not None:
            return (f"{stage} budget exhausted: {exhausted.limit} {exhausted.cap:g} "
                    f"(derived from {exhausted.limits.read_windows} read windows and "
                    f"{exhausted.limits.work_tool_calls} work calls)")
        failed = attempts[-1].failure
        kind = failed.kind if isinstance(failed, RecordedFailure) else type(failed).__name__
        return f"{stage} produced no output: {kind}: {failed}"[:2048]

    identification = await _stage("identification", issue)
    if not isinstance(identification, IssueIdentification):
        return stop("identification", failure_of("identification"))
    if identification.status != "ready":
        return stop("identification", f"identification {identification.status}: {identification.reason}",
                    identification=identification)

    try:
        planning_input = TestPlanningInput(scope=issue.scope, identification=identification,
                                           source_files=issue.source_files, environment=environment)
    except ValueError as exc:
        return stop("planning", f"planning input refused: {exc}"[:2048], identification=identification)
    plan = await _stage("planning", planning_input)
    if plan is None:
        return stop("planning", failure_of("planning"), identification=identification)
    if not isinstance(plan, ReadyTestPlan):
        return stop("planning", f"plan unsupported: {plan.missing_capability}", identification=identification)

    try:
        authoring_input = TestAuthoringInput(plan=plan, source_files=issue.source_files, environment=environment)
    except ValueError as exc:
        return stop("authoring", f"authoring input refused: {exc}"[:2048], identification=identification, plan=plan)
    patch = await _stage("authoring", authoring_input)
    if patch is None:
        return stop("authoring", failure_of("authoring"), identification=identification, plan=plan)
    if not isinstance(patch, TestPatch):
        return stop("authoring", f"authoring blocked at {patch.layer}: {patch.reason}",
                    identification=identification, plan=plan)

    try:
        expected = observation_plan(plan, patch)
        frozen = freeze(patch, environment.approved_test_paths)
    except ValueError as exc:
        return stop("execution", f"patch not frozen: {exc}"[:2048], identification=identification, plan=plan,
                    patch=patch)
    executions = []
    try:
        request, unrequested = witness_request(identification, case.witness_envelope), ()
    except ValueError as exc:
        # No approved envelope covers the identified target: run without a witness and say so.
        request, unrequested = None, (f"no witness requested: {exc}"[:512],)
    for revision in ("baseline", "candidate"):
        operation, observed, failure = new_operation(), None, None
        try:
            observed = await execute(revision, frozen, control_test_id=plan.control.test_id,
                                     security_test_id=plan.security.test_id,
                                     discovery_command=plan.discovery_command, operation=operation,
                                     witness=request)
        except Exception as exc:
            # A refused request (bad ids or patch) dispatched nothing; it is recorded, never retried.
            failure = exc
        executions.append(FrozenExecution(revision, operation, observed, failure))
    done = {"identification": identification, "plan": plan, "patch": patch, "observation_plan": expected,
            "executions": tuple(executions)}
    problems = []
    for e in executions:
        if e.observed is None:
            problems.append(f"{e.revision} run refused: {e.failure}")
        elif e.observed.operation != str(e.operation) or e.observed.patch_sha256 != frozen.sha256:
            problems.append(f"{e.revision} runner returned another operation or patch")
        elif (e.observed.workspace is not None
              and e.observed.workspace.source.sha256 != case.revision_sources[e.revision]):
            problems.append(f"{e.revision} workspace source is not the {e.revision} revision")
    if problems:
        return stop("execution", "; ".join(problems)[:2048], **done)

    identity = case.environment_identity
    runs = {e.revision: (e.observed,) for e in executions}
    witnesses = {e.revision: (witness_evidence(e.observed.witness, request, plan.security.test_id) if request else
                              WitnessEvidence(None, None, "no witness was requested or captured for this run"))
                 for e in executions}
    done["witnesses"] = tuple(witnesses.values())

    def gate_run(revision):
        found = witnesses[revision]
        return run_evidence(runs[revision][0], environment=identity, witness=found.witness,
                            sandbox_events=found.sandbox_events)
    evidence = AssessmentEvidence(plan=expected, baseline=(gate_run("baseline"),), candidate=(gate_run("candidate"),))
    gate = assess(evidence)
    limitations = UNOBSERVED + unrequested + tuple(f"{revision} witness not admitted: {found.reason}"
                                     for revision, found in witnesses.items() if found.witness is None) + tuple(
        f"{e.revision} workspace cleanup {e.observed.cleanup}" for e in executions if e.observed.cleanup != "confirmed")
    try:
        assessment_input = AssessmentInput(scope=issue.scope, evidence=evidence,
                                           items=evidence_items(expected, patch, identity, runs, admitted={
                                               revision for revision, found in witnesses.items()
                                               if found.witness is not None}))
    except ValueError as exc:
        return stop("assessment", f"assessment input refused: {exc}"[:2048], gate=gate, limitations=limitations,
                    **done)
    assessment = await _stage("assessment", assessment_input)
    if not isinstance(assessment, EvidenceAssessment):
        return stop("assessment", failure_of("assessment"), gate=gate, limitations=limitations, **done)
    return DirectRun(stopped_at=None, reason="complete", attempts=tuple(attempts), gate=gate, assessment=assessment,
                     limitations=limitations, **done)
