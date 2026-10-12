"""Stage-owned tools: confined test writes into an in-history patch and capped development runs.

The patch is not held in mutable dependencies: it is rebuilt from this run's successful
write_test_file calls, so the same tools work when native durability serializes deps.
"""

from dataclasses import dataclass
from hashlib import sha256
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.toolsets import FunctionToolset

from corsair.ports.test_runner import (
    MAX_PATCH_FILE_BYTES, ApprovedPatch, FailureDetail, NativeTestRun, PatchFile, TestCaseResult, TestRunner,
)

from ..source.contracts import SourceExcerpt, SourceFile
from ..source.tools import READ_SOURCE_TOOL, TOOL_RETRIES, read_saved_source, window_source_tools
from .contracts import DevelopmentOutcome, DevelopmentRun, TestAuthoringInput, WrittenFile

WRITE_TOOL = "write_test_file"
RUN_TOOL = "run_tests"
TOOLSET_ID = "test_authoring"
SOURCE_TOOLSET_ID = "test_authoring_source"
EXCERPT = 4096


@dataclass(frozen=True)
class AuthoringBudget:
    """Operator-owned; nothing in the prompt, plan or source can change it."""
    dev_runs: int = 3
    reveal_security_outcome: bool = False

    def __post_init__(self):
        if type(self.dev_runs) is not int or not 1 <= self.dev_runs <= 5:
            raise ValueError("development run budget outside the admitted range 1..5")


@dataclass(frozen=True)
class AuthoringDependencies:
    inputs: TestAuthoringInput
    runner: TestRunner
    budget: AuthoringBudget = AuthoringBudget()

    @property
    def source_files(self) -> tuple[SourceFile, ...]:
        return self.inputs.source_files

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        return read_saved_source(self.inputs.source_files, path, start_line, end_line)


def _successful(ctx: RunContext, tool_name: str) -> list[tuple[ToolCallPart, ToolReturnPart]]:
    """Calls of tool_name in this run whose native return succeeded, in completion order."""
    calls = {part.tool_call_id: part for message in ctx.messages if isinstance(message, ModelResponse)
             for part in message.parts if isinstance(part, ToolCallPart) and part.tool_name == tool_name}
    return [(calls[part.tool_call_id], part)
            for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
            for part in message.parts if isinstance(part, ToolReturnPart) and part.tool_name == tool_name
            and part.outcome == "success" and part.tool_call_id in calls]


def current_files(ctx: RunContext) -> dict[str, str]:
    """Latest successfully written content per approved path in this run."""
    files: dict[str, str] = {}
    for call, _ in _successful(ctx, WRITE_TOOL):
        args = call.args_as_dict()
        files[args["path"]] = args["content"]
    return files


def development_runs(ctx: RunContext) -> list[DevelopmentRun]:
    return [DevelopmentRun.model_validate(ret.content) for _, ret in _successful(ctx, RUN_TOOL)]


def approved_patch(files: dict[str, str], approved: tuple[str, ...]) -> ApprovedPatch:
    return ApprovedPatch(files=tuple(PatchFile(path, content.encode()) for path, content in sorted(files.items())),
                         approved_paths=approved)


def _outcome(case: TestCaseResult | None) -> DevelopmentOutcome | None:
    if case is None:
        return None
    failure: FailureDetail | None = case.failure
    return DevelopmentOutcome(outcome=case.outcome, failure_type=failure.type if failure else None,
                              failure_path=failure.path if failure else None,
                              failure_line=failure.line if failure else None,
                              message=(failure.message if failure else "")[:EXCERPT])


def summarize(number: int, observed: NativeTestRun, *, control_id: str, security_id: str,
              reveal_security: bool) -> DevelopmentRun:
    """What the author may see: discovery, compile/collection errors and the control; never the security verdict by default."""
    discovery, execution = observed.discovery, observed.execution
    status: str = {"workspace": "workspace_failure", "discovery": "collection_error",
                   "execution": "execution_failure", "report": "report_failure", None: "discovered"}[observed.failure_layer]
    if observed.failure_layer == "discovery" and discovery is not None and discovery.status == "execution_failure":
        status = "execution_failure"
    cases = {case.test_id: case for case in (execution.cases if execution else ())}
    security = cases.get(security_id)
    if security is not None and not reveal_security:
        # A setup error or skip means the body did not run validly and says nothing about the planned
        # assertion; only the pass/fail verdict is withheld.
        security_view = _outcome(security) if security.outcome in ("error", "skipped") else "withheld"
    else:
        security_view = _outcome(security)
    errors = (discovery.errors if discovery else "") or (execution.detail if execution else "") or observed.detail
    return DevelopmentRun(
        run=number, operation=observed.operation, patch_sha256=observed.patch_sha256, status=status,
        discovered_test_ids=discovery.test_ids[:64] if discovery else (), errors=errors[:EXCERPT],
        control=_outcome(cases.get(control_id)), security=security_view,
        run_command=execution.command if execution else (), cleanup=observed.cleanup)


