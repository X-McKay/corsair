"""run_setup_command: one bounded command in the preparation sandbox, recorded in the trusted ledger.

No retries, and nothing runs after an unknown delivery or an execution error.
"""

from hashlib import sha256
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext, ToolFailed

from corsair.agents.issue_analysis.contracts import Contract
from corsair.ports.execution import ExecutionError, ExecutionReceipt

from ..contracts import Command, CommandRecord
from ..dependencies import EnvironmentDependencies

RUN_SETUP_COMMAND_TOOL = "run_setup_command"
OUTPUT_TAIL_BYTES = 4096


class SetupRun(Contract):
    run_id: int
    delivery: str
    completion: str
    exit_code: int | None
    failure_layer: str | None
    execution_error: str | None
    stdout_bytes: int
    stderr_bytes: int
    stdout_tail: str
    stderr_tail: str


def _record(run_id: int, command: tuple[str, ...], receipt: ExecutionReceipt, error: str | None) -> CommandRecord:
    return CommandRecord(run_id=run_id, command=command, operation=receipt.operation, delivery=receipt.delivery,
                         completion=receipt.completion, exit_code=receipt.native_exit,
                         failure_layer=receipt.failure_layer, execution_error=error, stdout_sha256=sha256(receipt.stdout).hexdigest(),
                         stderr_sha256=sha256(receipt.stderr).hexdigest(), elapsed_seconds=receipt.elapsed_seconds)


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
    error = None
    try:
        receipt = deps.execution.execute(deps.handle, command, operation)
    except ExecutionError as failure:
        # Journal loss or unconfirmed cleanup can accompany exit 0; the run is still failed evidence.
        receipt, error = failure.receipt, str(failure)
    run_id = len(ledger.records) + 1
    ledger.records.append(_record(run_id, command, receipt, error))
    ledger.outputs[run_id] = (receipt.stdout, receipt.stderr)
    if error or receipt.delivery != "acknowledged" or receipt.completion != "terminal_observed":
        ledger.halted = (f"run {run_id} delivery {receipt.delivery}, completion {receipt.completion}, "
                         f"execution error {error}: no further commands")
    return SetupRun(run_id=run_id, delivery=receipt.delivery, completion=receipt.completion,
                    exit_code=receipt.native_exit, failure_layer=receipt.failure_layer, execution_error=error,
                    stdout_bytes=len(receipt.stdout), stderr_bytes=len(receipt.stderr),
                    stdout_tail=receipt.stdout[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"),
                    stderr_tail=receipt.stderr[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"))
