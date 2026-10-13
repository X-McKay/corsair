"""This run's writes, refusals and development runs, read back from native message history; never offered as tools."""

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from corsair.ports.test_runner import ApprovedPatch, PatchFile

from ..contracts import DevelopmentRun, RefusedWrite
from ..dependencies import AuthoringDependencies

WRITE_TOOL = "write_test_file"
RUN_TOOL = "run_tests"


def _successful(ctx: RunContext, tool_name: str) -> list[tuple[ToolCallPart, ToolReturnPart]]:
    """Calls of tool_name in this run whose native return succeeded, in completion order."""
    calls = {part.tool_call_id: part for message in ctx.messages if isinstance(message, ModelResponse)
             for part in message.parts if isinstance(part, ToolCallPart) and part.tool_name == tool_name}
    return [(calls[part.tool_call_id], part)
            for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolReturnPart) and part.tool_name == tool_name
            and part.outcome == "success" and part.tool_call_id in calls]


def _refused(content) -> bool:
    status = content.get("status") if isinstance(content, dict) else getattr(content, "status", None)
    return status == "refused"


def current_files(ctx: RunContext) -> dict[str, str]:
    """Latest admitted content per approved path in this run; a refused write leaves the previous content."""
    files: dict[str, str] = {}
    for call, ret in _successful(ctx, WRITE_TOOL):
        if not _refused(ret.content):
            args = call.args_as_dict()
            files[args["path"]] = args["content"]
    return files


def refused_writes(ctx: RunContext) -> list[RefusedWrite]:
    return [RefusedWrite.model_validate(ret.content) for _, ret in _successful(ctx, WRITE_TOOL) if _refused(ret.content)]


def admission_spent(ctx: RunContext[AuthoringDependencies]) -> bool:
    return len(refused_writes(ctx)) > ctx.deps.budget.admission_refusals


def development_runs(ctx: RunContext) -> list[DevelopmentRun]:
    return [DevelopmentRun.model_validate(ret.content) for _, ret in _successful(ctx, RUN_TOOL)]


def dispatched_runs(ctx: RunContext) -> list[str | None]:
    """Ids of every run_tests call dispatched in this run, including ones whose returns are not yet in history."""
    return [part.tool_call_id for message in ctx.messages
            if isinstance(message, ModelResponse) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolCallPart) and part.tool_name == RUN_TOOL]


def approved_patch(files: dict[str, str], approved: tuple[str, ...]) -> ApprovedPatch:
    return ApprovedPatch(files=tuple(PatchFile(path, content.encode()) for path, content in sorted(files.items())),
                         approved_paths=approved)


def readable_files(ctx: RunContext[AuthoringDependencies]) -> dict[str, str]:
    """Saved source plus this run's admitted test writes; a written test path shows its latest admitted content."""
    return {item.path: item.content for item in ctx.deps.source_files} | current_files(ctx)
