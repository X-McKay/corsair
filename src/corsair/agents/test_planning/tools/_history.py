"""This run's own successful source reads, the only evidence that can authorize a citation."""

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from ...source.contracts import SourceRead
from ...source.tools import READ_SOURCE_TOOL
from ..dependencies import PlanningDependencies


def run_reads(ctx: RunContext[PlanningDependencies]) -> list[SourceRead]:
    return [SourceRead.model_validate(part.content)
            for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolReturnPart)
            and part.tool_name == READ_SOURCE_TOOL and part.outcome == "success"]
