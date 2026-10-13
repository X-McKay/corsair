"""Tool availability: writes and runs are withdrawn once no test edit can change the outcome."""

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from ..dependencies import AuthoringDependencies
from ._history import admission_spent, development_runs, dispatched_runs


def withdrawal(ctx: RunContext[AuthoringDependencies]) -> str | None:
    """Why writes and runs are withdrawn, or None while a test edit can still change the outcome.

    After a workspace failure the tests never ran, so a rewrite cannot address it and another run would
    blindly retry the refusal; once the run budget is spent, further writes could not be verified; once the
    admission refusals are spent, the stage ends blocked at admission.
    """
    if admission_spent(ctx):
        return "the admission refusals are spent"
    executed = [run for run in development_runs(ctx) if run.status != "not_run"]
    if executed and executed[-1].status == "workspace_failure":
        return f"the last run was a workspace failure before any test ran: {executed[-1].errors}"
    if len(dispatched_runs(ctx)) >= ctx.deps.budget.dev_runs:
        return "the development run budget is spent"
    return None


async def while_edits_can_help(ctx: RunContext[AuthoringDependencies], tool: ToolDefinition) -> ToolDefinition | None:
    """Hide writes and runs once no test edit can change the outcome, leaving only the output contract."""
    return None if withdrawal(ctx) else tool
