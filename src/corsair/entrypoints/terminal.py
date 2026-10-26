"""Presentation only. Rich owns color/animation; Temporal owns execution and waiting."""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from contextlib import nullcontext
from typing import Any, Literal, Protocol, TypeVar, cast

from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from temporalio.service import RPCError, RPCStatusCode

from corsair.contracts import InvestigationResult
from corsair.evaluation.scoring import usage_metrics
from corsair.observability.logging import event, safe_error_detail, safe_text
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.ports.scm import SourceAdmissionError

_STYLES: dict[str, str] = {
    "SUPPORTED": "green",
    "CONDITIONAL": "yellow",
    "INCONCLUSIVE": "yellow",
    "ERROR": "red",
    "BLOCKED": "red",
    "CANCELLED": "yellow",
    "COMPLETED": "green",
}
T = TypeVar("T")


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


_TEMPORAL_REMEDY = (
    "Start Temporal (for example `temporal server start-dev`) or set temporal_address and "
    "temporal_namespace in --settings, then run `corsair doctor`."
)
_DOCKER_REMEDY = "Start the Docker daemon (or set DOCKER_HOST), then run `corsair doctor`."
_IMAGE_REMEDY = (
    "Build the trusted image with `just images`, or set image in --settings to a built tag, "
    "then run `corsair doctor`."
)
_JSON_REMEDY = "The file is not valid JSON; check it for truncation or an editing mistake."
_SOURCE_REMEDIES = (
    (
        "outside configured source_root",
        "Set source_root in --settings to a directory that contains the request's sources "
        "(the default is the current directory).",
    ),
    (
        "expected_digest",
        "The source tree differs from the request's frozen expected_digest. Restore that "
        "source, or write a new request for the changed source; never edit a frozen digest.",
    ),
    (
        "source path does not exist",
        "Check source.path in the request; it resolves relative to the request file.",
    ),
    (
        "configured source_root",
        "Set source_root in --settings to an existing, readable directory that is not a "
        "symbolic link.",
    ),
    (
        "limit",
        "Narrow the request's source path to the code under test, or review "
        "source_limit_bytes and source_limit_files in --settings.",
    ),
    (
        "are not admitted",
        "Remove symbolic links and special files from the source tree; only regular files "
        "and directories are admitted.",
    ),
)


def _module_error(error: BaseException, module: str, name: str) -> bool:
    """Match an SDK exception class only if its module is already loaded; never import it."""
    kind = getattr(sys.modules.get(module), name, None)
    return isinstance(kind, type) and isinstance(error, kind)


def failure_remedy(error: BaseException) -> str | None:
    """Return one fixed next step for a known failure class, or ``None``.

    The exception text is matched against fixed patterns but never echoed: every remedy is a
    constant, so it cannot carry credentials, endpoints or provider content. The original,
    sanitized error detail is still reported beside it.
    """
    text = str(error)
    if isinstance(error, ValidationError):
        if any(
            item["type"] == "json_invalid"
            for item in error.errors(include_input=False, include_url=False)
        ):
            return _JSON_REMEDY
        return (
            "Correct the fields named above; see docs/reference/configuration.md for settings "
            "and docs/reference/schemas.md for requests and submissions."
        )
    if isinstance(error, json.JSONDecodeError):
        return _JSON_REMEDY
    if isinstance(error, FileNotFoundError):
        return (
            "Check the path: command arguments and --settings resolve from the current "
            "directory, request source paths from the request file's directory."
        )
    if isinstance(error, IsADirectoryError | NotADirectoryError):
        return "Pass the path of a file, not a directory, and check each parent directory."
    if isinstance(error, PermissionError):
        return "Check file permissions: inputs must be readable and artifact_root writable."
    if isinstance(error, SourceAdmissionError):
        return next((remedy for pattern, remedy in _SOURCE_REMEDIES if pattern in text), None)
    if isinstance(error, SandboxUnavailable):
        return _IMAGE_REMEDY if "image" in text else _DOCKER_REMEDY
    if _module_error(error, "docker.errors", "ImageNotFound"):
        return _IMAGE_REMEDY
    if _module_error(error, "docker.errors", "DockerException"):
        return _DOCKER_REMEDY
    if isinstance(error, RPCError):
        if error.status == RPCStatusCode.NOT_FOUND and text.startswith("Namespace"):
            return (
                "Create the namespace (`temporal operator namespace create`) or set "
                "temporal_namespace in --settings."
            )
        if error.status == RPCStatusCode.NOT_FOUND:
            return (
                "Check the run id and temporal_namespace; `temporal workflow list` shows "
                "existing runs."
            )
        if error.status in {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}:
            return _TEMPORAL_REMEDY
        return None
    if isinstance(error, RuntimeError) and text.startswith("Failed client connect"):
        return _TEMPORAL_REMEDY
    if isinstance(error, TimeoutError):
        return (
            "A service did not answer in time; run `corsair doctor` to check Temporal and Docker."
        )
    if isinstance(error, ValueError) and text.startswith("No committed result"):
        return (
            "Check the run id and artifact_root in --settings; for a run that has not "
            "finished, use `corsair inspect RUN_ID --online`."
        )
    return None


