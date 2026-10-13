"""read_output: a byte window of a previous run's retained output from the trusted ledger."""

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext, ToolFailed

from corsair.agents.issue_analysis.contracts import Contract

from ..dependencies import EnvironmentDependencies

READ_OUTPUT_TOOL = "read_output"
READ_OUTPUT_BYTES = 16384


class OutputSlice(Contract):
    run_id: int
    stream: str
    offset: int
    total_bytes: int
    text: str


async def read_output(ctx: RunContext[EnvironmentDependencies], run_id: int,
                      stream: Annotated[str, Field(pattern="^(stdout|stderr)$")],
                      offset: Annotated[int, Field(ge=0)] = 0) -> OutputSlice:
    """Read up to 16 KiB of a previous run's retained output from a byte offset."""
    if run_id not in ctx.deps.ledger.outputs:
        raise ToolFailed("unknown run_id")
    data = ctx.deps.ledger.outputs[run_id][stream == "stderr"]
    return OutputSlice(run_id=run_id, stream=stream, offset=offset, total_bytes=len(data),
                       text=data[offset:offset + READ_OUTPUT_BYTES].decode("utf-8", "replace"))
