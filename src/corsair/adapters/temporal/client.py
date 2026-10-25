"""Temporal client-only operations; no worker or ADK composition imports."""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter

from corsair.settings import Settings


async def connect(settings: Settings) -> Client:
    """Create one native SDK connection for the current command/event loop."""
    async with asyncio.timeout(10):
        return await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            data_converter=pydantic_data_converter,
        )


async def wait_for_result[T](handle: WorkflowHandle[Any, T]) -> T:
    """Observe SDK closure without leaving a cancelled history long-poll at process exit.

    This is local observation only. It never cancels or schedules durable work.
    """
    deadline = timedelta(seconds=5)
    while (await handle.describe(rpc_timeout=deadline)).status == WorkflowExecutionStatus.RUNNING:
        await asyncio.sleep(1)
    return await handle.result(rpc_timeout=deadline)
