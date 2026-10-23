"""The producer's verification-submission SDK tool."""

from __future__ import annotations

from pydantic_ai import Agent, ModelRetry, RunContext

from corsair.agents.producer.dependencies import ProducerDeps
from corsair.agents.producer.types import BudgetExhausted, NegativeThresholdReached
from corsair.domain.policy import negative_verdict
from corsair.domain.verification import Fix, Submission


def register_submit(agent: Agent[ProducerDeps, str], *, retries: int) -> None:
    """Register the SDK tool that submits a candidate to trusted verification."""

    @agent.tool(retries=retries)
    async def submit(ctx: RunContext[ProducerDeps], submission: Submission) -> str:
        """Submit the hypothesis, build_script and probe to the verdict kernel. Returns VERIFIED, or raises with the
        failed gate and reason so you can correct the probe and submit again."""
        deps = ctx.deps
        if deps.verdict is not None and deps.verdict.fix is Fix.VERIFIED:
            return "VERIFIED already; stop and reply with one sentence."
        if len(deps.evaluations) >= deps.max_submissions:
            raise BudgetExhausted(f"{deps.max_submissions} submission(s) evaluated; none verified")
        evaluation = await deps.verification.evaluate(submission)
        deps.evaluations.append(evaluation)
        if deps.checkpoint is not None:
            deps.checkpoint(evaluation)
        gate = evaluation.gate
        remaining = deps.max_submissions - len(deps.evaluations)
        if evaluation.verdict is not None:
            deps.verdict = evaluation.verdict
            if gate.passed or remaining <= 0:
                return (
                    f"VERIFIED: {evaluation.verdict.reason}. Fix: {evaluation.verdict.fix} "
                    f"({evaluation.verdict.fix_reason}). Reply with one sentence."
                )
            raise ModelRetry(
                f"[VERIFIED, BUT {gate.stage}]\nReason: {gate.reason}\nSubmissions left: {remaining}. "
                "Correct the probe and submit again, or reply with one sentence to keep this result."
            )
        if negative_verdict(deps.evaluations, deps.negative_threshold) is not None:
            raise NegativeThresholdReached(f"{deps.negative_threshold} distinct clean negative(s) observed")
        detail = f"[KERNEL REJECTED AT {gate.stage}]\nReason: {gate.reason}"
        if gate.stdout_tail:
            detail += f"\nstdout: {gate.stdout_tail}"
        if gate.stderr_tail:
            detail += f"\nstderr: {gate.stderr_tail}"
        detail += f"\nSubmissions left: {remaining}. Fix exactly this and call submit again."
        raise ModelRetry(detail)
