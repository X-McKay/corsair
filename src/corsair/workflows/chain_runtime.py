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
from contextlib import contextmanager
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter
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

from corsair.agents.environment.contracts import (
    BlockedEnvironment, EnvironmentInput, ReadyEnvironment, UnsupportedEnvironment,
)
from corsair.agents.evidence_assessment.contracts import EvidenceAssessment
from corsair.agents.issue_analysis.contracts import SourceFile
from corsair.agents.issue_identification.contracts import IssueIdentification
from corsair.composition.assembly import FrozenTestPatch
from corsair.agents.test_authoring.contracts import AuthoringResult, TestAuthoringInput, TestPatch
from corsair.agents.probe_authoring.contracts import Drafted, Blocked
from corsair.agents.probe_authoring.dependencies import SpecialistDependencies
from corsair.agents.test_authoring.dependencies import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_planning.contracts import ReadyTestPlan, TestPlan
from corsair.composition.direct import (
    AGENTS, NO_CATALOG, NO_PREPARATION, AgentStage, BudgetExhausted, CompositionBudget, DirectRun, FixtureCase,
    Preparation, PreparationMissing, Purpose, RecordedFailure, Runners, RuntimeCatalogMissing, Stage, StageLimits,
    cap_reached, prepare_environment, stage_output_retries,
)
from corsair.core.disposition import GateResult, ObservationPlan
from corsair.nodes.runtime.contracts import RuntimeInputs, RuntimeOutcome
from corsair.nodes.runtime.environment import RuntimeCatalog, select_runtime as select_from_catalog
from corsair.nodes.witness import WitnessEvidence
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun, WitnessRequest

I = TypeVar("I")
O = TypeVar("O")
STAGES: tuple[AgentStage, ...] = ("identification", "planning", "control_authoring", "exploit_authoring", "assessment")
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
    control_authoring: str
    exploit_authoring: str
    assessment: str
    # Only a case with setup source needs it; without it that case stops at `environment` (SPEC-0068).
    environment: str | None = None


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
    witness: WitnessRequest | None = None


class RevisionRun(BaseModel):
    model_config = BYTES
    observed: NativeTestRun


@dataclass(frozen=True)
class ChainRequest:
    case: FixtureCase
    models: StageKeys
    budget: CompositionBudget


StageOutput = (ReadyEnvironment | BlockedEnvironment | UnsupportedEnvironment | IssueIdentification | TestPlan
               | Drafted | Blocked | EvidenceAssessment)


@dataclass(frozen=True)
class EnvironmentRequest:
    inputs: EnvironmentInput
    model_key: str
    budget: CompositionBudget


@dataclass(frozen=True)
class EnvironmentRecord:
    """What the environment activity observed; limits are derived again in the workflow from the same inputs."""
    output: ReadyEnvironment | BlockedEnvironment | UnsupportedEnvironment | None
    usage: RunUsage | None
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: FailureRecord | None
    exhausted: BudgetExhausted | None
    cleanup: Literal["confirmed", "unconfirmed"] | None
    messages_omitted: bool = False
    baseline_source: SourceFile | None = None
    baseline_refusal: str | None = None


