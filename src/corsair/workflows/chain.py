"""Durable E2E-0 chain: one parent workflow, one child workflow per agent stage, one activity per frozen revision.

Routing is ``corsair.composition.direct.run_chain``, the same code direct mode runs; this module only binds
its ports. Each child runs exactly the agent its factory built with native ``TemporalDurability`` (model
requests and tool calls are activities) under the stage budget's usage limits, with the stage
``timeout_seconds`` as its execution timeout. Operation ids come from ``workflow.uuid4()`` and elapsed time
from workflow time. Admission refusals are non-retryable typed ``ApplicationError``s raised before any
child, activity or model request. Workflow and activity names are frozen replay contracts.

A worker process calls ``configure_chain`` (``chain_runtime``) and then ``chain_worker``; ``run_durable``
does both for an in-process worker and takes the same arguments as ``run_direct``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, ClassVar
from uuid import uuid4

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, ChildWorkflowError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError
from temporalio.workflow import ActivityConfig

with workflow.unsafe.imports_passed_through():
    from pydantic_ai import capture_run_messages
    from pydantic_ai.durable_exec.temporal import AgentPlugin
    from pydantic_ai.exceptions import AgentRunError
    from pydantic_ai.usage import RunUsage
    from temporalio.client import Client
    from temporalio.worker import Worker

    from corsair.agents.evidence_assessment.contracts import AssessmentInput, EvidenceAssessment
    from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
    from corsair.agents.issue_identification.contracts import IssueIdentification
    from corsair.agents.test_authoring.contracts import AuthoringResult, TestAuthoringInput
    from corsair.agents.test_planning.contracts import TestPlan, TestPlanningInput
    from corsair.composition.direct import (
        AgentStage, CompositionBudget, FixtureCase, RecordedFailure, Runners, StageAttempt, StageModels, exhaustion,
        run_chain, stage_call, stage_limits,
    )

    from .chain_runtime import (
        STAGES, ChainRequest, ChainResult, ChainRuntime, RevisionRequest, StageKeys, StageRecord, StageRequest,
        WorkerRunner, chain_result, configure_chain, configured, execute_revision, failure_record, recorded,
        select_runtime, serving, within,
    )
    from corsair.nodes.runtime.contracts import RuntimeInputs, RuntimeOutcome
    from corsair.nodes.runtime.environment import RuntimeCatalog

# Operator-owned: the reviewed host runner bounds each subprocess at 60 s; an OpenShell runner may take longer.
REVISION_TIMEOUT = timedelta(minutes=10)
# Detection and selection read at most 1 MiB of encoded build files in memory.
SELECTION_TIMEOUT = timedelta(minutes=1)
NOT_DURABLE = "The case carries setup source; the environment stage has no durable mode yet (SPEC-0068)"
# Default for ``run_durable``: one attempt per model request or tool call, so nothing is blindly repeated.
ACTIVITY_CONFIG: ActivityConfig = {"start_to_close_timeout": timedelta(minutes=5), "retry_policy": RetryPolicy(maximum_attempts=1)}


def _refusal(kind: str, message: str) -> ApplicationError:
    return ApplicationError(message, type=kind, non_retryable=True)


def _admit(keys: tuple[str, ...], budget: CompositionBudget) -> ChainRuntime:
    runtime = configured()
    if runtime is None or set(runtime.agents) != set(STAGES):
        raise _refusal("AgentConfigurationInvalid", "The chain worker has no configured stage agents")
    if not set(keys) <= runtime.model_keys:
        raise _refusal("ModelKeyNotAdmitted", "Model key is not admitted by this worker configuration")
    if not within(budget, runtime.ceiling):
        raise _refusal("BudgetNotAdmitted", "Requested budget is not within the operator ceiling")
    return runtime


class ChainStage:
    """Runs one stage agent once; a model, tool or usage failure is returned as a record with its messages."""
    stage: ClassVar[AgentStage]

    async def invoke(self, request: StageRequest[Any]) -> StageRecord[Any]:
        runtime = _admit((request.model_key,), request.budget)
        prompt, deps = stage_call(self.stage, request.inputs, request.budget,
                                  WorkerRunner("development") if self.stage == "authoring" else None)
        usage, output, failure = RunUsage(), None, None
        with capture_run_messages() as messages:
            try:
                output = (await runtime.agents[self.stage].run(
                    prompt, model=request.model_key, deps=deps, usage=usage,
                    usage_limits=stage_limits(self.stage, request.inputs, request.budget).usage_limits())).output
            except (AgentRunError, ActivityError) as exc:
                failure = failure_record(exc)
        return StageRecord(output, usage, tuple(messages), failure)


@workflow.defn(name="corsair.chain.Identification")
class IdentificationStage(ChainStage):
    stage = "identification"

    @workflow.run
    async def run(self, request: StageRequest[IssueAnalysisInput]) -> StageRecord[IssueIdentification]:
        return await self.invoke(request)


@workflow.defn(name="corsair.chain.Planning")
class PlanningStage(ChainStage):
    stage = "planning"

    @workflow.run
    async def run(self, request: StageRequest[TestPlanningInput]) -> StageRecord[TestPlan]:
        return await self.invoke(request)


@workflow.defn(name="corsair.chain.Authoring")
class AuthoringStage(ChainStage):
    stage = "authoring"

    @workflow.run
    async def run(self, request: StageRequest[TestAuthoringInput]) -> StageRecord[AuthoringResult]:
        return await self.invoke(request)


@workflow.defn(name="corsair.chain.Assessment")
class AssessmentStage(ChainStage):
    stage = "assessment"

    @workflow.run
    async def run(self, request: StageRequest[AssessmentInput]) -> StageRecord[EvidenceAssessment]:
        return await self.invoke(request)


CHILDREN = {"identification": IdentificationStage, "planning": PlanningStage, "authoring": AuthoringStage,
            "assessment": AssessmentStage}


@workflow.defn(name="corsair.chain.Investigation")
class ChainInvestigation:
    @workflow.run
    async def run(self, request: ChainRequest) -> ChainResult:
        _admit(tuple(getattr(request.models, stage) for stage in STAGES), request.budget)
        parent = workflow.info().workflow_id

        async def invoke(stage: AgentStage, inputs: Any) -> StageAttempt:
            started = workflow.time()
            # Pure derivation from the stage input: the same caps the child enforces.
            limits = stage_limits(stage, inputs, request.budget)
            if stage == "environment":
                # SPEC-0068: the environment stage runs in direct mode only until its durable slice; never the declaration.
                return StageAttempt(stage, None, None, (), 0.0, RecordedFailure(
                    "EnvironmentStageNotDurable", NOT_DURABLE), limits)
            try:
                record = await workflow.execute_child_workflow(
                    CHILDREN[stage].run, StageRequest(inputs, getattr(request.models, stage), request.budget),
                    id=f"{parent}/{stage}", execution_timeout=timedelta(seconds=limits.timeout_seconds))
            except ChildWorkflowError as exc:
                # Timed out or failed without returning: usage and messages were not observed here.
                failure = recorded(exc)
                # Only the child's own execution timeout is the stage deadline.
                return StageAttempt(stage, None, None, (), workflow.time() - started, failure, limits,
                                    exhaustion(stage, limits, failure,
                                               deadline=isinstance(exc.cause, TemporalTimeoutError)))
            failure = record.failure and RecordedFailure(record.failure.kind, record.failure.message)
            return StageAttempt(stage, record.output, record.usage, record.messages, workflow.time() - started,
                                failure, limits, exhaustion(stage, limits, failure))

        async def execute(revision, patch, **run):
            try:
                result = await workflow.execute_activity(
                    execute_revision, RevisionRequest(revision=revision, patch=patch, **run),
                    start_to_close_timeout=REVISION_TIMEOUT, retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError as exc:
                # Failed or unknown delivery: recorded with its native cause, never rescheduled.
                raise recorded(exc) from None
            return result.observed

        async def select(inputs: RuntimeInputs) -> RuntimeOutcome:
            try:
                return await workflow.execute_activity(
                    select_runtime, inputs, start_to_close_timeout=SELECTION_TIMEOUT,
                    retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError as exc:
                raise recorded(exc) from None

        return chain_result(await run_chain(request.case, invoke, execute, select, new_operation=workflow.uuid4))


WORKFLOWS = (ChainInvestigation, IdentificationStage, PlanningStage, AuthoringStage, AssessmentStage)


@asynccontextmanager
async def chain_worker(client: Client, task_queue: str, **options: Any) -> AsyncIterator[Worker]:
    """A running worker for every chain workflow, each stage agent's native activities and the revision activity.

    It holds the process configuration while it runs, so ``configure_chain`` and another chain worker are refused
    until it stops: admission, authoring runners and revision activities never resolve a replaced configuration."""
    runtime = configured()
    if runtime is None:
        raise ValueError("configure_chain must run before a chain worker is built")
    with serving():
        async with Worker(client, task_queue=task_queue, workflows=list(WORKFLOWS), activities=[execute_revision, select_runtime],
                          plugins=[AgentPlugin(agent) for agent in runtime.agents.values()], **options) as worker:
            yield worker


async def run_durable(case: FixtureCase, models: StageModels, runners: Runners,
                      budget: CompositionBudget = CompositionBudget(), *, client: Client,
                      catalog: RuntimeCatalog | None = None,
                      workflow_id: str | None = None, execution_timeout: timedelta | None = None,
                      activity_config: ActivityConfig = ACTIVITY_CONFIG, **worker_options: Any) -> ChainResult:
    """``run_direct``'s arguments under an in-process worker; ``budget`` is also the ceiling. The client needs
    ``PydanticAIPlugin``. The workflow id (default random) names the parent and ``<id>/<stage>`` children."""
    configure_chain({stage: getattr(models, stage) for stage in STAGES}, runners, activity_config=activity_config,
                    ceiling=budget, catalog=catalog)
    identity = workflow_id or f"corsair-chain-{uuid4()}"
    # One configuration per process: an overlapping run_durable is refused rather than served another's models.
    async with chain_worker(client, identity, **worker_options):
        return await client.execute_workflow(ChainInvestigation.run, ChainRequest(case, StageKeys(*STAGES), budget),
                                             id=identity, task_queue=identity, execution_timeout=execution_timeout)
