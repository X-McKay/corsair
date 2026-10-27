"""Presentation only. Rich owns color/animation; Temporal owns execution and waiting.

``Terminal`` chooses JSON, Markdown or human output and dispatches each human view to its
family module under :mod:`corsair.entrypoints.render`.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, TypeVar, cast

from pydantic import TypeAdapter
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import InvestigationResult, Observation
from corsair.entrypoints.render.checks import (
    print_checks,
    print_datasets,
    print_intake,
    print_review_audit,
)
from corsair.entrypoints.render.preview import print_preview, print_preview_diff
from corsair.entrypoints.render.progress import (
    child_changes,
    child_line,
    progress_fields,
    progress_line,
    progress_panel,
)
from corsair.entrypoints.render.remedies import failure_remedy
from corsair.entrypoints.render.reports import print_comparison, print_evaluation
from corsair.entrypoints.render.result import (
    print_explanation,
    print_observation,
    print_result,
)
from corsair.entrypoints.render.runs import print_evidence, print_runs
from corsair.observability.logging import event, safe_error_detail

T = TypeVar("T")
# Seconds between native status queries while a durable workflow remains open.
_POLL_SECONDS = 1.0


class TerminalOptions(Protocol):
    """Presentation switches shared by every parsed command."""

    format: Literal["auto", "human", "json", "markdown"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Terminal:
    def __init__(self, args: TerminalOptions | argparse.Namespace) -> None:
        options = cast(TerminalOptions, args)
        requested = options.format
        self.human = requested == "human" or (requested == "auto" and sys.stdout.isatty())
        self.markdown = requested == "markdown"
        # JSON mode must remain free of cursor movement even when running on a TTY.
        colors = not options.no_color and requested not in {"json", "markdown"}
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

    def emit(self, value: object, *, store: ArtifactStore | None = None) -> None:
        """Write a complete JSON receipt, a Markdown record or a compact human rendering.

        ``store`` lets the human result view verify each round's receipts for its gate
        ledger; without it, rounds that reached the kernel show ``evidence_unverified``.
        JSON output never depends on it.
        """
        rendered = TypeAdapter(Any).dump_python(value, mode="json")
        if self.markdown:
            from corsair.entrypoints.markdown import to_markdown

            sys.stdout.write(to_markdown(rendered))
            return
        if not self.human:
            print(json.dumps(rendered, indent=2, ensure_ascii=False))
            return
        if isinstance(rendered, dict) and "statements" in rendered:
            print_explanation(self.out, rendered, store)
        elif isinstance(rendered, dict) and "disposition" in rendered:
            print_result(self.out, InvestigationResult.model_validate(rendered), store)
        elif isinstance(rendered, dict) and {"operation_id", "submission_digest"} <= set(rendered):
            print_observation(self.out, Observation.model_validate(rendered))
        elif isinstance(rendered, dict) and "runs" in rendered:
            print_runs(self.out, rendered)
        elif isinstance(rendered, dict) and {"intake", "findings"} <= set(rendered):
            print_intake(self.out, rendered)
        elif isinstance(rendered, dict) and "dataset_audit" in rendered:
            print_review_audit(self.out, rendered)
        elif isinstance(rendered, dict) and {"datasets", "valid"} <= set(rendered):
            print_datasets(self.out, rendered)
        elif isinstance(rendered, dict) and "observations" in rendered:
            print_evidence(self.out, rendered)
        elif isinstance(rendered, dict) and "checks" in rendered:
            print_checks(self.out, rendered)
        elif isinstance(rendered, dict) and "cases" in rendered and "regression" in rendered:
            print_comparison(self.out, rendered)
        elif isinstance(rendered, dict) and ("summary" in rendered or "attempts" in rendered):
            print_evaluation(self.out, rendered)
        else:
            self.out.print(
                Panel(
                    JSON(json.dumps(rendered, ensure_ascii=False)),
                    title="Corsair · Native receipt",
                    border_style="cyan",
                )
            )

    def preview(self, value: dict[str, Any], *, full: bool) -> None:
        """Render an agent preview or preview diff; JSON and Markdown keep every byte."""
        if not self.human:
            self.emit(value)
        elif "baseline" in value:
            print_preview_diff(self.out, value, full=full)
        else:
            print_preview(self.out, value, full=full)

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

    def _print_progress(
        self, label: str, status: Mapping[str, object], seen: dict[str, str], begun: float
    ) -> None:
        """Plain mode: one line per evaluation child state change, else one status line."""
        now = _utcnow()
        fields = progress_fields(status, now, time.monotonic() - begun)
        lines = [child_line(label, row, fields, now) for row in child_changes(seen, status)]
        for line in lines or [progress_line(label, fields)]:
            self.err.print(line, soft_wrap=True)

    async def wait(
        self,
        awaitable: Awaitable[T],
        label: str,
        *,
        query: Callable[[], Awaitable[Mapping[str, object]]] | None = None,
    ) -> T:
        """Observe actual SDK completion; query failures never invent success or progress.

        With a status query, an animated terminal shows a live panel, a plain human terminal
        prints one line per status change (per child state change for an evaluation), and
        JSON mode writes nothing beyond the logs.
        """
        begun = time.monotonic()
        last: Mapping[str, object] | None = None
        seen: dict[str, str] = {}

        def frame() -> Panel:
            now = _utcnow()
            fields = progress_fields(last, now, time.monotonic() - begun)
            return progress_panel(label, last, fields, now=now)

        display: AbstractContextManager[object] = nullcontext()
        if self.animate and query is not None:
            display = Live(
                console=self.err, get_renderable=frame, refresh_per_second=4, transient=False
            )
        elif self.animate:
            display = self.err.status(Text(label), spinner="dots", spinner_style="cyan")
        task = asyncio.ensure_future(awaitable)
        query_failed = False
        with display:
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
                                event(
                                    "workflow.progress",
                                    phase=phase if isinstance(phase, str) else None,
                                    round=round_index if isinstance(round_index, int) else None,
                                    completed=completed if isinstance(completed, int) else None,
                                    total=total if isinstance(total, int) else None,
                                )
                                last = actual
                                if self.human and not self.animate:
                                    self._print_progress(label, last, seen, begun)
                            query_failed = False
                        except Exception as error:
                            if not query_failed:
                                event(
                                    "workflow.progress_unavailable",
                                    level=logging.WARNING,
                                    error_type=type(error).__name__,
                                )
                            query_failed = True
                    await asyncio.wait({task}, timeout=_POLL_SECONDS)
                return await task
            finally:
                if not task.done():
                    # Cancels local waiting, not the durable remote workflow.
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
