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
from corsair.settings import Settings
from corsair.workflows.evaluation import EvaluationWorkflow
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
