"""Native workflow method reused by an explicitly configured top-level workflow."""

from dataclasses import dataclass
from typing import ClassVar

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pydantic_ai.durable_exec.temporal import PydanticAIWorkflow
    from pydantic_ai.exceptions import UserError
    from pydantic_ai.usage import UsageLimits

    from corsair.agents.issue_analysis import (
        FixtureDependencies, IssueAnalysis, IssueAnalysisInput, fixture_prompt,
    )


@dataclass(frozen=True)
class IssueAnalysisExecution:
    output: IssueAnalysis
    requests: int
    tool_calls: int
    input_tokens: int
    output_tokens: int


class IssueAnalysisWorkflow(PydanticAIWorkflow):
    """Concrete workflows register exactly one existing agent and admitted model keys."""

    model_keys: ClassVar[tuple[str, ...]]

    async def run(self, inputs: IssueAnalysisInput, model_key: str,
                  request_limit: int = 3) -> IssueAnalysisExecution:
        if len(self.__pydantic_ai_agents__) != 1:
            raise UserError("Issue analysis requires exactly one configured agent")
        if model_key not in self.model_keys:
            raise UserError("Model key is not admitted by this workflow configuration")
        if type(request_limit) is not int or not 1 <= request_limit <= 3:
            raise UserError("Operator request limit must be between one and three")
        agent = self.__pydantic_ai_agents__[0]
        result = await agent.run(
            fixture_prompt(inputs), model=model_key, deps=FixtureDependencies(inputs),
            usage_limits=UsageLimits(request_limit=request_limit, tool_calls_limit=1,
                                     total_tokens_limit=5000),
        )
        return IssueAnalysisExecution(result.output, result.usage.requests, result.usage.tool_calls,
                                      result.usage.input_tokens, result.usage.output_tokens)
