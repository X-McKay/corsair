"""Standard logging and native Temporal lifecycle hooks; never log agent content."""

import asyncio
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from temporalio import activity
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor
from typing_extensions import TypedDict

logger = logging.getLogger("corsair")
type LogValue = str | int | float | bool | None
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
    """Redact current credentials, endpoint URLs and terminal control characters."""
    text = str(value)
    for name, secret in os.environ.items():
        if len(secret) >= 8 and any(
            word in name.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")
        ):
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://\S+", "[endpoint]", text)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)[:2000]


def safe_error_detail(error: Exception) -> str:
    """Explain validation failures without reflecting rejected input values."""
    if isinstance(error, ValidationError):
        return safe_text(
            "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                for item in error.errors(include_input=False, include_url=False)
            )
        )
    return safe_text(error)


def event(name: str, *, level: int = logging.INFO, **fields: LogValue) -> None:
    logger.log(
        level,
        name,
        extra={"fields": {key: value for key, value in fields.items() if key in _FIELDS}},
    )


class MetadataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        fields = getattr(record, "fields", {})
        if not record.name.startswith("corsair"):
            # Preserve diagnostic provenance, not SDK request bodies or exception locals.
            record.msg, record.args = "sdk.diagnostic_content_omitted", ()
            if record.exc_info and record.exc_info[0]:
                fields = {**fields, "error_type": record.exc_info[0].__name__}
        else:
            record.msg, record.args = safe_text(record.getMessage()), ()
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


def _set_log_handlers(handlers: list[logging.Handler], level: str) -> None:
    """Install owned handlers once; close shared previous handlers without duplication."""
    previous: set[logging.Handler] = set()
    for name, threshold in (("corsair", level), ("", "WARNING")):
        selected = logging.getLogger(name)
        previous.update(selected.handlers)
        selected.handlers = handlers[:]
        selected.setLevel(threshold)
        selected.disabled = False
        selected.propagate = False
    for handler in previous:
        if handler not in handlers:
            handler.close()


def _console_log_handler(console: Console, format: Literal["text", "json"]) -> logging.Handler:
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
    return handler


def configure_logging(
    console: Console,
    *,
    level: str = "INFO",
    format: Literal["text", "json"] = "text",
    path: str | Path | None = None,
) -> None:
    """Configure stderr before file I/O, so failed mirroring still produces safe diagnostics."""
    handlers: list[logging.Handler] = [_console_log_handler(console, format)]
    _set_log_handlers(handlers, level)
    for name in ("google.adk", "google_genai", "httpx", "httpcore", "LiteLLM", "litellm"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(mode=0o600, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(MetadataFilter())
        handlers.append(file_handler)
        _set_log_handlers(handlers, level)


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
