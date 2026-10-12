"""Read-only saved input lookup; no agent-controlled filesystem access.

The native toolsets are built per stage so each stage keeps its own toolset id
(and so its durable activity identity) while sharing one confined reader.
"""

from typing import Annotated, Protocol

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets import FunctionToolset

from .contracts import SourceExcerpt, SourceFile, SourceLine, SourceRead, confined_path

READ_SOURCE_TOOL = "read_source"
# Native per-tool budget: an invented or failing read is refused at once.
TOOL_RETRIES = 0
READ_LINE_LIMIT = 80


def read_saved_source(source_files: tuple[SourceFile, ...], path: str, start_line: int, end_line: int) -> SourceExcerpt:
    confined_path(path)
    source = next((item for item in source_files if item.path == path), None)
    if source is None:
        raise ValueError("source path is absent from the supplied fixture")
    lines = source.content.splitlines()
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError("source line range is absent from the supplied fixture")
    if end_line - start_line + 1 > READ_LINE_LIMIT:
        raise ValueError("source read exceeds 80 lines")
    return SourceExcerpt(path=path, start_line=start_line, end_line=end_line,
                         quote="\n".join(lines[start_line - 1:end_line]))


class SavedSourceDependencies(Protocol):
    """What the shared reader needs from a stage's dependencies."""

    @property
    def source_files(self) -> tuple[SourceFile, ...]: ...

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt: ...


def _numbered(excerpt: SourceExcerpt) -> SourceRead:
    return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                      lines=tuple(SourceLine(number=excerpt.start_line + offset, text=text)
                                  for offset, text in enumerate(excerpt.quote.split("\n"))))


def ranged_source_tools(toolset_id: str) -> FunctionToolset[SavedSourceDependencies]:
    """Caller-selected inclusive range; retained for the legacy analyst and reviewer."""
    tools = FunctionToolset[SavedSourceDependencies](id=toolset_id)

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[SavedSourceDependencies],
                    path: Annotated[str, Field(description="Saved source path exactly as listed in the inventory")],
                    start_line: Annotated[int, Field(ge=1, description="First one-based inclusive line in the saved file, not an upstream document line number")],
                    end_line: Annotated[int, Field(ge=1, description="Last one-based inclusive line in the saved file, not an upstream document line number")]) -> SourceRead:
        """Read at most 80 saved-file-local lines from an inventory path.

        Returned start_line/end_line use that saved file's coordinates. Numbers
        printed inside line text are content, not coordinates. Inventory metadata
        is not source content."""
        try:
            return _numbered(ctx.deps.read_source(path, start_line, end_line))
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    return tools


def window_source_tools(toolset_id: str) -> FunctionToolset[SavedSourceDependencies]:
    """Bounded saved-source windows: the tool computes EOF, the model selects a start."""
    tools = FunctionToolset[SavedSourceDependencies](id=toolset_id)

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[SavedSourceDependencies],
                          path: Annotated[str, Field(description="Saved path exactly as listed in the inventory")],
                          start_line: Annotated[int, Field(ge=1, description="First saved-file line, default 1; use the returned end_line plus one for the next window")] = 1) -> SourceRead:
        """Read up to 80 saved-file lines from start_line, stopping at the actual end of file.

        The tool determines end_line; there is no caller-controlled end_line argument.
        Returned numbered lines are the only coordinates that can authorize a citation.
        """
        try:
            confined_path(path)
            source = next((item for item in ctx.deps.source_files if item.path == path), None)
            if source is None:
                raise ValueError("source path is absent from the supplied fixture")
            end_line = min(start_line + READ_LINE_LIMIT - 1, len(source.content.splitlines()))
            excerpt = ctx.deps.read_source(path, start_line, end_line)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        return _numbered(excerpt)

    return tools
