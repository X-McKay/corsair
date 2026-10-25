"""The producer's episode-bound read-only source listing tool."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.tools.tool_context import ToolContext

from corsair.contracts import ProducerInput
from corsair.ports.scm import SourceAdmissionError, SourceReader


def create_list_files(
    producer_input: ProducerInput, sources: SourceReader
) -> Callable[..., object]:
    """Bind one native ``list_files`` callable to an admitted producer episode."""

    async def list_files(tool_context: ToolContext) -> dict[str, Any]:
        """List bounded regular relative files in the validated admitted source snapshot."""

        del tool_context
        try:
            names = [name for name, _ in sources.iter_files(producer_input.prepared.source)]
        except (SourceAdmissionError, ValueError) as error:
            return {"error": str(error)}

        selected: list[str] = []
        size = 0
        for name in names:
            encoded = name.encode("utf-8")
            if selected and size + len(encoded) + 1 > producer_input.budget.tool_output_bytes:
                break
            selected.append(name)
            size += len(encoded) + 1
        return {"files": selected, "truncated": len(selected) != len(names)}

    return list_files
