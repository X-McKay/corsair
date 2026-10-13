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
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from corsair.ports.test_runner import (
    MAX_PATCH_FILE_BYTES, ApprovedPatch, FailureDetail, NativeTestRun, PatchFile, TestCaseResult, TestRunner,
)

from ..source.contracts import SourceExcerpt, SourceFile, SourceLine, SourceRead
from ..source.tools import READ_LINE_LIMIT, READ_SOURCE_TOOL, TOOL_RETRIES, read_saved_source
from .admission import self_observation
from .contracts import DevelopmentOutcome, DevelopmentRun, RefusedWrite, TestAuthoringInput, UnreadSource, WrittenFile

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
    # Refused writes the author may act on; the next refusal ends the stage blocked at admission.
    admission_refusals: int = 1

    def __post_init__(self):
        if type(self.dev_runs) is not int or not 1 <= self.dev_runs <= 5:
            raise ValueError("development run budget outside the admitted range 1..5")
        if type(self.admission_refusals) is not int or not 0 <= self.admission_refusals <= 2:
            raise ValueError("admission refusal budget outside the admitted range 0..2")


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

    @tools.tool(name=WRITE_TOOL, retries=TOOL_RETRIES, prepare=while_edits_can_help)
    async def write_test_file(ctx: RunContext[AuthoringDependencies],
                              path: Annotated[str, Field(description="One of the approved test paths, exactly as given")],
                              content: Annotated[str, Field(description="Complete new file content; replaces any earlier write of this path")]) -> WrittenFile | RefusedWrite:
        """Write one complete test file into the patch. Only approved test paths are accepted; application source and test configuration are never writable.

        Test code that installs audit hooks, monitoring, tracing or profiling, raises audit events, or patches file, process, network or import facilities is refused: the operator witness observes the target, and a refused write leaves the file unchanged."""
        if path not in ctx.deps.inputs.environment.approved_test_paths:
            raise ModelRetry(f"{path} is not an approved test path")
        data = content.encode()
        if len(data) > MAX_PATCH_FILE_BYTES:
            raise ModelRetry(f"test file exceeds {MAX_PATCH_FILE_BYTES} bytes")
        findings = self_observation(content)
        if findings:
            left = max(ctx.deps.budget.admission_refusals - len(refused_writes(ctx)), 0)
            return RefusedWrite(status="refused", path=path, findings=findings[:32], refusals_left=left, reason=(
                "Refused: test code must not observe, forge or replace what the operator witness observes ("
                + "; ".join(f"line {f.line}: {f.facility}" for f in findings[:8]) + "). The operator witness already "
                "records the target's calls, raised exceptions and file opens; remove these constructs and assert only "
                "the planned required behavior. The file keeps its previous content. "
                + ("Another refusal ends this stage blocked." if left else "This stage now ends blocked at admission.")))
        return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))

    @tools.tool(name=RUN_TOOL, retries=TOOL_RETRIES, sequential=True, prepare=while_edits_can_help)
    def run_tests(ctx: RunContext[AuthoringDependencies]) -> DevelopmentRun:
        """Apply the current patch to a fresh copy of the baseline source in the development sandbox, run native discovery and, when exactly the two planned tests are found, execute them once.

        Returns discovered test ids, collection or compile errors and the control outcome. The security test's pass/fail outcome is withheld; a setup error or skip is shown. Every call counts against an operator run budget; only the first call in one response runs.
        """
        deps = ctx.deps
        plan = deps.inputs.plan
        # Reserve against every run_tests call dispatched in this run, including others in the same
        # model response whose returns are not yet in history; each call gets its own operation.
        dispatched = dispatched_runs(ctx)
        if dispatched.count(ctx.tool_call_id) != 1:
            raise RuntimeError("run_tests call id must identify exactly one dispatched call in this run")
        number = dispatched.index(ctx.tool_call_id) + 1
        # Calls in one response see the same files, so a later one would repeat the first run's patch blindly,
        # including after a workspace failure with uncertain side effects; only the first runs.
        response = next(message for message in ctx.messages if isinstance(message, ModelResponse)
                        and message.run_id == ctx.run_id and any(isinstance(part, ToolCallPart)
                                                                 and part.tool_call_id == ctx.tool_call_id
                                                                 for part in message.parts))
        batched = [part.tool_call_id for part in response.parts
                   if isinstance(part, ToolCallPart) and part.tool_name == RUN_TOOL]
        files = current_files(ctx)
        if not files or number > deps.budget.dev_runs or batched[0] != ctx.tool_call_id:
            reason = ("no test file has been written" if not files
                      else f"development run budget of {deps.budget.dev_runs} is spent" if number > deps.budget.dev_runs
                      else "only the first run_tests call in one response runs; the files cannot change between them")
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


def readable_files(ctx: RunContext[AuthoringDependencies]) -> dict[str, str]:
    """Saved source plus this run's admitted test writes; a written test path shows its latest admitted content."""
    return {item.path: item.content for item in ctx.deps.source_files} | current_files(ctx)


def source_tools() -> FunctionToolset[AuthoringDependencies]:
    """Bounded windows over saved source and the author's own written tests.

    Unlike the shared reader, an absent path or a start past the end is a typed answer, not a ModelRetry: with
    no tool retries a ModelRetry ends the stage, and live authors re-read their own test file after a
    collection error (PLAN-0048 write-only run: 10 of 14 failures).
    """
    tools = FunctionToolset[AuthoringDependencies](id=SOURCE_TOOLSET_ID)

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[AuthoringDependencies],
                          path: Annotated[str, Field(description="A saved path as listed in the inventory, or an approved test path you have written")],
                          start_line: Annotated[int, Field(ge=1, description="First line, default 1; use the returned end_line plus one for the next window")] = 1) -> SourceRead | UnreadSource:
        """Read up to 80 lines from start_line of a saved source file or of a test file you wrote, stopping at the actual end of file.

        A written test path returns your latest admitted write, not the saved source. Returned numbered lines are the only coordinates that can authorize a citation.
        """
        files = readable_files(ctx)
        written = sorted(current_files(ctx))
        content = files.get(path)
        if content is None:
            approved = ctx.deps.inputs.environment.approved_test_paths
            hint = (f"{path} is an approved test path you have not written yet; write_test_file creates it"
                    if path in approved else f"{path} is neither in the saved source nor a test file you wrote")
            return UnreadSource(status="not_in_source", path=path[:256], reason=(
                f"{hint}. Readable: the saved paths in the inventory and your written test files "
                f"({', '.join(written) or 'none yet'}). run_tests already reports collection and compile errors "
                "with file and line; to change a test file, write it again in full with write_test_file.")[:4096])
        lines = content.splitlines()
        if start_line > len(lines):
            return UnreadSource(status="past_end", path=path, reason=(
                f"{path} has {len(lines)} lines; start_line {start_line} is past its end. "
                + ("Read from line 1." if lines else "The file is empty.")))
        end_line = min(start_line + READ_LINE_LIMIT - 1, len(lines))
        return SourceRead(path=path, start_line=start_line, end_line=end_line,
                          lines=tuple(SourceLine(number=number, text=lines[number - 1])
                                      for number in range(start_line, end_line + 1)))

    return tools


__all__ = ["READ_SOURCE_TOOL", "RUN_TOOL", "WRITE_TOOL", "AuthoringBudget", "AuthoringDependencies", "admission_spent",
           "approved_patch", "authoring_tools", "current_files", "development_runs", "readable_files", "refused_writes", "source_tools",
           "summarize"]
