"""Bounded saved-source reader; never reads the sibling author's artifacts."""
from typing import Annotated
from pydantic import Field
from pydantic_ai import RunContext
from corsair.agents.source.contracts import SourceRead
from corsair.agents.test_authoring.contracts import UnreadSource
from corsair.agents.source.contracts import SourceLine
from corsair.agents.test_authoring.tools._history import readable_files
from corsair.agents.source.tools import READ_LINE_LIMIT
from ..dependencies import SpecialistDependencies

async def read_source(ctx: RunContext[SpecialistDependencies],
                      path: Annotated[str, Field(description='A saved source path or your admitted written file')],
                      start_line: Annotated[int, Field(ge=1, description='First saved-file line')] = 1) -> SourceRead | UnreadSource:
    """Read up to 80 saved lines or your own admitted draft; no filesystem lookup or execution."""
    content = readable_files(ctx).get(path)
    if content is None:
        return UnreadSource(status='not_in_source', path=path[:256], reason='Path is not saved source or your admitted own draft')
    lines = content.splitlines()
    if start_line > len(lines):
        return UnreadSource(status='past_end', path=path, reason='Requested line is past the saved file end')
    end = min(start_line + READ_LINE_LIMIT - 1, len(lines))
    return SourceRead(path=path, start_line=start_line, end_line=end,
        lines=tuple(SourceLine(number=i, text=lines[i-1]) for i in range(start_line, end+1)))
