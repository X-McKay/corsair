"""Standard logging configuration and sanitizers; never log agent content.

Only the standard library is imported at module scope so finite CLI commands do not pay for
Rich or Pydantic before they need them; Temporal lifecycle hooks live in ``lifecycle``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from rich.console import Console

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
        "role",
        "skill_name",
        "remedy",
        "max_concurrent_activities",
        "max_concurrent_workflow_tasks",
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
    from pydantic import ValidationError

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
        fields = dict(getattr(record, "fields", {}))
        remedy = fields.pop("remedy", None)
        line = f"{record.getMessage()} {' '.join(f'{k}={v}' for k, v in fields.items())}".rstrip()
        # A remedy is a next step for a person, so it gets its own line rather than a key=value.
        return f"{line}\nremedy: {remedy}" if remedy else line


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
    from rich.logging import RichHandler

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
