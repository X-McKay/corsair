"""Typed Python API over native Temporal workflows; no HTTP server or agent duplication."""

from datetime import timedelta

from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from corsair.contracts import (
    BatchItem,
    BatchRequest,
    InvestigationRequest,
    InvestigationResult,
    validate_root_identity,
)
from corsair.contracts.intake_agent import IntakeRequest, IntakeResult
from corsair.contracts.intake_pipeline import IntakeInvestigationRequest, IntakeInvestigationResult
from corsair.policies.time_bounds import investigation_execution_seconds
from corsair.settings import Settings
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.intake import IntakeWorkflow
from corsair.workflows.intake_pipeline import IntakeInvestigationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow


async def start_investigation(
    client: Client, request: InvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[InvestigationWorkflow, InvestigationResult]:
    """Submit one bounded durable investigation, refusing duplicate identities.

    The root identity is validated with operation-suffix headroom so an over-long
    id is rejected here, before any producer call, rather than failing later when
    an evidence operation suffix would overflow the Identifier bound.
    """
    identity = validate_root_identity(run_id)
    return await client.start_workflow(
        InvestigationWorkflow.run,
        request,
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=investigation_execution_seconds(request.budget)),
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
    client: Client, request: IntakeRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[IntakeWorkflow, IntakeResult]:
    """Run standalone agentic intake; existing scanner dry-run stays independent."""
    from corsair.contracts.intake_agent import IntakeStart
    from corsair.workflows.intake import IntakeWorkflow

    identity = validate_root_identity(run_id)
    return await client.start_workflow(
        IntakeWorkflow.run,
        IntakeStart(run_id=identity, request=request),
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.budget.max_elapsed_seconds + 120),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_intake_investigation(
    client: Client, request: IntakeInvestigationRequest, settings: Settings, *, run_id: str
) -> WorkflowHandle[IntakeInvestigationWorkflow, IntakeInvestigationResult]:
    """Run intake, then main's existing trusted investigation only when supported."""
    from corsair.workflows.intake_pipeline import IntakeInvestigationWorkflow

    identity = validate_root_identity(run_id)
    return await client.start_workflow(
        IntakeInvestigationWorkflow.run,
        request,
        id=identity,
        task_queue=settings.task_queue,
        execution_timeout=timedelta(seconds=request.intake.budget.max_elapsed_seconds + 240),
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