@dataclass(frozen=True)
class AttemptRecord:
    stage: AgentStage
    output: StageOutput | None
    usage: RunUsage | None
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: FailureRecord | None
    limits: StageLimits | None = None
    exhausted: BudgetExhausted | None = None
    cleanup: Literal["confirmed", "unconfirmed"] | None = None
    messages_omitted: bool = False
    baseline_source: SourceFile | None = None
    baseline_refusal: str | None = None

    @property
    def tool_cap_reached(self) -> bool:
        return cap_reached(self.limits, self.usage)


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
    patch: TestPatch | FrozenTestPatch | None = None
    observation_plan: ObservationPlan | None = None
    executions: tuple[ExecutionRecord, ...] = ()
    gate: GateResult | None = None
    assessment: EvidenceAssessment | None = None
    validity_review: EvidenceAssessment | None = None
    witnesses: tuple[WitnessEvidence, ...] = ()
    limitations: tuple[str, ...] = ()
    runtime: RuntimeOutcome | None = None
    environment: ReadyEnvironment | BlockedEnvironment | UnsupportedEnvironment | None = None


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
        attempts=tuple(AttemptRecord(a.stage, a.output, a.usage, a.messages, a.elapsed_seconds, failure(a.failure),
                                     a.limits, a.exhausted, a.cleanup, a.messages_omitted,
                                     a.baseline_source, a.baseline_refusal) for a in run.attempts),
        identification=run.identification, plan=run.plan, patch=run.patch, observation_plan=run.observation_plan,
        executions=tuple(ExecutionRecord(revision=e.revision, operation=e.operation, observed=e.observed,
                                         failure=failure(e.failure)) for e in run.executions),
        gate=run.gate, assessment=run.assessment, validity_review=run.validity_review, witnesses=run.witnesses,
        limitations=run.limitations, runtime=run.runtime, environment=run.environment)


def within(budget: CompositionBudget, ceiling: CompositionBudget) -> bool:
    """Every stage cap and derivation term at most the operator's; output retries are fixed when the agents are built."""
    caps = ("request_limit", "tool_calls_limit", "total_tokens_limit", "timeout_seconds", "slack_tool_calls",
            "tokens_per_request")
    return (isinstance(budget, CompositionBudget) and budget.dev_runs <= ceiling.dev_runs
            and budget.admission_refusals <= ceiling.admission_refusals
            and budget.setup_commands <= ceiling.setup_commands
            and budget.output_retries == ceiling.output_retries
            and budget.author_output_retries == ceiling.author_output_retries
            and all(getattr(getattr(budget, stage), cap) <= getattr(getattr(ceiling, stage), cap)
                    for stage in STAGES + ("environment",) for cap in caps))


@dataclass(frozen=True)
class WorkerRunner:
    """Workflow-side stand-in for a runner: it names a purpose and never runs; the worker resolves it."""
    purpose: Purpose

    def run(self, *args: Any, **kwargs: Any) -> NativeTestRun:
        raise RuntimeError("a runner is resolved on the worker, never run inside a workflow")


@dataclass(frozen=True)
class AuthoringPayload:
    """Historical combined-author compatibility only; not registered by the production chain. How ``AuthoringDependencies`` crosses an activity boundary: inputs, budget and the runner's purpose."""
    inputs: TestAuthoringInput
    runner: WorkerRunner
    budget: AuthoringBudget


class AuthoringRunContext(TemporalRunContext[AuthoringDependencies]):
    """Historical combined-author ``run_context_type``; not a production chain stage.

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


class SpecialistRunContext(TemporalRunContext[SpecialistDependencies]):
    """Own write calls cross native activities; no peer draft or execution port is carried."""
    @classmethod
    def serialize_run_context(cls, ctx: Any) -> dict[str, Any]:
        return super().serialize_run_context(ctx) | {"messages": ctx.messages}

    @classmethod
    def deserialize_run_context(cls, ctx: dict[str, Any], deps: Any) -> "SpecialistRunContext":
        messages = ModelMessagesTypeAdapter.validate_python(ctx["messages"])
        return cls(**(ctx | {"messages": messages}), deps=deps)


@dataclass(frozen=True)
class ChainRuntime:
    agents: Mapping[AgentStage, Agent[Any, Any]]
    model_keys: frozenset[str]
    runners: Runners
    ceiling: CompositionBudget
    catalog: RuntimeCatalog | None = None
    # The environment stage runs its agent inside one activity, so its model is resolved here by key.
    models: Mapping[str, Model] = field(default_factory=dict)
    preparation: Preparation | None = None


_runtime: ChainRuntime | None = None
# Workers resolve agents and runners from the one process configuration, so it is never replaced under a live worker.
_serving = False


def configured() -> ChainRuntime | None:
    return _runtime


@contextmanager
def serving():
    """Hold the configuration for one worker's lifetime; another configuration is refused until it closes."""
    global _serving
    if _serving:
        raise RuntimeError("a chain worker in this process is already serving its configuration")
    _serving = True
    try:
        yield
    finally:
        _serving = False


