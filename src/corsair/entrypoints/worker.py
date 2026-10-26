"""Standard Temporal SDK composition, with no alternate scheduler or agent loop."""

import asyncio
import signal
from datetime import timedelta

from temporalio.worker import Worker

from corsair.adapters.inference.adk import AdkInference
from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.adapters.temporal.client import connect
from corsair.observability.logging import LifecycleLoggingInterceptor, event
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.workflows.evaluation import EvaluationWorkflow
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
        async with Worker(
            client,
            task_queue=settings.task_queue,
            workflows=[InvestigationWorkflow, EvaluationWorkflow],
            activities=activities.registered(),
            max_concurrent_activities=4,
            interceptors=[LifecycleLoggingInterceptor()],
            graceful_shutdown_timeout=timedelta(seconds=45),
        ):
            event(
                "worker.ready",
                namespace=settings.temporal_namespace,
                task_queue=settings.task_queue,
            )
            try:
                await stopped.wait()
            finally:
                event("worker.stopping", task_queue=settings.task_queue)
        event("worker.stopped", task_queue=settings.task_queue)
    finally:
        if signal_installed:
            loop.remove_signal_handler(signal.SIGTERM)
