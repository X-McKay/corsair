"""read_source: up to 80 saved manifest, CI or documentation lines from the supplied inventory."""

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext, ToolFailed

from corsair.agents.issue_analysis.contracts import SourceLine, SourceRead

from ..dependencies import EnvironmentDependencies

READ_SOURCE_TOOL = "read_source"


async def read_source(ctx: RunContext[EnvironmentDependencies],
                      path: Annotated[str, Field(description="Saved path exactly as listed in the inventory")],
                      start_line: Annotated[int, Field(ge=1, description="First saved-file line; use the returned end_line plus one for the next window")] = 1) -> SourceRead:
    """Read up to 80 saved manifest, CI or documentation lines from start_line, stopping at end of file."""
    try:
        source = next((s for s in ctx.deps.inputs.source_files if s.path == path), None)
        if source is None:
            raise ValueError("source path is absent from the supplied inventory")
        excerpt = ctx.deps.read_source(path, start_line, min(start_line + 79, len(source.content.splitlines())))
    except ValueError as exc:
        raise ToolFailed(str(exc)) from exc
    return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                      lines=tuple(SourceLine(number=excerpt.start_line + i, text=text)
                                  for i, text in enumerate(excerpt.quote.split("\n"))))
