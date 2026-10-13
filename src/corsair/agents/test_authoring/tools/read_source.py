"""read_source: bounded windows over saved source and the author's own written tests.

Unlike the shared reader, an absent path or a start past the end is a typed answer, not a ModelRetry: with
no tool retries a ModelRetry ends the stage, and live authors re-read their own test file after a
collection error (PLAN-0048 write-only run: 10 of 14 failures).
"""

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from ...source.contracts import SourceLine, SourceRead
from ...source.tools import READ_LINE_LIMIT, READ_SOURCE_TOOL
from ..contracts import UnreadSource
from ..dependencies import AuthoringDependencies
from ._history import current_files, readable_files

__all__ = ["READ_SOURCE_TOOL", "read_source"]


async def read_source(ctx: RunContext[AuthoringDependencies],
                      path: Annotated[str, Field(description="A saved path as listed in the inventory, or an approved test path you have written")],
                      start_line: Annotated[int, Field(ge=1, description="First line, default 1; use the returned end_line plus one for the next window")] = 1) -> SourceRead | UnreadSource:
    """Read up to 80 lines from start_line of a saved source file or of a test file you wrote, stopping at the actual end of file.

    A written test path returns your latest admitted write, not the saved source. Returned numbered lines are the only coordinates that can authorize a citation.
    """
    files = readable_files(ctx)
    written = sorted(current_files(ctx))
    content = files.get(path)
    if content is None:
        approved = ctx.deps.inputs.environment.approved_test_paths
        hint = (f"{path} is an approved test path you have not written yet; write_test_file creates it"
                if path in approved else f"{path} is neither in the saved source nor a test file you wrote")
        return UnreadSource(status="not_in_source", path=path[:256], reason=(
            f"{hint}. Readable: the saved paths in the inventory and your written test files "
            f"({', '.join(written) or 'none yet'}). run_tests already reports collection and compile errors "
            "with file and line; to change a test file, write it again in full with write_test_file.")[:4096])
    lines = content.splitlines()
    if start_line > len(lines):
        return UnreadSource(status="past_end", path=path, reason=(
            f"{path} has {len(lines)} lines; start_line {start_line} is past its end. "
            + ("Read from line 1." if lines else "The file is empty.")))
    end_line = min(start_line + READ_LINE_LIMIT - 1, len(lines))
    return SourceRead(path=path, start_line=start_line, end_line=end_line,
                      lines=tuple(SourceLine(number=number, text=lines[number - 1])
                                  for number in range(start_line, end_line + 1)))
