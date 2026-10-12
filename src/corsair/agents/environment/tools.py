"""Stage-owned tools: saved manifest reads and bounded commands in one preparation sandbox.

Commands run only through the vendor-free execution port under the operator's
sandbox policy and limits; no retries, and nothing runs after an unknown delivery.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Annotated, Callable
from uuid import UUID, uuid4

from pydantic import Field
from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.toolsets import FunctionToolset

from corsair.agents.issue_analysis.contracts import Contract, SourceExcerpt, SourceLine, SourceRead, confined_path
from corsair.ports.execution import ExecutionError, ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle

from .contracts import Command, CommandRecord, EnvironmentInput, Toolchain

READ_SOURCE_TOOL = "read_source"
RUN_SETUP_COMMAND_TOOL = "run_setup_command"
TOOL_RETRIES = 0
OUTPUT_TAIL_BYTES = 4096
READ_OUTPUT_BYTES = 16384


@dataclass(frozen=True)
class SetupBudget:
    """Operator-owned; nothing the model or repository says can change it."""
    max_commands: int = 12

    def __post_init__(self):
        if type(self.max_commands) is not int or not 1 <= self.max_commands <= 64:
            raise ValueError("setup command budget outside the admitted range")


@dataclass
class SetupLedger:
    """Trusted per-run record of every dispatched command and its retained output."""
    records: list[CommandRecord] = field(default_factory=list)
    outputs: dict[int, tuple[bytes, bytes]] = field(default_factory=dict)
    halted: str | None = None


@dataclass(frozen=True)
class EnvironmentDependencies:
    inputs: EnvironmentInput
    execution: SandboxExecution
    handle: SandboxHandle
    toolchain_id: str
    scratch_location: str
    budget: SetupBudget = SetupBudget()
    ledger: SetupLedger = field(default_factory=SetupLedger)
    new_operation: Callable[[], UUID] = uuid4

    def __post_init__(self):
        if self.toolchain_id not in {t.toolchain_id for t in self.inputs.toolchains}:
            raise ValueError("preparation sandbox toolchain is absent from the catalog")
        if not self.scratch_location.startswith("/"):
            raise ValueError("absolute operator scratch location required")

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        confined_path(path)
        source = next((s for s in self.inputs.source_files if s.path == path), None)
        if source is None:
            raise ValueError("source path is absent from the supplied inventory")
        lines = source.content.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines) or end_line - start_line + 1 > 80:
            raise ValueError("source line range is absent from the supplied inventory")
        return SourceExcerpt(path=path, start_line=start_line, end_line=end_line,
                             quote="\n".join(lines[start_line - 1:end_line]))


class ToolchainCatalog(Contract):
    prepared: str = Field(description="Toolchain of the preparation sandbox; commands run in this one only")
    toolchains: tuple[Toolchain, ...]


class SetupRun(Contract):
    run_id: int
    delivery: str
    completion: str
    exit_code: int | None
    failure_layer: str | None
    stdout_bytes: int
    stderr_bytes: int
    stdout_tail: str
    stderr_tail: str


class OutputSlice(Contract):
    run_id: int
    stream: str
    offset: int
    total_bytes: int
    text: str


def _record(run_id: int, command: tuple[str, ...], receipt: ExecutionReceipt) -> CommandRecord:
    return CommandRecord(run_id=run_id, command=command, operation=receipt.operation, delivery=receipt.delivery,
                         completion=receipt.completion, exit_code=receipt.native_exit,
                         failure_layer=receipt.failure_layer, stdout_sha256=sha256(receipt.stdout).hexdigest(),
                         stderr_sha256=sha256(receipt.stderr).hexdigest(), elapsed_seconds=receipt.elapsed_seconds)


def environment_tools() -> FunctionToolset[EnvironmentDependencies]:
    tools = FunctionToolset[EnvironmentDependencies](id="environment")

    @tools.tool(name=READ_SOURCE_TOOL, retries=TOOL_RETRIES)
    async def read_source(ctx: RunContext[EnvironmentDependencies],
                          path: Annotated[str, Field(description="Saved path exactly as listed in the inventory")],
                          start_line: Annotated[int, Field(ge=1, description="First saved-file line; use the returned end_line plus one for the next window")] = 1) -> SourceRead:
        """Read up to 80 saved manifest, CI or documentation lines from start_line, stopping at end of file."""
        try:
            source = next((s for s in ctx.deps.inputs.source_files if s.path == path), None)
            if source is None:
                raise ValueError("source path is absent from the supplied inventory")
            excerpt = ctx.deps.read_source(path, start_line, min(start_line + 79, len(source.content.splitlines())))
        except ValueError as exc:
            raise ToolFailed(str(exc)) from exc
        return SourceRead(path=excerpt.path, start_line=excerpt.start_line, end_line=excerpt.end_line,
                          lines=tuple(SourceLine(number=excerpt.start_line + i, text=text)
                                      for i, text in enumerate(excerpt.quote.split("\n"))))

    @tools.tool(name="list_toolchains", retries=TOOL_RETRIES)
    async def list_toolchains(ctx: RunContext[EnvironmentDependencies]) -> ToolchainCatalog:
        """List the admitted toolchain images and the one the preparation sandbox runs."""
        return ToolchainCatalog(prepared=ctx.deps.toolchain_id, toolchains=ctx.deps.inputs.toolchains)

    @tools.tool(name=RUN_SETUP_COMMAND_TOOL, retries=TOOL_RETRIES)
    async def run_setup_command(ctx: RunContext[EnvironmentDependencies],
                                command: Annotated[Command, Field(description="Argument tokens executed directly, without a shell unless the first tokens invoke one")]) -> SetupRun:
        """Run one command once in the preparation sandbox under operator limits and policy.

        Never retried. If delivery is unknown, no further command can run."""
        deps, ledger = ctx.deps, ctx.deps.ledger
        if ledger.halted:
            raise ToolFailed(ledger.halted)
        if len(ledger.records) >= deps.budget.max_commands:
            raise ToolFailed("operator setup command budget exhausted")
        command = tuple(command)
        operation = deps.new_operation()
        try:
            receipt = deps.execution.execute(deps.handle, command, operation)
        except ExecutionError as error:
            receipt = error.receipt
        run_id = len(ledger.records) + 1
        ledger.records.append(_record(run_id, command, receipt))
        ledger.outputs[run_id] = (receipt.stdout, receipt.stderr)
        if receipt.delivery != "acknowledged" or receipt.completion != "terminal_observed":
            ledger.halted = f"run {run_id} delivery {receipt.delivery}, completion {receipt.completion}: no further commands"
        return SetupRun(run_id=run_id, delivery=receipt.delivery, completion=receipt.completion,
                        exit_code=receipt.native_exit, failure_layer=receipt.failure_layer,
                        stdout_bytes=len(receipt.stdout), stderr_bytes=len(receipt.stderr),
                        stdout_tail=receipt.stdout[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"),
                        stderr_tail=receipt.stderr[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"))

    @tools.tool(name="read_output", retries=TOOL_RETRIES)
    async def read_output(ctx: RunContext[EnvironmentDependencies], run_id: int,
                          stream: Annotated[str, Field(pattern="^(stdout|stderr)$")],
                          offset: Annotated[int, Field(ge=0)] = 0) -> OutputSlice:
        """Read up to 16 KiB of a previous run's retained output from a byte offset."""
        if run_id not in ctx.deps.ledger.outputs:
            raise ToolFailed("unknown run_id")
        data = ctx.deps.ledger.outputs[run_id][stream == "stderr"]
        return OutputSlice(run_id=run_id, stream=stream, offset=offset, total_bytes=len(data),
                           text=data[offset:offset + READ_OUTPUT_BYTES].decode("utf-8", "replace"))

    return tools
