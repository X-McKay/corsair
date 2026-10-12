"""Native workflow method reused by an explicitly configured top-level workflow."""

import time
from dataclasses import dataclass
from typing import ClassVar, Literal

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from pydantic_ai.durable_exec.temporal import PydanticAIWorkflow
    from pydantic_ai.messages import ModelResponse, RetryPromptPart
    from pydantic_ai.usage import UsageLimits

    from corsair.agents.issue_analysis import (
        FixtureDependencies, IssueAnalysis, IssueAnalysisInput, fixture_prompt,
    )


@dataclass(frozen=True)
class IssueAnalysisBudget:
    """Operator-owned native usage limits for one agent run; recorded in workflow history."""

    request_limit: int
    tool_calls_limit: int
    total_tokens_limit: int

    def within(self, ceiling: "IssueAnalysisBudget") -> bool:
        values = (self.request_limit, self.tool_calls_limit, self.total_tokens_limit)
        limits = (ceiling.request_limit, ceiling.tool_calls_limit, ceiling.total_tokens_limit)
        return (all(type(value) is int for value in values)
                and self.request_limit >= 1 and self.tool_calls_limit >= 0 and self.total_tokens_limit >= 1
                and all(value <= limit for value, limit in zip(values, limits)))


@dataclass(frozen=True)
class IssueAnalysisRequest:
    inputs: IssueAnalysisInput
    model_key: str
    budget: IssueAnalysisBudget


@dataclass(frozen=True)
class IssueAnalysisExecution:
    """Result plus native run accounting; token counts are None when no response reported usage.

    `output_corrections` counts every native retry prompt the run sent (output validation,
    schema or unknown-tool refusals). `elapsed_seconds` is replay-safe workflow time in durable
    mode (it advances per workflow task) and host monotonic time in direct mode.
    """

    output: IssueAnalysis
    run_id: str
    mode: Literal["direct", "durable"]
    requests: int
    tool_calls: int
    usage_reported: bool
    input_tokens: int | None
    output_tokens: int | None
    output_corrections: int
    elapsed_seconds: float


def _clock() -> float:
    # Workflow time is deterministic under replay; the host clock is only read outside workflows.
    return workflow.time() if workflow.in_workflow() else time.monotonic()


def _refusal(kind: str, message: str) -> ApplicationError:
    # A FailureError fails the workflow (not the task), so admission refusals close attributably.
    return ApplicationError(message, type=kind, non_retryable=True)


class IssueAnalysisWorkflow(PydanticAIWorkflow):
    """Concrete workflows register exactly one existing agent, admitted model keys and a ceiling.

    The concrete `@workflow.defn(name=...)` name is a frozen replay contract, as is the single
    `IssueAnalysisRequest` parameter.
    """

    model_keys: ClassVar[tuple[str, ...]]
    budget_ceiling: ClassVar[IssueAnalysisBudget]

    async def run(self, request: IssueAnalysisRequest) -> IssueAnalysisExecution:
        """Run the configured agent once within an admitted operator budget.

        Temporal applies parameter type hints only when the payload count equals the parameter
        count; positional or defaulted parameters therefore decoded as untyped dicts. One frozen
        request dataclass is the documented form and records inputs, model key and budget in
        history. Refusals are non-retryable `ApplicationError`s typed `AgentConfigurationInvalid`,
        `ModelKeyNotAdmitted` or `BudgetNotAdmitted`, raised before any model or tool request.
        """
        agents = getattr(self, "__pydantic_ai_agents__", ())
        if len(agents) != 1:
            raise _refusal("AgentConfigurationInvalid", "Issue analysis requires exactly one configured agent")
        if request.model_key not in getattr(self, "model_keys", ()):
            raise _refusal("ModelKeyNotAdmitted", "Model key is not admitted by this workflow configuration")
        ceiling = getattr(self, "budget_ceiling", None)
        budget = request.budget
        if (not isinstance(ceiling, IssueAnalysisBudget) or not isinstance(budget, IssueAnalysisBudget)
                or not budget.within(ceiling)):
            raise _refusal("BudgetNotAdmitted", "Requested budget is not within the operator ceiling")
        mode: Literal["direct", "durable"] = "durable" if workflow.in_workflow() else "direct"
        started = _clock()
        result = await agents[0].run(
            fixture_prompt(request.inputs), model=request.model_key, deps=FixtureDependencies(request.inputs),
            usage_limits=UsageLimits(request_limit=budget.request_limit, tool_calls_limit=budget.tool_calls_limit,
                                     total_tokens_limit=budget.total_tokens_limit),
        )
        elapsed = _clock() - started
        messages = result.new_messages()
        responses = [message for message in messages if isinstance(message, ModelResponse)]
        reported = bool(responses) and all(response.usage.has_values() for response in responses)
        usage = result.usage
        return IssueAnalysisExecution(
            output=result.output, run_id=result.run_id, mode=mode,
            requests=usage.requests, tool_calls=usage.tool_calls, usage_reported=reported,
            input_tokens=usage.input_tokens if reported else None,
            output_tokens=usage.output_tokens if reported else None,
            output_corrections=sum(isinstance(part, RetryPromptPart) for message in messages
                                   for part in message.parts),
            elapsed_seconds=elapsed,
        )
