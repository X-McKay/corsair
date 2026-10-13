"""list_toolchains: the admitted toolchain catalog and the preparation sandbox's toolchain."""

from pydantic import Field
from pydantic_ai import RunContext

from corsair.agents.issue_analysis.contracts import Contract

from ..contracts import Toolchain
from ..dependencies import EnvironmentDependencies

LIST_TOOLCHAINS_TOOL = "list_toolchains"


class ToolchainCatalog(Contract):
    prepared: str = Field(description="Toolchain of the preparation sandbox; commands run in this one only")
    toolchains: tuple[Toolchain, ...]


async def list_toolchains(ctx: RunContext[EnvironmentDependencies]) -> ToolchainCatalog:
    """List the admitted toolchain images and the one the preparation sandbox runs."""
    return ToolchainCatalog(prepared=ctx.deps.toolchain_id, toolchains=ctx.deps.inputs.toolchains)
