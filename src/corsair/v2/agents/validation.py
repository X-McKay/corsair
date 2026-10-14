"""Pure, no-I/O output checks that remain inside each role's declared authority."""
from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from ..contracts import ProbeDraft, RepairDraft
from .dependencies import AgentDeps
from .prompts import Role


def validate_role_output(ctx: RunContext[AgentDeps], output: object, role: Role) -> object:
    """Enforce only local contract/path authority after native Pydantic validation.

    Source citation existence/ranges and all business evidence checks deliberately
    remain in the parent deterministic activity; this validator never touches
    storage, a filesystem, a provider, or Temporal state.
    """
    deps = ctx.deps
    if role in ("control_author", "exploit_author"):
        if not isinstance(output, ProbeDraft):
            raise ModelRetry("The author must return the declared ProbeDraft output")
        if deps.expected_probe_path is None:
            raise ModelRetry("No probe path authority was admitted for this author")
        if output.path != deps.expected_probe_path:
            raise ModelRetry("The draft path must exactly equal the admitted own probe path")
    if role == "repair":
        if not isinstance(output, RepairDraft):
            raise ModelRetry("The repair stage must return the declared RepairDraft output")
        if output.status == "proposed" and (not output.files or set(output.files) - set(deps.allowed_repair_paths)):
            raise ModelRetry("A repair may modify only the explicitly admitted source paths")
    return output


__all__ = ["validate_role_output"]
