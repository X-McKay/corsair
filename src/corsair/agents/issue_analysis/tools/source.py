"""Read-only saved input lookup; no agent-controlled filesystem access."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets import FunctionToolset

from ..contracts import IssueAnalysisInput, SourceExcerpt, SourceLine, SourceRead, confined_path


@dataclass(frozen=True)
class FixtureDependencies:
    inputs: IssueAnalysisInput

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        confined_path(path)
        source = next((item for item in self.inputs.source_files if item.path == path), None)
        if source is None:
            raise ValueError("source path is absent from the supplied fixture")
        lines = source.content.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            raise ValueError("source line range is absent from the supplied fixture")
        if end_line - start_line + 1 > 80:
            raise ValueError("source read exceeds 80 lines")
        return SourceExcerpt(path=path, start_line=start_line, end_line=end_line,
                             quote="\n".join(lines[start_line - 1:end_line]))



def source_tools() -> FunctionToolset[FixtureDependencies]:
    tools = FunctionToolset[FixtureDependencies](id="issue_analysis_source")

    @tools.tool(retries=0)
    async def read_source(ctx: RunContext[FixtureDependencies], path: str,
                    start_line: Annotated[int, Field(ge=1, description="First one-based inclusive line in the saved file, not an upstream document line number")],
                    end_line: Annotated[int, Field(ge=1, description="Last one-based inclusive line in the saved file, not an upstream document line number")]) -> SourceRead:
        """Read at most 80 saved-file-local lines from an inventory path.

        Returned start_line/end_line use that saved file's coordinates. Numbers
        printed inside line text are content, not coordinates. Inventory metadata
        is not source content."""
        try:
            excerpt = ctx.deps.read_source(path, start_line, end_line)
            return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                              lines=tuple(SourceLine(number=excerpt.start_line + offset, text=text)
                                          for offset, text in enumerate(excerpt.quote.split("\n"))))
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    return tools
