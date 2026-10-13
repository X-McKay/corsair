"""Direct-mode E2E-0 composition: identification, planning, authoring, frozen execution, assessment, gates.

Each stage reuses its own factory and typed contract; routing is a total match on the previous
stage's status, every abstention stops the run with its reason, and nothing loops between
stages. Environment evidence is operator-supplied (IDEA-0004). The gate verdict is computed
from the frozen evidence whether or not the assessment agent completes.
"""

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.agents.evidence_assessment.agent import assessment_prompt, create_evidence_assessment_agent
from corsair.agents.evidence_assessment.contracts import AssessmentInput, EvidenceAssessment
from corsair.agents.evidence_assessment.tools import AssessmentDependencies
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.issue_analysis.identification import create_issue_identification_agent, identification_prompt
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.issue_analysis.tools import FixtureDependencies
from corsair.agents.source.contracts import Contract
from corsair.agents.test_authoring.agent import authoring_prompt, create_test_authoring_agent
from corsair.agents.test_authoring.contracts import TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.tools import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.agent import PlanningDependencies, create_test_planning_agent, planning_prompt
from corsair.agents.test_planning.contracts import EnvironmentEvidence, ReadyTestPlan, TestPlanningInput
from corsair.core.disposition import AssessmentEvidence, EnvironmentIdentity, GateResult, ObservationPlan, assess
from corsair.nodes.witness import WitnessEvidence, witness_evidence
from corsair.ports.test_runner import NativeTestRun, TestRunner

from .evidence import evidence_items, freeze, observation_plan, run_evidence, witness_request

Stage = Literal["identification", "planning", "authoring", "execution", "assessment"]
Purpose = Literal["development", "baseline", "candidate"]


class StageBudget(Contract):
    """Operator-owned per-stage caps; the provider configuration owns the response cap."""
    request_limit: int = Field(strict=True, gt=0, le=24)
    tool_calls_limit: int = Field(strict=True, ge=0, le=24)
    total_tokens_limit: int = Field(strict=True, gt=0, le=262144)
    timeout_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class CompositionBudget(Contract):
    identification: StageBudget = StageBudget(request_limit=6, tool_calls_limit=4, total_tokens_limit=64000,
                                              timeout_seconds=300)
    planning: StageBudget = StageBudget(request_limit=10, tool_calls_limit=8, total_tokens_limit=96000,
                                        timeout_seconds=600)
    authoring: StageBudget = StageBudget(request_limit=12, tool_calls_limit=10, total_tokens_limit=128000,
                                         timeout_seconds=900)
    assessment: StageBudget = StageBudget(request_limit=12, tool_calls_limit=10, total_tokens_limit=128000,
                                          timeout_seconds=600)
    dev_runs: int = Field(default=3, strict=True, ge=1, le=5)
    output_retries: int = Field(default=1, strict=True, ge=0, le=1)


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


@dataclass(frozen=True)
class StageAttempt:
    stage: Stage
    output: Any
    usage: RunUsage
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: BaseException | None


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


async def _invoke(attempts: list[StageAttempt], stage: Stage, agent: Agent[Any, Any], prompt: str, deps: Any,
                  budget: StageBudget) -> Any:
    usage, messages, output, failure = RunUsage(), [], None, None
    started = perf_counter()
    try:
        with capture_run_messages() as messages:
            async with asyncio.timeout(budget.timeout_seconds):
                output = (await agent.run(prompt, deps=deps, usage=usage, usage_limits=budget.usage_limits())).output
    except Exception as exc:
        failure = exc
    finally:
        attempts.append(StageAttempt(stage, output, usage, tuple(messages), perf_counter() - started, failure))
    return output


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
    attempts: list[StageAttempt] = []
    issue, environment = case.issue, case.environment

    def stop(stage: Stage, reason: str, **values) -> DirectRun:
        return DirectRun(stopped_at=stage, reason=reason, attempts=tuple(attempts), **values)

    def failure_of(stage: Stage) -> str:
        failed = attempts[-1].failure
        return f"{stage} produced no output: {type(failed).__name__}: {failed}"[:2048]

    identification = await _invoke(
        attempts, "identification", create_issue_identification_agent(models.identification,
                                                                      output_retries=budget.output_retries),
        identification_prompt(issue), FixtureDependencies(issue), budget.identification)
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
    plan = await _invoke(
        attempts, "planning", create_test_planning_agent(models.planning, output_retries=budget.output_retries),
        planning_prompt(planning_input), PlanningDependencies(planning_input), budget.planning)
    if plan is None:
        return stop("planning", failure_of("planning"), identification=identification)
    if not isinstance(plan, ReadyTestPlan):
        return stop("planning", f"plan unsupported: {plan.missing_capability}", identification=identification)

    try:
        authoring_input = TestAuthoringInput(plan=plan, source_files=issue.source_files, environment=environment)
    except ValueError as exc:
        return stop("authoring", f"authoring input refused: {exc}"[:2048], identification=identification, plan=plan)
    patch = await _invoke(
        attempts, "authoring", create_test_authoring_agent(models.authoring, output_retries=budget.output_retries),
        authoring_prompt(authoring_input),
        AuthoringDependencies(authoring_input, runners("development"), AuthoringBudget(dev_runs=budget.dev_runs)),
        budget.authoring)
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
        request, unrequested = witness_request(identification), ()
    except ValueError as exc:
        # The identified symbol or path cannot address a probe target: run without one and say so.
        request, unrequested = None, (f"no witness requested: {exc}"[:512],)
    for revision in ("baseline", "candidate"):
        operation, observed, failure = uuid4(), None, None
        try:
            observed = runners(revision).run(frozen, control_test_id=plan.control.test_id,
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
    assessment = await _invoke(
        attempts, "assessment",
        create_evidence_assessment_agent(models.assessment, output_retries=budget.output_retries),
        assessment_prompt(assessment_input), AssessmentDependencies(assessment_input), budget.assessment)
    if not isinstance(assessment, EvidenceAssessment):
        return stop("assessment", failure_of("assessment"), gate=gate, limitations=limitations, **done)
    return DirectRun(stopped_at=None, reason="complete", attempts=tuple(attempts), gate=gate, assessment=assessment,
                     limitations=limitations, **done)
