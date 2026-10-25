"""Standard logging and native Temporal lifecycle hooks; never log agent content."""

import asyncio
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from temporalio import activity
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor

logger = logging.getLogger("corsair")
_FIELDS = frozenset(
    [
        "run_id",
        "case_id",
        "operation_id",
        "activity",
        "attempt",
        "phase",
        "round",
        "completed",
        "total",
        "seconds",
        "llm_calls",
        "tool_calls",
        "input_tokens",
        "output_tokens",
        "gate",
        "error_type",
        "execution_status",
        "disposition",
        "cleanup_confirmed",
        "artifact",
        "task_queue",
        "namespace",
        "check",
        "status",
        "image_id",
        "usage_complete",
        "message",
    ]
)


def safe_text(value: object) -> str:
    """Redact known credential values, endpoint URLs and terminal control characters."""
    text = str(value)
    for name, secret in os.environ.items():
        if len(secret) >= 8 and any(
            word in name.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")
        ):
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://\S+", "[endpoint]", text)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)[:2000]


def event(name: str, *, level: int = logging.INFO, **fields) -> None:
    logger.log(
        level,
        name,
        extra={"fields": {key: value for key, value in fields.items() if key in _FIELDS}},
    )


class MetadataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("corsair"):
            # SDK warnings may contain request bodies or exception-local input values.
            record.msg, record.args = "SDK diagnostic; request content omitted", ()
        else:
            record.msg, record.args = safe_text(record.getMessage()), ()
        fields = getattr(record, "fields", {})
        record.fields = {
            key: safe_text(value) if isinstance(value, str) else value
            for key, value in fields.items()
            if key in _FIELDS and (value is None or isinstance(value, (str, int, float, bool)))
        }
        record.exc_info = record.exc_text = record.stack_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                    timespec="milliseconds"
                ),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
                **getattr(record, "fields", {}),
            },
            ensure_ascii=False,
        )


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(f"{key}={value}" for key, value in getattr(record, "fields", {}).items())
        return f"{record.getMessage()} {fields}".rstrip()


def configure_logging(console: Console, *, level="INFO", format="text", path=None) -> None:
    """CLI composition only; libraries do not configure application logging."""
    handler = (
        logging.StreamHandler(console.file)
        if format == "json"
        else RichHandler(
            console=console,
            show_path=False,
            markup=False,
            rich_tracebacks=False,
            log_time_format="%H:%M:%S",
            highlighter=None,
        )
    )
    handler.addFilter(MetadataFilter())
    handler.setFormatter(JsonFormatter() if format == "json" else TextFormatter())
    handlers = [handler]
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(MetadataFilter())
        handlers.append(file_handler)
    for name, threshold in (("corsair", level), ("", "WARNING")):
        selected = logging.getLogger(name)
        for old in selected.handlers[:]:
            selected.removeHandler(old)
            old.close()
        selected.handlers = handlers[:]
        selected.setLevel(threshold)
        selected.propagate = False
    # Providers may opt into debug at import time; keep request bodies out of CLI logs.
    for name in ("google.adk", "google_genai", "httpx", "httpcore", "LiteLLM", "litellm"):
        logging.getLogger(name).setLevel(logging.WARNING)


class _ActivityLogging(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput):
        info = activity.info()
        fields = {
            "run_id": info.workflow_id,
            "activity": info.activity_type,
            "attempt": info.attempt,
        }
        started = time.monotonic()
        event("activity.started", **fields)
        try:
            result = await self.next.execute_activity(input)
        except asyncio.CancelledError:
            event("activity.cancelled", level=logging.WARNING, **fields)
            raise
        except Exception as error:
            event("activity.failed", level=logging.ERROR, error_type=type(error).__name__, **fields)
            raise
        else:
            usage = getattr(result, "usage", None)
            feedback = getattr(result, "feedback", None)
            event(
                "activity.completed",
                **fields,
                seconds=round(time.monotonic() - started, 3),
                gate=feedback.gate if feedback else None,
                cleanup_confirmed=getattr(result, "cleanup_confirmed", None),
                llm_calls=usage.llm_calls if usage else None,
                tool_calls=usage.tool_calls if usage else None,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                execution_status=getattr(result, "execution_status", None),
                disposition=getattr(result, "disposition", None),
            )
            return result


class LifecycleLoggingInterceptor(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _ActivityLogging(next)
