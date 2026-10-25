"""Standard Temporal SDK composition, with no alternate scheduler or agent loop."""

import asyncio
import signal
from datetime import timedelta

from temporalio.worker import Worker

from corsair.observability.logging import LifecycleLoggingInterceptor, event
from corsair.runtime.client import connect
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow


async def run_worker(settings: Settings) -> None:
    event(
        "worker.connecting", namespace=settings.temporal_namespace, task_queue=settings.task_queue
    )
    client = await connect(settings)
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
            activities=Activities(settings).registered(),
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
