"""The producer's bounded workspace shell tool."""

from __future__ import annotations

import time

from pydantic_ai import Agent, RunContext

from corsair.agents.producer.dependencies import ProducerDeps

BASH_TIMEOUT_S = 180.0
BASH_TAIL = 6000


def register_bash(agent: Agent[ProducerDeps, str]) -> None:
    """Register the SDK tool that observes the disposable producer workspace."""

    @agent.tool
    def bash(ctx: RunContext[ProducerDeps], command: str) -> str:
        """Run a shell command in your working sandbox (repository at /work). Output is truncated."""
        deps = ctx.deps
        if deps.bash_calls >= deps.max_bash_calls:
            return (
                f"Shell budget of {deps.max_bash_calls} commands is spent. Write the probe from what you have read "
                "and call submit; the kernel's gates are the evidence, not further exploration."
            )
        deps.bash_calls += 1
        before = deps.backend.workspace_state(deps.work)
        started = time.monotonic()
        result = deps.backend.exec_once(
            deps.work, ["bash", "-lc", command], workdir="/work", timeout=BASH_TIMEOUT_S
        )
        after = deps.backend.workspace_state(deps.work)
        changed = (
            sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
            if before is not None and after is not None
            else None
        )
        deps.observations.append(
            {
                "tool": "bash",
                "call": deps.bash_calls,
                "duration_s": time.monotonic() - started,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "container_failed": result.container_failed,
                "file_changes": changed,
                "stdout": deps.verification.artifacts.put(result.stdout).model_dump(mode="json"),
                "stderr": deps.verification.artifacts.put(result.stderr).model_dump(mode="json"),
            }
        )
        status = (
            "timed out"
            if result.timed_out
            else "container failed"
            if result.container_failed
            else f"exit {result.exit_code}"
        )
        out = result.stdout.decode(errors="replace")[-BASH_TAIL:]
        err = result.stderr.decode(errors="replace")[-BASH_TAIL:]
        return f"$ {command}\n[{status}]\n{out}" + (f"\n--- stderr ---\n{err}" if err else "")
