"""Tool availability: writes and runs are withdrawn once no test edit can change the outcome."""

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from ..dependencies import AuthoringDependencies
from ._history import admission_spent, development_runs, dispatched_runs


async def while_edits_can_help(ctx: RunContext[AuthoringDependencies], tool: ToolDefinition) -> ToolDefinition | None:
    """Hide writes and runs once no test edit can change the outcome, leaving only the output contract.

    After a workspace failure the tests never ran, so a rewrite cannot address it and another run would
    blindly retry the refusal; once the run budget is spent, further writes could not be verified; once the
    admission refusals are spent, the stage ends blocked at admission.
    """
    if admission_spent(ctx):
        return None
    executed = [run for run in development_runs(ctx) if run.status != "not_run"]
    if executed and executed[-1].status == "workspace_failure":
        return None
    if len(dispatched_runs(ctx)) >= ctx.deps.budget.dev_runs:
        return None
    return tool
