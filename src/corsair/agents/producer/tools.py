"""Episode-local producer tools.

The producer receives capabilities only through these native ADK function tools.
They inspect an already admitted source archive; they never execute the target
or write to the source tree. ADK owns structured final output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from google.adk.tools.tool_context import ToolContext
from pydantic import Field

from corsair.contracts import ProducerInput
from corsair.ports.scm import SourceAdmissionError, SourceReader


@dataclass
class ProducerTools:
    """Read-only source capabilities private to one bounded producer episode."""

    producer_input: ProducerInput
    sources: SourceReader

    def native_tools(self) -> list[Callable[..., Any]]:
        """Return the exact ADK callables approved for the producer role."""

        return [self.read_file, self.list_files]

    async def read_file(
        self,
        path: Annotated[str, Field(min_length=1, max_length=240)],
        tool_context: ToolContext,
    ) -> dict[str, str]:
        """Read one normalized relative file from the admitted source snapshot."""

        del tool_context
        try:
            content = self.sources.read_text(
                self.producer_input.prepared.source,
                path,
                max_bytes=self.producer_input.budget.tool_output_bytes,
            )
        except (SourceAdmissionError, ValueError) as error:
            return {"error": str(error)}
        return {"path": path, "content": content}

    async def list_files(self, tool_context: ToolContext) -> dict[str, Any]:
        """List regular relative files in the validated admitted source snapshot."""

        del tool_context
        try:
            names = [
                name for name, _ in self.sources.iter_files(self.producer_input.prepared.source)
            ]
        except (SourceAdmissionError, ValueError) as error:
            return {"error": str(error)}

        selected: list[str] = []
        size = 0
        for name in names:
            encoded = name.encode("utf-8")
            if selected and size + len(encoded) + 1 > self.producer_input.budget.tool_output_bytes:
                break
            selected.append(name)
            size += len(encoded) + 1
        return {"files": selected, "truncated": len(selected) != len(names)}


def build_producer_tools(producer_input: ProducerInput, sources: SourceReader) -> ProducerTools:
    """Construct read-only source capabilities for one bounded ADK invocation."""

    return ProducerTools(producer_input=producer_input, sources=sources)
