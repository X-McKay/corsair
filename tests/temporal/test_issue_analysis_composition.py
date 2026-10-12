"""Small direct/native payload checks before any service allocation."""

import asyncio

import pytest
from pydantic_ai import models
from pydantic_ai.exceptions import UsageLimitExceeded, UserError
from pydantic_ai.usage import UsageLimits
from temporalio.converter import DataConverter
from pydantic_ai.durable_exec.temporal import PydanticAIPayloadConverter

from corsair.agents.issue_analysis import FixtureDependencies, fixture_prompt
from corsair.workflows.issue_analysis import IssueAnalysisExecution, IssueAnalysisWorkflow
from tests.temporal.test_issue_analysis_support import AGENT, EXPECTED, MODELS, inputs


class DirectConfiguredWorkflow(IssueAnalysisWorkflow):
    __pydantic_ai_agents__ = [AGENT]
    model_keys = tuple(MODELS)


def test_same_capability_agent_remains_direct_and_payload_roundtrips():
    async def check():
        with models.override_allow_model_requests(False):
            result = await DirectConfiguredWorkflow().run(inputs(), "path_traversal")
        assert result.output == EXPECTED["path_traversal"]
        assert (result.requests, result.tool_calls) == (2, 1)
        converter = DataConverter(payload_converter_class=PydanticAIPayloadConverter)
        restored, = await converter.decode(await converter.encode([result]), [IssueAnalysisExecution])
        assert restored == result
    asyncio.run(check())


@pytest.mark.parametrize("key,limit", [("unadmitted-provider", 3), ("path_traversal", 4), ("path_traversal", True)])
def test_operator_admission_refuses_before_agent_execution(key, limit):
    with pytest.raises(UserError):
        asyncio.run(DirectConfiguredWorkflow().run(inputs(), key, limit))


def test_native_direct_request_limit_remains_effective():
    async def check():
        with models.override_allow_model_requests(False), pytest.raises(UsageLimitExceeded):
            await AGENT.run(fixture_prompt(inputs()), model="path_traversal", deps=FixtureDependencies(inputs()),
                            usage_limits=UsageLimits(request_limit=1, tool_calls_limit=1, total_tokens_limit=5000))
    asyncio.run(check())
