"""Standard Temporal SDK composition, with no alternate scheduler or agent loop."""

import asyncio

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.workflows.evaluation import EvaluationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow


async def connect(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )


async def run_worker(settings: Settings) -> None:
    client = await connect(settings)
    async with Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[InvestigationWorkflow, EvaluationWorkflow],
        activities=Activities(settings).registered(),
        max_concurrent_activities=4,
    ):
        await asyncio.Event().wait()
