"""Bounded saved-source reader; never reads the sibling author's artifacts."""
from typing import Annotated
from pydantic import Field
from pydantic_ai import RunContext
from corsair.agents.source.contracts import SourceRead
from corsair.agents.test_authoring.contracts import UnreadSource
from corsair.agents.test_authoring.tools.read_source import read_source as read_authored_source
from ..dependencies import SpecialistDependencies

async def read_source(ctx: RunContext[SpecialistDependencies],
                      path: Annotated[str, Field(description='A saved source path or your admitted written file')],
                      start_line: Annotated[int, Field(ge=1, description='First saved-file line')] = 1) -> SourceRead | UnreadSource:
    """Read up to 80 saved lines or your own admitted draft; no filesystem lookup or execution."""
    return await read_authored_source(ctx, path, start_line)
