"""Toolset binding for the planner, in offered order.

The planner reuses the shared confined window reader rather than copying it; it binds
its own stable toolset id (its durable activity identity). The reader is offered
through a native PreparedToolset that withdraws it once every inventory line was returned.
"""

from pydantic_ai.toolsets import FunctionToolset, PreparedToolset

from ...source.tools import window_source_tools
from ...toolset_identity import toolset_sha256
from ..dependencies import PlanningDependencies
from ._preparation import withdraw_when_read

TOOLSET_ID = "test_planning_source"


def planning_tools() -> FunctionToolset[PlanningDependencies]:
    """Bounded saved-source windows: the tool computes EOF, the model selects a start."""
    return window_source_tools(TOOLSET_ID)


def offered_tools() -> PreparedToolset[PlanningDependencies]:
    """What the agent registers: the planning toolset, withdrawn once every inventory line was returned."""
    return planning_tools().prepared(withdraw_when_read)


# The digest covers what is offered: the wrapper type and its rule's qualified name around the reader.
TOOLSET_SHA256 = toolset_sha256(offered_tools())
