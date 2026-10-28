"""Standard Temporal SDK composition, with no alternate scheduler or agent loop."""

import asyncio
import signal
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from corsair.adapters.inference.adk import AdkInference
from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.adapters.temporal.client import connect
from corsair.observability.lifecycle import LifecycleLoggingInterceptor
from corsair.observability.logging import event
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.steps.intake_agent import IntakeActivities
from corsair.steps.intake_handoff import IntakePipelineActivities
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.intake import IntakeWorkflow
from corsair.workflows.intake_pipeline import IntakeInvestigationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow


def compose_worker_activities(settings: Settings) -> Activities:
    """Construct the worker's real activity adapters around one artifact store."""

    store = ArtifactStore(settings.artifact_root)
    return Activities(
        settings,
        store=store,
        inference=AdkInference(settings, store),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=DockerSandbox(settings, store=store),
    )


def compose_worker(client: Client, settings: Settings, activities: Activities) -> Worker:
    """Construct the one Temporal worker, with task slots taken from settings."""

    return Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[
            InvestigationWorkflow,
            EvaluationWorkflow,
            IntakeWorkflow,
            IntakeInvestigationWorkflow,
        ],
        activities=[
            *activities.registered(),
            *IntakeActivities(settings, activities.store).registered(),
            *IntakePipelineActivities(activities.store).registered(),
        ],
        max_concurrent_activities=settings.max_concurrent_activities,
        max_concurrent_workflow_tasks=settings.max_concurrent_workflow_tasks,
        interceptors=[LifecycleLoggingInterceptor()],
        graceful_shutdown_timeout=timedelta(seconds=45),
    )


async def run_worker(settings: Settings) -> None:
    event(
        "worker.connecting", namespace=settings.temporal_namespace, task_queue=settings.task_queue
    )
    client = await connect(settings)
    activities = compose_worker_activities(settings)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, stopped.set)
    except (NotImplementedError, RuntimeError, ValueError):
        signal_installed = False  # Windows/non-main-thread loops do not support Unix signals.
    else:
        signal_installed = True
    try:
        async with compose_worker(client, settings, activities):
            event(
                "worker.ready",
                namespace=settings.temporal_namespace,
                task_queue=settings.task_queue,
                max_concurrent_activities=settings.max_concurrent_activities,
                max_concurrent_workflow_tasks=settings.max_concurrent_workflow_tasks,
            )
            try:
                await stopped.wait()
            finally:
                event("worker.stopping", task_queue=settings.task_queue)
        event("worker.stopped", task_queue=settings.task_queue)
    finally:
        if signal_installed:
            loop.remove_signal_handler(signal.SIGTERM)
