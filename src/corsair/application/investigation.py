"""Application orchestration for a producer investigation."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from pydantic_ai import UnexpectedModelBehavior, UsageLimitExceeded, UsageLimits, capture_run_messages
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model

from corsair.agents.producer.agent import build_producer
from corsair.agents.producer.dependencies import NEGATIVE_THRESHOLD, SKILLS_DIR, ProducerDeps
from corsair.agents.producer.types import BudgetExhausted, NegativeThresholdReached, ProducerRun
from corsair.agents.resources import skill_inventory, validate_agent_spec
from corsair.domain.case import Case
from corsair.domain.policy import negative_verdict, terminal_verdict
from corsair.domain.verification import Evaluation, Fix, Gate, GateVerdict, Label, Verdict
from corsair.ports.sandbox import Sandboxes, SandboxSpec, labels
from corsair.ports.verification import Verification
from corsair.runtime.matrix import Row


def render_case(case: Case, row: Row) -> str:
    """Render only finding and runtime facts; never expose an oracle to the producer."""
    finding = case.finding
    lines = [f"Finding: {finding.title}", f"Description: {finding.description or '(none)'}"]
    if finding.file_path:
        lines.append(
            f"Reported file: {finding.file_path}"
            + (f" line {finding.start_line}" if finding.start_line else "")
        )
    if finding.symbol:
        lines.append(f"Reported symbol: {finding.symbol}")
    if finding.cwe:
        lines.append(f"Reported weakness: {finding.cwe}")
    lines.append(
        f"Runtime: {row.language} / {row.framework}, image {row.image}. The repository root is /work."
    )
    lines.append(
        "A fixed revision exists and will be checked by the kernel."
        if case.fixed_revision
        else "No fixed revision is available."
    )
    return "\n".join(lines)


async def investigate(
    case: Case,
    row: Row,
    *,
    model: Model,
    kernel: Verification,
    backend: Sandboxes,
    max_submissions: int = 4,
    max_bash_calls: int = 12,
    request_limit: int = 60,
    total_tokens_limit: int | None = 400_000,
    skills_dir: Path = SKILLS_DIR,
    negative_threshold: int = NEGATIVE_THRESHOLD,
    checkpoint: Callable[[Evaluation], None] | None = None,
) -> ProducerRun:
    """Create the working sandbox, run the producer, and decide the verdict from trusted observations."""
    if min(negative_threshold, max_submissions, request_limit) < 1 or max_bash_calls < 0:
        raise ValueError(
            "submission, request and negative limits must be positive; shell limit must be nonnegative"
        )
    if total_tokens_limit is not None and total_tokens_limit < 1:
        raise ValueError("token limit must be positive when configured")
    producer_spec = validate_agent_spec(
        "corsair.agents.producer", tool_names=("bash", "read_skill", "submit")
    )
    allowed_skills = skill_inventory(skills_dir)
    if tuple(sorted(allowed_skills)) != tuple(sorted(producer_spec.skills)):
        raise ValueError("producer skill capability drift")
    started = time.monotonic()
    spec = SandboxSpec(
        image=row.image, workdir="/work", labels=labels(kernel.run_id, "work"), network="build"
    )
    deps = ProducerDeps(
        verification=kernel,
        backend=backend,
        work=spec.name,
        skills_dir=skills_dir,
        allowed_skills=allowed_skills,
        max_submissions=max_submissions,
        max_bash_calls=max_bash_calls,
        negative_threshold=negative_threshold,
        checkpoint=checkpoint,
    )
    final_text = error = None
    result = None
    budget_stop = False
    early_stop: str | None = None
    messages: list = []
    ours = True
    try:
        backend.create(spec)
        backend.copy_tree_in(spec.name, Path(case.revision.source), "/work")
        agent = build_producer(model, max_submissions=max_submissions)
        try:
            with capture_run_messages() as messages:
                result = await agent.run(
                    render_case(case, row),
                    deps=deps,
                    usage_limits=UsageLimits(
                        request_limit=request_limit, total_tokens_limit=total_tokens_limit
                    ),
                )
            final_text = result.output
        except NegativeThresholdReached:
            early_stop = "negative_threshold"
        except (BudgetExhausted, UnexpectedModelBehavior, UsageLimitExceeded) as failure:
            error = f"{type(failure).__name__}: {failure}"[:2000]
            budget_stop = True
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"[:2000]
    except Exception as failure:
        from corsair.ports.sandbox import SandboxExists

        ours = not isinstance(failure, SandboxExists)
        error = f"{type(failure).__name__}: {failure}"[:2000]
    finally:
        confirmed = backend.remove(spec.name) if ours else None
    responses = [message for message in messages if isinstance(message, ModelResponse)]
    requests = len(responses) if responses else (result.usage.requests if result is not None else None)
    input_tokens = sum(response.usage.input_tokens or 0 for response in responses) if responses else None
    output_tokens = sum(response.usage.output_tokens or 0 for response in responses) if responses else None
    tool_calls = sum(len(response.tool_calls) for response in responses) if responses else None
    negatives = negative_verdict(deps.evaluations, negative_threshold)
    if deps.verdict is not None:
        verdict = deps.verdict
    elif negatives is not None:
        verdict = negatives
    elif deps.evaluations:
        verdict = terminal_verdict(deps.evaluations[-1].gate, len(deps.evaluations))
    elif error and not budget_stop:
        verdict = terminal_verdict(
            GateVerdict(passed=False, stage=Gate.INFRA, reason=f"producer made no submission: {error}"), 0
        )
    elif error:
        verdict = Verdict(
            label=Label.INCONCLUSIVE,
            rule="K3",
            fix=Fix.NOT_APPLICABLE,
            reason=f"the producer's budget ended the run before any submission: {error[:1500]}",
        )
    else:
        verdict = Verdict(
            label=Label.INCONCLUSIVE,
            rule="K3",
            fix=Fix.NOT_APPLICABLE,
            reason=f"the producer ended without a submission: {(final_text or '')[:1500]}",
        )
    return ProducerRun(
        verdict=verdict,
        evaluations=tuple(deps.evaluations),
        requests=requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        bash_calls=deps.bash_calls,
        duration_s=time.monotonic() - started,
        final_text=final_text,
        error=error,
        cleanup_confirmed=confirmed,
        early_stop=early_stop,
        observations=tuple(deps.observations),
    )
