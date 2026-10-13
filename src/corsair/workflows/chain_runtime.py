"""Worker-side configuration, typed boundary records and the revision activity of the durable chain.

Agents bind their durability (and so their activities and admitted models) when built, while workflow
classes must be importable at module level for the sandbox. The worker process therefore calls
``configure_chain`` once with the operator's models, runners, activity config and budget ceiling
before it builds a worker; ``corsair.workflows.chain`` imports this module through the sandbox
pass-through, so its workflows read the same configuration. Only one configuration exists per
process: configuring again replaces it for workers built afterwards.

Activity names are frozen replay contracts.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability, TemporalRunContext
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage
from temporalio import activity
from temporalio.exceptions import ActivityError, ApplicationError, ChildWorkflowError, FailureError
from temporalio.workflow import ActivityConfig

from corsair.agents.evidence_assessment.contracts import EvidenceAssessment
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.test_authoring.contracts import AuthoringResult, TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.tools import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.contracts import ReadyTestPlan, TestPlan
from corsair.composition.direct import (
    AGENTS, AgentStage, CompositionBudget, DirectRun, FixtureCase, Purpose, RecordedFailure, Runners, Stage,
)
from corsair.core.disposition import GateResult, ObservationPlan
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun

I = TypeVar("I")
O = TypeVar("O")
STAGES: tuple[AgentStage, ...] = ("identification", "planning", "authoring", "assessment")
# Native bytes (patch files, receipt output) cross as base64 so non-UTF-8 output survives the payload.
BYTES = ConfigDict(frozen=True, ser_json_bytes="base64", val_json_bytes="base64")


@dataclass(frozen=True)
class FailureRecord:
    kind: str
    message: str


@dataclass(frozen=True)
class StageKeys:
    """The admitted model key each stage runs with; models themselves stay registered on the worker."""
    identification: str
    planning: str
    authoring: str
    assessment: str


@dataclass(frozen=True)
class StageRequest(Generic[I]):
    inputs: I
    model_key: str
    budget: CompositionBudget


@dataclass(frozen=True)
class StageRecord(Generic[O]):
    output: O | None
    usage: RunUsage
    messages: tuple[ModelMessage, ...]
    failure: FailureRecord | None


class RevisionRequest(BaseModel):
    model_config = BYTES
    revision: Literal["baseline", "candidate"]
    patch: ApprovedPatch
    control_test_id: str
    security_test_id: str
    discovery_command: tuple[str, ...]
    operation: UUID


class RevisionRun(BaseModel):
    model_config = BYTES
    observed: NativeTestRun


@dataclass(frozen=True)
class ChainRequest:
    case: FixtureCase
    models: StageKeys
    budget: CompositionBudget


StageOutput = IssueIdentification | TestPlan | AuthoringResult | EvidenceAssessment


@dataclass(frozen=True)
class AttemptRecord:
    stage: AgentStage
    output: StageOutput | None
    usage: RunUsage | None
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: FailureRecord | None


class ExecutionRecord(BaseModel):
    model_config = BYTES
    revision: Literal["baseline", "candidate"]
    operation: UUID
    observed: NativeTestRun | None
    failure: FailureRecord | None


@dataclass(frozen=True)
class ChainResult:
    """``DirectRun`` as typed records; ``elapsed_seconds`` is workflow time and ``usage`` None when not returned."""
    stopped_at: Stage | None
    reason: str
    attempts: tuple[AttemptRecord, ...]
    identification: IssueIdentification | None = None
    plan: ReadyTestPlan | None = None
    patch: TestPatch | None = None
    observation_plan: ObservationPlan | None = None
    executions: tuple[ExecutionRecord, ...] = ()
    gate: GateResult | None = None
    assessment: EvidenceAssessment | None = None
    limitations: tuple[str, ...] = ()


def failure_record(failure: BaseException) -> FailureRecord:
    """The innermost native cause: an activity or child failure keeps the original type name and message."""
    while isinstance(failure, (ActivityError, ChildWorkflowError)) and failure.cause is not None:
        failure = failure.cause
    if isinstance(failure, RecordedFailure):
        return FailureRecord(failure.kind, str(failure)[:2048])
    kind = failure.type if isinstance(failure, ApplicationError) and failure.type else type(failure).__name__
    return FailureRecord(kind, (failure.message if isinstance(failure, FailureError) else str(failure))[:2048])


def recorded(failure: BaseException) -> RecordedFailure:
    record = failure_record(failure)
    return RecordedFailure(record.kind, record.message)


def chain_result(run: DirectRun) -> ChainResult:
    def failure(value: BaseException | None) -> FailureRecord | None:
        return None if value is None else failure_record(value)
    return ChainResult(
        stopped_at=run.stopped_at, reason=run.reason,
        attempts=tuple(AttemptRecord(a.stage, a.output, a.usage, a.messages, a.elapsed_seconds, failure(a.failure))
                       for a in run.attempts),
        identification=run.identification, plan=run.plan, patch=run.patch, observation_plan=run.observation_plan,
        executions=tuple(ExecutionRecord(revision=e.revision, operation=e.operation, observed=e.observed,
                                         failure=failure(e.failure)) for e in run.executions),
        gate=run.gate, assessment=run.assessment, limitations=run.limitations)


def within(budget: CompositionBudget, ceiling: CompositionBudget) -> bool:
    """Every stage cap at most the operator's; output retries are fixed when the agents are built."""
    caps = ("request_limit", "tool_calls_limit", "total_tokens_limit", "timeout_seconds")
    return (isinstance(budget, CompositionBudget) and budget.dev_runs <= ceiling.dev_runs
            and budget.output_retries == ceiling.output_retries
            and all(getattr(getattr(budget, stage), cap) <= getattr(getattr(ceiling, stage), cap)
                    for stage in STAGES for cap in caps))