def _text(value: object) -> Text:
    return Text("unknown" if value is None else safe_text(value))


class Terminal:
    def __init__(self, args: TerminalOptions | argparse.Namespace) -> None:
        options = cast(TerminalOptions, args)
        requested = options.format
        self.human = requested == "human" or (requested == "auto" and sys.stdout.isatty())
        # JSON mode must remain free of cursor movement even when running on a TTY.
        colors = not options.no_color and requested != "json"
        animation = self.human and not options.no_animation
        animation = animation and options.log_format != "json"
        self.out = Console(
            no_color=not colors,
            color_system="auto" if colors else None,
            force_interactive=False,
            markup=False,
            highlight=False,
        )
        self.err = Console(
            stderr=True,
            no_color=not colors,
            color_system="auto" if colors else None,
            force_interactive=None if animation else False,
            markup=False,
            highlight=False,
        )
        self.animate = animation and self.err.is_interactive

    def emit(self, value: object) -> None:
        """Write a complete JSON receipt or a compact human rendering to stdout."""
        rendered = TypeAdapter(Any).dump_python(value, mode="json")
        if not self.human:
            print(json.dumps(rendered, indent=2, ensure_ascii=False))
            return
        if isinstance(rendered, dict) and "disposition" in rendered:
            self._result(rendered)
        elif isinstance(rendered, dict) and "checks" in rendered:
            table = Table("Check", "Status", "Details", expand=True)
            for check in rendered["checks"]:
                style = {"pass": "green", "fail": "red", "warn": "yellow"}.get(
                    check["status"], "cyan"
                )
                detail = _text(check["detail"])
                if check.get("remedy"):
                    detail.append("\n→ ").append(_text(check["remedy"]))
                table.add_row(
                    _text(check["name"]), Text(check["status"].upper(), style=style), detail
                )
            self.out.print(Panel(table, title="Corsair · Environment checks", border_style="cyan"))
            self.out.print(_text(rendered["qualification"]))
        elif isinstance(rendered, dict) and ("summary" in rendered or "attempts" in rendered):
            summary = rendered.get("summary", rendered)
            table = Table.grid(padding=(0, 2))
            for key, detail in summary.items():
                table.add_row(Text(key.replace("_", " "), style="cyan"), _text(detail))
            self.out.print(Panel(table, title="Corsair · Evaluation", border_style="cyan"))
            if "report" in rendered:
                self.out.print(Text("Report: ") + _text(rendered["report"]))
        else:
            self.out.print(
                Panel(
                    JSON(json.dumps(rendered, ensure_ascii=False)),
                    title="Corsair · Native receipt",
                    border_style="cyan",
                )
            )

    def _result(self, value: dict[str, Any]) -> None:
        """Render a validated investigation result without exposing model content."""
        table = Table.grid(padding=(0, 2), expand=True)
        label = value["disposition"]
        table.add_row(
            Text("Disposition", style="cyan"), Text(label, style=_STYLES.get(label, "cyan"))
        )
        for key in ("run_id", "case_id", "execution_status", "scope", "reason", "fix_status"):
            table.add_row(Text(key.replace("_", " ").title(), style="cyan"), _text(value.get(key)))
        for item in value.get("rounds", []):
            observation = item.get("observation") or {}
            session = item.get("session", 1)
            name = (
                f"Round {item['index']}"
                if session == 1
                else f"Session {session} round {item['index']}"
            )
            for role in ("control", "adversarial"):
                evidence = observation.get(role) or {}
                detail = (
                    f"{evidence.get('outcome', 'not observed')} · "
                    f"exit={evidence.get('native_exit_code')} · "
                    f"coverage={evidence.get('covered_lines', [])}"
                )
                table.add_row(_text(f"{name} {role}"), _text(detail))
            audit = (item.get("audit") or {}).get("review") or {}
            table.add_row(_text(f"{name} audit"), _text(audit.get("decision")))
            usage = item["producer"]["usage"]
            table.add_row(
                _text(f"{name} producer"),
                _text(f"{usage['llm_calls']} LLM / {usage['tool_calls']} tool calls"),
            )
            feedback = item["producer"].get("feedback") or observation.get("feedback")
            if feedback:
                table.add_row(Text("Gate", style="yellow"), _text(feedback["gate"]))
        table.add_row(
            Text("Usage complete", style="cyan"), _text(value.get("usage_complete", True))
        )
        for key, total in usage_metrics(InvestigationResult.model_validate(value)).items():
            table.add_row(Text(key.replace("_", " ").title(), style="cyan"), _text(total))
        for role, model in (value.get("manifest") or {}).get("models", {}).items():
            table.add_row(Text(f"{role.title()} model", style="cyan"), _text(model))
        table.add_row(Text("Cost", style="cyan"), Text("unknown"))
        artifact = value.get("result_artifact") or {}
        table.add_row(Text("Result SHA-256", style="cyan"), _text(artifact.get("sha256")))
        self.out.print(
            Panel(table, title="Corsair · Investigation", border_style=_STYLES.get(label, "cyan"))
        )

    def report_failure(self, error: Exception) -> None:
        """Log a failed command with its sanitized detail and, when known, a fixed remedy."""
        remedy = failure_remedy(error)
        event(
            "cli.failed",
            level=logging.ERROR,
            error_type=type(error).__name__,
            message=safe_error_detail(error),
            **({} if remedy is None else {"remedy": remedy}),
        )

    async def wait(
        self,
        awaitable: Awaitable[T],
        label: str,
        *,
        query: Callable[[], Awaitable[Mapping[str, object]]] | None = None,
    ) -> T:
        """Observe actual SDK completion; query failures never invent success or progress."""
        status = (
            self.err.status(Text(label), spinner="dots", spinner_style="cyan")
            if self.animate
            else None
        )
        task = asyncio.ensure_future(awaitable)
        last: Mapping[str, object] | None = None
        query_failed = False
        with status if status is not None else nullcontext():
            try:
                while not task.done():
                    if query is not None:
                        try:
                            async with asyncio.timeout(2):
                                actual = await query()
                            if actual != last:
                                phase = actual.get("phase")
                                round_index = actual.get("round")
                                completed = actual.get("completed")
                                total = actual.get("total")
                                detail = " · ".join(
                                    f"{key}={value}" for key, value in actual.items()
                                )
                                event(
                                    "workflow.progress",
                                    phase=phase if isinstance(phase, str) else None,
                                    round=round_index if isinstance(round_index, int) else None,
                                    completed=completed if isinstance(completed, int) else None,
                                    total=total if isinstance(total, int) else None,
                                )
                                if status:
                                    status.update(Text(f"{label} · {detail}"))
                                last = actual
                            query_failed = False
                        except Exception as error:
                            if not query_failed:
                                event(
                                    "workflow.progress_unavailable",
                                    level=logging.WARNING,
                                    error_type=type(error).__name__,
                                )
                            query_failed = True
                    await asyncio.wait({task}, timeout=1)
                return await task
            finally:
                if not task.done():
                    # Cancels local waiting, not the durable remote workflow.
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
