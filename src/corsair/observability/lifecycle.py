"""Native Temporal activity lifecycle logging; never log agent content."""

import asyncio
import logging
import time
from typing import Any

from temporalio import activity
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor
from typing_extensions import TypedDict

from corsair.observability.logging import event


class _ActivityIdentity(TypedDict, closed=True):
    run_id: str | None
    activity: str
    attempt: int


class _ActivityLogging(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        info = activity.info()
        identity: _ActivityIdentity = {
            "run_id": info.workflow_id,
            "activity": info.activity_type,
            "attempt": info.attempt,
        }
        started = time.monotonic()
        event("activity.started", **identity)
        try:
            result = await self.next.execute_activity(input)
        except asyncio.CancelledError:
            event("activity.cancelled", level=logging.WARNING, **identity)
            raise
        except Exception as error:
            event(
                "activity.failed", level=logging.ERROR, error_type=type(error).__name__, **identity
            )
            raise
        usage, feedback = getattr(result, "usage", None), getattr(result, "feedback", None)
        event(
            "activity.completed",
            **identity,
            seconds=round(time.monotonic() - started, 3),
            gate=feedback.gate if feedback else None,
            cleanup_confirmed=getattr(result, "cleanup_confirmed", None),
            llm_calls=usage.llm_calls if usage else None,
            tool_calls=usage.tool_calls if usage else None,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            usage_complete=getattr(result, "usage_complete", None),
            execution_status=getattr(result, "execution_status", None),
            disposition=getattr(result, "disposition", None),
        )
        return result


class LifecycleLoggingInterceptor(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _ActivityLogging(next)
