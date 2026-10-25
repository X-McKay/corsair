"""The producer's episode-bound read-only source-file tool."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from google.adk.tools.tool_context import ToolContext
from pydantic import Field

from corsair.contracts import ProducerInput
from corsair.ports.scm import SourceAdmissionError, SourceReader


def create_read_file(producer_input: ProducerInput, sources: SourceReader) -> Callable[..., object]:
    """Bind one native ``read_file`` callable to an admitted producer episode."""

    async def read_file(
        path: Annotated[str, Field(min_length=1, max_length=240)],
        tool_context: ToolContext,
    ) -> dict[str, str]:
        """Read one normalized relative text file from the admitted source snapshot."""

        del tool_context
        try:
            content = sources.read_text(
                producer_input.prepared.source,
                path,
                max_bytes=producer_input.budget.tool_output_bytes,
            )
        except (SourceAdmissionError, ValueError) as error:
            return {"error": str(error)}
        return {"path": path, "content": content}

    return read_file
