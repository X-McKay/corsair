"""Episode-local producer tools.

The producer receives capabilities only through these native ADK function tools.
They inspect an already admitted source archive and collect one declarative
submission; they never execute the target or write to the source tree.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Annotated, Any

from google.adk.tools.tool_context import ToolContext
from pydantic import Field, ValidationError

from corsair.contracts import JsonValue, PlanRevision, ProducerInput, Submission
from corsair.runtime.artifacts import ArtifactStore
from corsair.tools.security.sources import SourceAdmissionError, iter_snapshot_files, read_source


@dataclass
class ProducerTools:
    """Mutable capability state that exists for one bounded producer episode."""

    producer_input: ProducerInput
    store: ArtifactStore
    tool_call_limit: int
    tool_calls: int = 0
    submission: Submission | None = None
    terminal: bool = False
    limit_exhausted: bool = False
    errors: list[str] = field(default_factory=list)
    _submit_claimed: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def native_tools(self) -> list:
        """Return the exact ADK callables approved for the producer role."""

        return [self.read_file, self.list_files, self.submit]

    async def _reserve(self, tool_name: str) -> str | None:
        """Charge a tool call before work and reject calls after terminal submit."""

        async with self._lock:
            if self.terminal:
                return "episode already completed by submit"
            if tool_name == "submit":
                if self._submit_claimed:
                    return "a submit call was already made in this episode"
                self._submit_claimed = True
                # A submit is one terminal proposal attempt. Closing before
                # validation means a malformed attempt cannot be followed by
                # another submit or sibling tool that spends more budget.
                self.terminal = True
            if self.tool_calls >= self.tool_call_limit:
                self.limit_exhausted = True
                return "tool-call budget exhausted"
            self.tool_calls += 1
            return None

    @staticmethod
    def _error(reason: str) -> dict[str, str]:
        return {"error": reason}

    async def read_file(
        self,
        path: Annotated[str, Field(min_length=1, max_length=240)],
        tool_context: ToolContext,
    ) -> dict[str, str]:
        """Read one normalized relative file from the admitted source snapshot."""

        del tool_context
        if reason := await self._reserve("read_file"):
            return self._error(reason)
        try:
            content = read_source(
                self.producer_input.prepared.source,
                path,
                self.store,
                self.producer_input.budget.tool_output_bytes,
            )
        except (SourceAdmissionError, ValueError) as error:
            message = str(error)
            self.errors.append(message)
            return self._error(message)
        return {"path": path, "content": content}

    async def list_files(self, tool_context: ToolContext) -> dict[str, Any]:
        """List regular relative files in the validated admitted source snapshot."""

        del tool_context
        if reason := await self._reserve("list_files"):
            return self._error(reason)
        try:
            names = [
                name
                for name, _ in iter_snapshot_files(self.producer_input.prepared.source, self.store)
            ]
        except (SourceAdmissionError, ValueError) as error:
            message = str(error)
            self.errors.append(message)
            return self._error(message)

        selected: list[str] = []
        size = 0
        for name in names:
            encoded = name.encode("utf-8")
            if selected and size + len(encoded) + 1 > self.producer_input.budget.tool_output_bytes:
                break
            selected.append(name)
            size += len(encoded) + 1
        return {"files": selected, "truncated": len(selected) != len(names)}

    async def submit(
        self,
        control_payload: JsonValue,
        exploit_payload: JsonValue,
        hypothesis: Annotated[str, Field(min_length=1, max_length=4000)],
        plan: PlanRevision,
        tool_context: ToolContext,
    ) -> dict[str, str]:
        """Validate and terminally record the episode's one declarative submission."""

        if reason := await self._reserve("submit"):
            return self._error(reason)
        # ADK 2.13's ToolContext does not expose a public terminal setter;
        # native ADK tool handlers set this InvocationContext flag directly.
        # It is not a prompt convention: the LLM flow checks it before another
        # model step is admitted, including after a malformed submission.
        tool_context._invocation_context.end_invocation = True
        try:
            submission = Submission(
                control_payload=control_payload,
                exploit_payload=exploit_payload,
                hypothesis=hypothesis,
                plan=plan,
            )
        except ValidationError as error:
            message = f"invalid submission: {error.errors(include_url=False)}"
            self.errors.append(message)
            return self._error(message)

        expected_parent = (
            None if self.producer_input.round_index == 1 else self.producer_input.round_index - 1
        )
        if submission.plan.revision != self.producer_input.round_index:
            message = "plan revision must equal the current round index"
            self.errors.append(message)
            return self._error(message)
        if submission.plan.parent_revision != expected_parent:
            message = "plan parent_revision does not match the preceding round"
            self.errors.append(message)
            return self._error(message)

        async with self._lock:
            # A second submit cannot arrive after _submit_claimed, but retain a
            # defensive check so a future transport change cannot overwrite the
            # immutable episode result.
            if self.submission is not None:
                return self._error("a submission was already accepted")
            self.submission = submission
        return {"status": "accepted"}


def build_producer_tools(
    producer_input: ProducerInput, store: ArtifactStore, *, tool_call_limit: int | None = None
) -> ProducerTools:
    """Construct private producer tools for a single activity invocation."""

    limit = producer_input.tool_call_limit if tool_call_limit is None else tool_call_limit
    if limit < 1:
        raise ValueError("tool_call_limit must be positive")
    return ProducerTools(producer_input=producer_input, store=store, tool_call_limit=limit)