def _unselected(messages: list[ModelMessage], info: Any) -> ModelResponse:
    raise UserError("a durable chain request must name an admitted model key")


def configure_chain(models: Mapping[str, Model], runners: Runners, *, activity_config: ActivityConfig,
                    ceiling: CompositionBudget = CompositionBudget(),
                    catalog: RuntimeCatalog | None = None, preparation: Preparation | None = None) -> ChainRuntime:
    """Build each stage's agent once with native durability over the operator's models, keyed for requests.

    ``catalog`` (runtime matrix and prepared images) answers the runtime stage of cases that carry build files;
    ``preparation`` prepares the environment stage's sandbox for cases that carry setup source."""
    global _runtime
    if _serving:
        raise RuntimeError("the chain configuration is held by a serving worker; it cannot be replaced")
    if not models or "default" in models or not all(isinstance(model, Model) for model in models.values()):
        raise ValueError("chain models need explicit keys other than 'default' and PydanticAI Model instances")

    def durability(stage: AgentStage) -> TemporalDurability[Any]:
        if stage in ("control_authoring", "exploit_authoring"):
            return TemporalDurability(models=models, activity_config=activity_config,
                                      run_context_type=SpecialistRunContext)
        return TemporalDurability(models=models, activity_config=activity_config)
    # The default model only answers a request that named no key, which admission never lets through.
    agents = {stage: AGENTS[stage](FunctionModel(_unselected), output_retries=stage_output_retries(stage, ceiling),
                                   durability=durability(stage)) for stage in STAGES}
    _runtime = ChainRuntime(agents, frozenset(models), runners, ceiling, catalog, dict(models), preparation)
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
        operation=request.operation, witness=request.witness)
    return RevisionRun(observed=observed)


@activity.defn(name="corsair.chain.select_runtime")
async def select_runtime(inputs: RuntimeInputs) -> RuntimeOutcome:
    """SPEC-0060 runtime stage from the worker's catalog; deterministic, scheduled once."""
    runtime = configured()
    if runtime is None or runtime.catalog is None:
        raise ApplicationError(NO_CATALOG, type=RuntimeCatalogMissing.__name__, non_retryable=True)
    return select_from_catalog(inputs, runtime.catalog)


# Temporal refuses payloads over 2 MB; the environment record keeps half of that.
MAX_RECORD_BYTES = 1 << 20
ENVIRONMENT_RECORD = TypeAdapter(EnvironmentRecord)


@activity.defn(name="corsair.chain.prepare_environment")
async def run_environment(request: EnvironmentRequest) -> EnvironmentRecord:
    """SPEC-0068 environment stage, whole, on the worker that holds the sandbox preparation; scheduled once.

    The agent's setup ledger and the live sandbox stay in this one call (PLAN-0075); its model requests and tool
    calls are not activities of their own."""
    runtime = configured()
    model = runtime and runtime.models.get(request.model_key)
    if runtime is None or runtime.preparation is None or model is None:
        raise ApplicationError(NO_PREPARATION, type=PreparationMissing.__name__, non_retryable=True)
    attempt = await prepare_environment(request.inputs, model, runtime.preparation, request.budget)
    record = EnvironmentRecord(attempt.output, attempt.usage, attempt.messages, attempt.elapsed_seconds,
                               attempt.failure and failure_record(attempt.failure), attempt.exhausted, attempt.cleanup,
                               baseline_source=attempt.baseline_source, baseline_refusal=attempt.baseline_refusal)
    # Model output is bounded by usage, not bytes: the messages give way before the result crosses the payload limit.
    if len(ENVIRONMENT_RECORD.dump_json(record)) > MAX_RECORD_BYTES:
        record = replace(record, messages=(), messages_omitted=True)
    return record
