"""Reuse the bounded authoring reader with an explicit immutable seed and current-run writes."""

from typing import Annotated
from pydantic import Field
from pydantic_ai import RunContext

from corsair.agents.source.contracts import SourceRead
from corsair.agents.test_authoring.contracts import UnreadSource
from corsair.agents.test_authoring.tools.read_source import read_source as read_authored_source
from ..dependencies import DraftingDependencies


async def read_source(ctx: RunContext[DraftingDependencies],
                      path: Annotated[str, Field(description="A saved source path, frozen control path or your admitted written test path")],
                      start_line: Annotated[int, Field(ge=1, description="First saved-file line, default 1")] = 1) -> SourceRead | UnreadSource:
    """Read up to 80 saved lines from source, immutable frozen control or this run's admitted drafts.

    No filesystem lookup occurs; this tool performs no discovery or execution."""
    result = await read_authored_source(ctx, path, start_line)
    if isinstance(result, UnreadSource) and result.status == "not_in_source":
        return result.model_copy(update={"reason": "Path is not in the saved source, frozen control or admitted writes; write only owned test paths"})
    return result
