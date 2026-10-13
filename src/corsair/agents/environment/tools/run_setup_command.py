"""run_setup_command: one bounded command in the preparation sandbox, recorded in the trusted ledger.

No retries, and nothing runs after an unknown delivery or an execution error.
"""

from hashlib import sha256
import re
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext, ToolFailed

from corsair.agents.issue_analysis.contracts import Contract
from corsair.core.blockers import Blocker
from corsair.ports.execution import ExecutionError, ExecutionReceipt
from ..diagnostics import budget_blocker, setup_blocker
from ..contracts import Command, CommandRecord
from ..dependencies import EnvironmentDependencies

RUN_SETUP_COMMAND_TOOL = "run_setup_command"
OUTPUT_TAIL_BYTES = 4096


class Correction(Contract):
    run_id: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class SetupRun(Contract):
    correction_available: bool = False
    diagnostic: Blocker | None = None
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


def _pytest_prefix(command: tuple[str, ...]) -> tuple[str, ...] | None:
    if command[0] == "pytest":
        return command[:1]
    if len(command) >= 3 and re.fullmatch(r"python(?:3(?:\.\d+)?)?", command[0]) and command[1:3] == ("-m", "pytest"):
        return command[:3]
    return None


def _correctable(command: tuple[str, ...], receipt: ExecutionReceipt, diagnostic: Blocker) -> bool:
    # Symptoms permit a bounded correction, never establish absence of side effects.
    # Infrastructure and recognized operator/dependency blockers take precedence.
    if diagnostic.code != "setup_command_failed":
        return False
    output = (receipt.stdout[-16384:] + b"\n" + receipt.stderr[-16384:]).lower()
    if command[0] == "mvn" and receipt.native_exit == 127:
        return b"not found" in output or b"no such file" in output
    return bool(_pytest_prefix(command) and receipt.native_exit == 4 and b"unrecognized arguments:" in output)


def _valid_correction(previous: tuple[str, ...], command: tuple[str, ...]) -> bool:
    if previous[0] == "mvn":
        return command == ("./mvnw", *previous[1:])
    prefix = _pytest_prefix(previous)
    return bool(prefix and _pytest_prefix(command) == prefix and command != previous)


async def run_setup_command(ctx: RunContext[EnvironmentDependencies],
                            command: Annotated[Command, Field(description="Argument tokens executed directly, without a shell unless the first tokens invoke one")],
                            correction: Correction | None = None) -> SetupRun:
    """Run one command once in the preparation sandbox under operator limits and policy.

    Never automatically retried. A returned correction_available permits one changed invocation
    citing that run and explaining the correction. Other failures stop command execution."""
    deps, ledger = ctx.deps, ctx.deps.ledger
    if ledger.halted:
        raise ToolFailed(ledger.halted)
    if len(ledger.records) >= deps.budget.max_commands:
        diagnostic = budget_blocker()
        if not any(d.code == diagnostic.code for d in ledger.diagnostics):
            ledger.diagnostics.append(diagnostic)
        # Nothing was dispatched: preserve already-complete successful evidence.
        raise ToolFailed(diagnostic.render())
    command = tuple(command)
    if any(r.command == command and r.exit_code != 0 for r in ledger.records):
        raise ToolFailed("This invocation already failed; do not repeat it.")
    if ledger.pending_correction is not None:
        previous = ledger.records[ledger.pending_correction - 1]
        if correction is None or correction.run_id != previous.run_id or not correction.reason.strip():
            raise ToolFailed("Inspect the failed run and provide correction with its run_id and a specific reason.")
        if not _valid_correction(previous.command, command):
            raise ToolFailed("Correction must change pytest arguments under the same executable, or replace mvn with ./mvnw keeping its arguments; no identical retry or other command.")
        ledger.corrections_used += 1
    elif correction is not None:
        raise ToolFailed("No failed invocation is awaiting correction.")
    operation = deps.new_operation()
    error = None
    try:
        receipt = deps.execution.execute(deps.handle, command, operation)
    except ExecutionError as failure:
        # Journal loss or unconfirmed cleanup can accompany exit 0; the run is still failed evidence.
        receipt, error = failure.receipt, str(failure)
    run_id = len(ledger.records) + 1
    diagnostic = setup_blocker(receipt, run_id, error)
    # A native infrastructure failure can accompany exit zero or empty output.
    # Give the finalizer a trusted, citeable error without copying private native detail.
    if diagnostic and diagnostic.certainty == "observed" and not error:
        error = diagnostic.summary
    ledger.records.append(_record(run_id, command, receipt, error))
    ledger.outputs[run_id] = (receipt.stdout, receipt.stderr)
    ledger.pending_correction = None
    if diagnostic:
        ledger.diagnostics.append(diagnostic)
        if (_correctable(command, receipt, diagnostic) and ledger.corrections_used < deps.budget.max_corrections
                and len(ledger.records) < deps.budget.max_commands):
            ledger.pending_correction = run_id
        else:
            ledger.halted = diagnostic.render() + "\nNo further setup commands in this attempt."

    return SetupRun(correction_available=ledger.pending_correction == run_id, diagnostic=diagnostic, run_id=run_id, delivery=receipt.delivery, completion=receipt.completion,
                    exit_code=receipt.native_exit, failure_layer=receipt.failure_layer, execution_error=error,
                    stdout_bytes=len(receipt.stdout), stderr_bytes=len(receipt.stderr),
                    stdout_tail=receipt.stdout[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"),
                    stderr_tail=receipt.stderr[-OUTPUT_TAIL_BYTES:].decode("utf-8", "replace"))
