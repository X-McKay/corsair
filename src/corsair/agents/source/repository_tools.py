"""Native bounded list, search and read tools over a whole-repository `SourceTree`.

Per-run accounting (bytes returned, windows already read) is derived from the run's own
message history rather than mutable dependency state, so it is deterministic and survives
message replay. Only `read_source` results can authorize a citation (SPEC-0020); search
matches only locate lines.
"""

from typing import Annotated, Protocol

from pydantic import Field, ValidationError
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from .contracts import SourceExcerpt, SourceLine, SourceRead
from .repository import (
    RepeatedRead, RepositoryLimits, SourceListing, SourceSearch, SourceTree, list_tree, search_tree,
)
from .tools import READ_SOURCE_TOOL, TOOL_RETRIES

LIST_SOURCE_TOOL = "list_source"
SEARCH_SOURCE_TOOL = "search_source"
REPOSITORY_TOOLS = frozenset({LIST_SOURCE_TOOL, SEARCH_SOURCE_TOOL, READ_SOURCE_TOOL})


class RepositorySourceDependencies(Protocol):
    @property
    def source_tree(self) -> SourceTree: ...

    @property
    def source_limits(self) -> RepositoryLimits: ...

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt: ...


def _run_returns(ctx: RunContext) -> list[ToolReturnPart]:
    return [part for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolReturnPart) and part.outcome == "success"]


def run_source_reads(ctx: RunContext) -> list[SourceRead]:
    """Successful read_source windows returned in this run; repeated-read notices are not reads."""
    reads = []
    for part in _run_returns(ctx):
        if part.tool_name != READ_SOURCE_TOOL:
            continue
        if isinstance(part.content, SourceRead):
            reads.append(part.content)
        elif isinstance(part.content, dict) and "lines" in part.content:
            try:
                reads.append(SourceRead.model_validate(part.content))
            except ValidationError:
                continue
    return reads


def returned_bytes(ctx: RunContext) -> int:
    """UTF-8 bytes of repository tool results already shown to the model in this run."""
    return sum(len(part.model_response_str().encode("utf-8")) for part in _run_returns(ctx)
               if part.tool_name in REPOSITORY_TOOLS)


async def withdraw_when_spent(ctx: RunContext[RepositorySourceDependencies],
                              tools: list[ToolDefinition]) -> list[ToolDefinition]:
    """Native tool preparation: once the run byte budget is spent only the output tool remains."""
    if returned_bytes(ctx) >= ctx.deps.source_limits.run_bytes:
        return [tool for tool in tools if tool.name not in REPOSITORY_TOOLS]
    return tools


def repository_source_tools(toolset_id: str):
    """Bounded whole-repository tools; the toolset id is the stage's durable tool identity."""
    tools = FunctionToolset[RepositorySourceDependencies](id=toolset_id)

    @tools.tool(name=LIST_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def list_source(ctx: RunContext[RepositorySourceDependencies],
                          directory: Annotated[str, Field(max_length=256, description="Repository directory, '' for the root")] = "",
                          pattern: Annotated[str | None, Field(max_length=256, description="Optional glob matched against each full path or file name, for example '*Servlet*.java'; lists matching files at any depth under directory")] = None) -> SourceListing:
        """List a directory's immediate entries with nested file counts and sizes, or find files by glob.

        Results are capped; truncated reports more entries than were returned. Narrow the
        directory or pattern rather than listing again."""
        try:
            return list_tree(ctx.deps.source_tree, ctx.deps.source_limits, directory, pattern)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    @tools.tool(name=SEARCH_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def search_source(ctx: RunContext[RepositorySourceDependencies],
                            text: Annotated[str, Field(min_length=1, max_length=256, description="Literal text to find on one line; not a regular expression")],
                            directory: Annotated[str, Field(max_length=256, description="Restrict to this directory, '' for the whole repository")] = "",
                            pattern: Annotated[str | None, Field(max_length=256, description="Optional glob restricting searched paths or file names, for example '*.java'")] = None,
                            ignore_case: bool = False) -> SourceSearch:
        """Find lines containing literal text, in path order, with a capped number of matches.

        Match line numbers locate code only. Read the lines with read_source before citing them."""
        try:
            return search_tree(ctx.deps.source_tree, ctx.deps.source_limits, text, directory, pattern, ignore_case)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[RepositorySourceDependencies],
                          path: Annotated[str, Field(description="Repository file path exactly as listed or found")],
                          start_line: Annotated[int, Field(ge=1, description="First repository-file line, default 1; use the returned end_line plus one for the next window")] = 1) -> SourceRead | RepeatedRead:
        """Read up to 80 numbered lines of a repository file from start_line.

        The tool determines end_line (80 lines, a byte cap or end of file). Returned numbered
        lines are the only coordinates that can authorize a citation. A window already
        returned in this run is not returned again."""
        try:
            end_line = ctx.deps.source_tree.window_end(path, start_line, ctx.deps.source_limits)
            if any(read.path == path and read.start_line <= start_line and end_line <= read.end_line
                   for read in run_source_reads(ctx)):
                return RepeatedRead(path=path, start_line=start_line, end_line=end_line)
            excerpt = ctx.deps.read_source(path, start_line, end_line)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                          lines=tuple(SourceLine(number=excerpt.start_line + offset, text=text)
                                      for offset, text in enumerate(excerpt.quote.split("\n"))))

    return tools.prepared(withdraw_when_spent)