def authoring_tools() -> FunctionToolset[AuthoringDependencies]:
    tools = FunctionToolset[AuthoringDependencies](id=TOOLSET_ID)

    @tools.tool(name=WRITE_TOOL, retries=TOOL_RETRIES)
    async def write_test_file(ctx: RunContext[AuthoringDependencies],
                              path: Annotated[str, Field(description="One of the approved test paths, exactly as given")],
                              content: Annotated[str, Field(description="Complete new file content; replaces any earlier write of this path")]) -> WrittenFile:
        """Write one complete test file into the patch. Only approved test paths are accepted; application source and test configuration are never writable."""
        if path not in ctx.deps.inputs.environment.approved_test_paths:
            raise ModelRetry(f"{path} is not an approved test path")
        data = content.encode()
        if len(data) > MAX_PATCH_FILE_BYTES:
            raise ModelRetry(f"test file exceeds {MAX_PATCH_FILE_BYTES} bytes")
        return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))

    @tools.tool(name=RUN_TOOL, retries=TOOL_RETRIES, sequential=True)
    def run_tests(ctx: RunContext[AuthoringDependencies]) -> DevelopmentRun:
        """Apply the current patch to a fresh copy of the baseline source in the development sandbox, run native discovery and, when exactly the two planned tests are found, execute them once.

        Returns discovered test ids, collection or compile errors and the control outcome. The security test's pass/fail outcome is withheld; a setup error or skip is shown. Every call counts against an operator run budget.
        """
        deps = ctx.deps
        plan = deps.inputs.plan
        # Reserve against every run_tests call dispatched in this run, including others in the same
        # model response whose returns are not yet in history; each call gets its own operation.
        dispatched = [part.tool_call_id for message in ctx.messages
                      if isinstance(message, ModelResponse) and message.run_id == ctx.run_id
                      for part in message.parts if isinstance(part, ToolCallPart) and part.tool_name == RUN_TOOL]
        if dispatched.count(ctx.tool_call_id) != 1:
            raise RuntimeError("run_tests call id must identify exactly one dispatched call in this run")
        number = dispatched.index(ctx.tool_call_id) + 1
        files = current_files(ctx)
        if not files or number > deps.budget.dev_runs:
            reason = "no test file has been written" if not files else f"development run budget of {deps.budget.dev_runs} is spent"
            return DevelopmentRun(run=number, operation="", patch_sha256=sha256(b"").hexdigest(), status="not_run",
                                  discovered_test_ids=(), errors=reason, control=None, security=None,
                                  run_command=(), cleanup="not_required")
        patch = approved_patch(files, deps.inputs.environment.approved_test_paths)
        operation = uuid5(NAMESPACE_URL, f"corsair:test-authoring:{ctx.run_id}:{ctx.tool_call_id}")
        observed = deps.runner.run(patch, control_test_id=plan.control.test_id,
                                   security_test_id=plan.security.test_id,
                                   discovery_command=plan.discovery_command, operation=operation)
        if observed.operation != str(operation) or observed.patch_sha256 != patch.sha256:
            raise RuntimeError("runner returned an observation for a different operation or patch")
        return summarize(number, observed, control_id=plan.control.test_id, security_id=plan.security.test_id,
                         reveal_security=deps.budget.reveal_security_outcome)

    return tools


def source_tools() -> FunctionToolset:
    return window_source_tools(SOURCE_TOOLSET_ID)


__all__ = ["READ_SOURCE_TOOL", "RUN_TOOL", "WRITE_TOOL", "AuthoringBudget", "AuthoringDependencies",
           "approved_patch", "authoring_tools", "current_files", "development_runs", "source_tools", "summarize"]
