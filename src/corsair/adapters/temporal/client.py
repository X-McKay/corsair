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


async def query_intake_progress(client: Client, handle: WorkflowHandle) -> dict:
    """Observe parent and active child metadata without changing durable execution."""
    timeout = timedelta(milliseconds=750)
    parent = dict(await handle.query("status", rpc_timeout=timeout))
    child_id = parent.get("investigation_run_id")
    if parent.get("phase") != "investigation" or not isinstance(child_id, str):
        return parent
    parent["parent_phase"] = parent["phase"]
    try:
        child = await client.get_workflow_handle(child_id).query("status", rpc_timeout=timeout)
    except Exception:
        # Keep known parent state; a temporarily unavailable child is not a failed run.
        parent["child_status_unavailable"] = True
        return parent
    for key in ("phase", "session", "round", "max_sessions", "max_rounds", "gate", "timeline"):
        if key in child:
            parent[key] = child[key]
    return parent
