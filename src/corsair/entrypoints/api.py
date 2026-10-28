"""Typed Python API over native Temporal workflows; no HTTP server or agent duplication."""

from datetime import timedelta
from typing import Never, overload

from pydantic import TypeAdapter
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from corsair.contracts import (
    BatchItem,
    BatchRequest,
    Identifier,
    InvestigationRequest,
    InvestigationResult,
)
from corsair.contracts.execution import ExecutionRequest, ExecutionResult
from corsair.contracts.intake import IntakeRequest, IntakeResult, IntakeStart
from corsair.contracts.pipeline import IssueInvestigationRequest, IssueInvestigationResult
from corsair.settings import Settings
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.execution import ExecutionWorkflow
from corsair.workflows.intake import IntakeWorkflow
from corsair.workflows.investigation import InvestigationWorkflow
from corsair.workflows.pipeline import IssueInvestigationWorkflow


async def _start_legacy_investigation(
    client: Client, request: InvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[InvestigationWorkflow, InvestigationResult]:
    """Submit one bounded durable investigation, refusing duplicate identities."""
    identity = TypeAdapter(Identifier).validate_python(run_id)
    return await client.start_workflow(
        InvestigationWorkflow.run,
        request,
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.budget.max_elapsed_seconds + 120),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_evaluation(
    client: Client, request: BatchRequest, settings: Settings
) -> WorkflowHandle[EvaluationWorkflow, list[BatchItem]]:
    """Submit a finite batch; oracle labels and scoring never enter workflow input."""
    return await client.start_workflow(
        EvaluationWorkflow.run,
        request,
        id=request.batch_id,
        task_queue=settings.task_queue,
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_intake(
    client: Client, request: "IntakeRequest", settings: Settings, *, run_id: str
) -> "WorkflowHandle[IntakeWorkflow, IntakeResult]":
    """Start one finite intake workflow without starting an investigation."""
    identity = TypeAdapter(Identifier).validate_python(run_id)
    return await client.start_workflow(
        IntakeWorkflow.run,
        IntakeStart(run_id=identity, request=request),
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.budget.max_elapsed_seconds + 120),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_execution(
    client: Client, request: ExecutionRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[ExecutionWorkflow, ExecutionResult]:
    """Start a new recipe-free investigation under its separate v3 workflow identity."""
    from corsair.contracts.execution import ExecutionRequest
    from corsair.workflows.execution import ExecutionWorkflow

    identity = TypeAdapter(Identifier).validate_python(run_id)
    if len(identity) > 60:
        raise ValueError("run identity must leave space for execution operation suffixes")
    request = ExecutionRequest.model_validate(request.model_dump())
    return await client.start_workflow(
        ExecutionWorkflow.run,
        request,
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.budget.max_elapsed_seconds + 120),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_issue_investigation(
    client: Client, request: IssueInvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[IssueInvestigationWorkflow, IssueInvestigationResult]:
    """Start the intake-gated normal investigation path."""
    identity = TypeAdapter(Identifier).validate_python(run_id)
    if len(identity) > 60:
        raise ValueError("run identity must leave space for operation suffixes")
    request = IssueInvestigationRequest.model_validate(request.model_dump())
    return await client.start_workflow(
        IssueInvestigationWorkflow.run,
        request,
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.intake.budget.max_elapsed_seconds + 180),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


@overload
async def start_investigation(
    client: Client, request: IssueInvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[IssueInvestigationWorkflow, IssueInvestigationResult]: ...


@overload
async def start_investigation(
    client: Client, request: ExecutionRequest, settings: Settings, *, run_id: str
) -> Never: ...


@overload
async def start_investigation(
    client: Client, request: InvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[InvestigationWorkflow, InvestigationResult]: ...


async def start_investigation(
    client: Client,
    request: IssueInvestigationRequest | ExecutionRequest | InvestigationRequest,
    settings: Settings,
    *,
    run_id: str,
) -> (
    WorkflowHandle[IssueInvestigationWorkflow, IssueInvestigationResult]
    | WorkflowHandle[InvestigationWorkflow, InvestigationResult]
):
    """Start intake first; historical request objects retain explicit legacy diagnostics."""
    if isinstance(request, IssueInvestigationRequest):
        return await start_issue_investigation(client, request, settings, run_id=run_id)
    if isinstance(request, ExecutionRequest):
        raise ValueError("direct execution requires explicit start_execution")
    return await _start_legacy_investigation(client, request, settings, run_id=run_id)
