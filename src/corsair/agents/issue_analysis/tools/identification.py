"""Bounded saved-source windows: the tool computes EOF, the model selects a start."""

from typing import Annotated

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets import FunctionToolset

from ..contracts import SourceLine, SourceRead, confined_path
from .source import READ_SOURCE_TOOL, TOOL_RETRIES, FixtureDependencies


def identification_tools() -> FunctionToolset[FixtureDependencies]:
    tools = FunctionToolset[FixtureDependencies](id="issue_identification_source")

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[FixtureDependencies],
                          path: Annotated[str, Field(description="Saved path exactly as listed in the inventory")],
                          start_line: Annotated[int, Field(ge=1, description="First saved-file line, default 1; use the returned end_line plus one for the next window")] = 1) -> SourceRead:
        """Read up to 80 saved-file lines from start_line, stopping at the actual end of file.

        The tool determines end_line; there is no caller-controlled end_line argument.
        Returned numbered lines are the only coordinates that can authorize a target.
        """
        try:
            confined_path(path)
            source = next((item for item in ctx.deps.inputs.source_files if item.path == path), None)
            if source is None:
                raise ValueError("source path is absent from the supplied fixture")
            end_line = min(start_line + 79, len(source.content.splitlines()))
            excerpt = ctx.deps.read_source(path, start_line, end_line)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                          lines=tuple(SourceLine(number=excerpt.start_line + i, text=text)
                                      for i, text in enumerate(excerpt.quote.split("\n"))))

    return tools
