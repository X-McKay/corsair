"""The Prober's only write, and the code checks that turn its final answer into a ``ProbeDraft``.

``write_test_file`` writes nothing to disk and admits only the one path the brief assigns; an admitted call is
recorded in the run's native message history. Finalisation reads the last admitted write back from
that history rather than from mutable deps, so it is the same in direct mode and inside a durable activity.

The protocol checks are substring checks on names every language spells the same way (the two environment
variables and the planned test name). Whether the markers are the first and last statements, whether the ``check``
marker is computed from the asserted condition, and whether the token is used only as the assertion message needs
reading the code; that is the Reviewer's job, not this one.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from ...contracts import ProbeBrief, ProbeDraft

MARKER_ENV = "CORSAIR_MARKER_DIR"
TOKEN_ENV = "CORSAIR_TOKEN"
MAX_SOURCE = 64_000
WRITE_TOOL = "write_test_file"
WRITTEN = "written"


class ProbeDeps(BaseModel):
    """Serialisable run dependencies: the one brief, and the digest a correction revises. The source tree is the
    run's workspace, not a dependency."""

    model_config = ConfigDict(frozen=True)

    brief: ProbeBrief
    revision_of: str | None = None


class DraftAnswer(BaseModel):
    """What the model returns after writing: drafted, or blocked with the missing evidence named."""

    status: Literal["drafted", "blocked"]
    note: str = Field(default="", max_length=2_000, description="For blocked: what the source cannot support")


def protocol_defects(role: str, test_name: str, source: str) -> list[str]:
    """Both roles follow one protocol, so ``role`` does not change the checks."""
    defects = []
    if not source.strip():
        defects.append("the file is empty")
    if len(source) > MAX_SOURCE:
        defects.append(f"the file is longer than {MAX_SOURCE} characters")
    if MARKER_ENV not in source:
        defects.append(f"the test never reads {MARKER_ENV}, so it cannot write the start, check and end marker files")
    if TOKEN_ENV not in source:
        defects.append(f"the test never reads {TOKEN_ENV} for its main assertion's failure message")
    if test_name not in source:
        defects.append(f"the planned test name {test_name} does not appear in the file")
    return defects


async def write_test_file(ctx: RunContext[ProbeDeps], path: str, content: str) -> str:
    """Write the complete content of your one assigned test file, replacing any earlier write."""
    brief = ctx.deps.brief
    if path.strip().removeprefix("./") != brief.test_file:
        return f"refused, nothing written: you may write only your assigned test file {brief.test_file}"
    defects = protocol_defects(brief.role, brief.test_name, content)
    if defects:
        return "refused, nothing written: " + "; ".join(defects)
    digest = sha256(content.encode()).hexdigest()
    return f"{WRITTEN} {brief.test_file} ({len(content.encode())} bytes, sha256 {digest})"


def last_write(messages) -> str | None:
    """The content of the last ``write_test_file`` call the tool admitted, from native run history."""
    calls = {part.tool_call_id: part for message in messages if isinstance(message, ModelResponse)
             for part in message.parts if isinstance(part, ToolCallPart) and part.tool_name == WRITE_TOOL}
    content = None
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if (isinstance(part, ToolReturnPart) and part.tool_name == WRITE_TOOL
                    and str(part.content).startswith(WRITTEN) and part.tool_call_id in calls):
                content = calls[part.tool_call_id].args_as_dict().get("content")
    return content if isinstance(content, str) else None


async def finalize_draft(ctx: RunContext[ProbeDeps], answer: DraftAnswer) -> ProbeDraft | None:
    """Drafted requires an admitted write that still meets the protocol; blocked returns no draft."""
    if answer.status == "blocked":
        return None
    brief = ctx.deps.brief
    source = last_write(ctx.messages)
    if source is None:
        raise ModelRetry(f"drafted requires a successful {WRITE_TOOL} call first; write the whole file, "
                         "or answer blocked")
    if defects := protocol_defects(brief.role, brief.test_name, source):
        raise ModelRetry("the written file has defects: " + "; ".join(defects))
    return ProbeDraft(role=brief.role, test_file=brief.test_file, test_name=brief.test_name, source=source,
                      revision_of=ctx.deps.revision_of)


__all__ = ["DraftAnswer", "MARKER_ENV", "ProbeDeps", "TOKEN_ENV", "finalize_draft", "last_write",
           "protocol_defects", "write_test_file"]