@dataclass(frozen=True)
class WorkerRunner:
    """Workflow-side stand-in for a runner: it names a purpose and never runs; the worker resolves it."""
    purpose: Purpose

    def run(self, *args: Any, **kwargs: Any) -> NativeTestRun:
        raise RuntimeError("a runner is resolved on the worker, never run inside a workflow")


@dataclass(frozen=True)
class AuthoringPayload:
    """How ``AuthoringDependencies`` crosses an activity boundary: inputs, budget and the runner's purpose."""
    inputs: TestAuthoringInput
    runner: WorkerRunner
    budget: AuthoringBudget


class AuthoringRunContext(TemporalRunContext[AuthoringDependencies]):
    """Native ``run_context_type`` for the authoring stage.

    The authoring tools rebuild the patch and the development-run count from this run's messages, so
    they are carried; the development runner is resolved on the worker from the operator's ``Runners``.
    """

    @classmethod
    def serialize_run_context(cls, ctx: Any) -> dict[str, Any]:
        return super().serialize_run_context(ctx) | {"messages": ctx.messages}

    @classmethod
    def deserialize_run_context(cls, ctx: dict[str, Any], deps: Any) -> "AuthoringRunContext":
        runtime = configured()
        if runtime is None or not isinstance(deps, AuthoringPayload) or deps.runner.purpose != "development":
            raise UserError("authoring activities need a configured chain worker and development dependencies")
        messages = ModelMessagesTypeAdapter.validate_python(ctx["messages"])
        return cls(**(ctx | {"messages": messages}),
                   deps=AuthoringDependencies(deps.inputs, runtime.runners("development"), deps.budget))


@dataclass(frozen=True)
class ChainRuntime:
    agents: Mapping[AgentStage, Agent[Any, Any]]
    model_keys: frozenset[str]
    runners: Runners
    ceiling: CompositionBudget


_runtime: ChainRuntime | None = None


def configured() -> ChainRuntime | None:
    return _runtime


def _unselected(messages: list[ModelMessage], info: Any) -> ModelResponse:
    raise UserError("a durable chain request must name an admitted model key")


def configure_chain(models: Mapping[str, Model], runners: Runners, *, activity_config: ActivityConfig,
                    ceiling: CompositionBudget = CompositionBudget()) -> ChainRuntime:
    """Build each stage's agent once with native durability over the operator's models, keyed for requests."""
    global _runtime
    if not models or "default" in models or not all(isinstance(model, Model) for model in models.values()):
        raise ValueError("chain models need explicit keys other than 'default' and PydanticAI Model instances")

    def durability(stage: AgentStage) -> TemporalDurability[Any]:
        if stage == "authoring":
            return TemporalDurability(models=models, activity_config=activity_config,
                                      deps_type=AuthoringPayload, run_context_type=AuthoringRunContext)
        return TemporalDurability(models=models, activity_config=activity_config)
    # The default model only answers a request that named no key, which admission never lets through.
    agents = {stage: AGENTS[stage](FunctionModel(_unselected), output_retries=ceiling.output_retries,
                                   durability=durability(stage)) for stage in STAGES}
    _runtime = ChainRuntime(agents, frozenset(models), runners, ceiling)
    return _runtime


@activity.defn(name="corsair.chain.execute_revision")
async def execute_revision(request: RevisionRequest) -> RevisionRun:
    """One frozen revision run on a fresh workspace from the worker's runners; scheduled once, never retried."""
    runtime = configured()
    if runtime is None:
        raise ApplicationError("No chain runtime is configured on this worker", type="AgentConfigurationInvalid",
                               non_retryable=True)
    runner = runtime.runners(request.revision)
    observed = await asyncio.to_thread(
        runner.run, request.patch, control_test_id=request.control_test_id,
        security_test_id=request.security_test_id, discovery_command=request.discovery_command,
        operation=request.operation)
    return RevisionRun(observed=observed)
