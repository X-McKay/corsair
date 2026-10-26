"""Read-only infrastructure diagnostics, not a mock run or model qualification."""

import asyncio
import os
from contextlib import closing
from importlib.metadata import version
from pathlib import Path

import docker
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest

from corsair.adapters.temporal.client import connect
from corsair.entrypoints.terminal import failure_remedy
from corsair.observability.logging import safe_text
from corsair.settings import Settings


def _directory(path: str, *, writable=False) -> str:
    target = Path(path).absolute()
    if not writable:
        if not target.is_dir() or not os.access(target, os.R_OK | os.X_OK):
            raise ValueError("source_root must be a readable directory")
        return "Readable source admission root"
    while not target.exists():
        target = target.parent
    if not target.is_dir() or not os.access(target, os.W_OK | os.X_OK):
        raise ValueError("artifact root or its parent must be writable")
    return "Writable artifact root or parent; no files created"


def _docker(settings: Settings) -> str:
    with closing(docker.from_env(timeout=5)) as client:
        client.ping()
        image = client.images.get(settings.image)
        runtimes = client.info().get("Runtimes", {})
        if settings.runtime not in runtimes:
            raise ValueError(f"configured runtime {settings.runtime} is not registered")
        return f"Daemon reachable; runtime={settings.runtime}; image={image.id}"


def _failed_check(name: str, error: Exception) -> dict:
    """Report a failed dependency with its sanitized error and any fixed remedy."""
    check = {
        "name": name,
        "status": "fail",
        "detail": safe_text(f"{type(error).__name__}: {error}"),
    }
    remedy = failure_remedy(error)
    return check if remedy is None else {**check, "remedy": remedy}


async def diagnose(settings: Settings) -> dict:
    checks = []
    for name, operation in (
        ("source_root", lambda: _directory(settings.source_root)),
        ("artifact_root", lambda: _directory(settings.artifact_root, writable=True)),
        ("docker", lambda: _docker(settings)),
    ):
        try:
            detail = await asyncio.to_thread(operation)
            checks.append({"name": name, "status": "pass", "detail": detail})
        except Exception as error:
            checks.append(_failed_check(name, error))
    try:
        async with asyncio.timeout(8):
            client = await connect(settings)
            await client.workflow_service.describe_namespace(
                DescribeNamespaceRequest(namespace=settings.temporal_namespace)
            )
            checks.append(
                {
                    "name": "temporal",
                    "status": "pass",
                    "detail": f"Namespace {settings.temporal_namespace} is accessible",
                }
            )
            queues = await asyncio.gather(
                *[
                    client.workflow_service.describe_task_queue(
                        DescribeTaskQueueRequest(
                            namespace=settings.temporal_namespace,
                            task_queue=TaskQueue(name=settings.task_queue),
                            task_queue_type=kind,
                        )
                    )
                    for kind in (
                        TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
                        TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
                    )
                ]
            )
            available = all(response.pollers for response in queues)
            checks.append(
                {
                    "name": "worker_pollers",
                    "status": "pass" if available else "warn",
                    "detail": "Workflow and activity pollers reported"
                    if available
                    else "Start corsair worker; workflow/activity pollers not both reported",
                }
            )
    except Exception as error:
        checks.append(_failed_check("temporal", error))
    return {
        "ready": all(check["status"] == "pass" for check in checks),
        "checks": checks,
        "versions": {
            name: version(name) for name in ("google-adk", "temporalio", "docker", "rich")
        },
        "qualification": "Infrastructure checks only. Poller presence is not an execution test. "
        "Model credentials, provider policy, native evidence and accuracy were not tested.",
    }
