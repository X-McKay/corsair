"""Small direct/native payload checks before any service allocation."""

import asyncio
from dataclasses import replace

import pytest
from pydantic_ai import capture_run_messages, models
from pydantic_ai.durable_exec.temporal import PydanticAIPayloadConverter, TemporalDurability
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.usage import RequestUsage, UsageLimits
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError

from corsair.agents.issue_analysis import FixtureDependencies, create_issue_analysis_agent, fixture_prompt
from corsair.workflows.issue_analysis import (
    IssueAnalysisExecution, IssueAnalysisRequest, IssueAnalysisWorkflow,
)
from tests.temporal.test_issue_analysis_support import (
    ACTIVITY_CONFIG, BUDGET, EXPECTED, MODELS, admitted, fixture_agent, inputs,
)


@admitted
class DirectConfiguredWorkflow(IssueAnalysisWorkflow):
    __pydantic_ai_agents__ = [fixture_agent()]
    model_keys = tuple(MODELS)
    budget_ceiling = BUDGET


def test_same_capability_agent_remains_direct_and_payload_roundtrips():
    async def check():
        request = IssueAnalysisRequest(inputs(), "path_traversal", BUDGET)
        with models.override_allow_model_requests(False):
            result = await DirectConfiguredWorkflow().run(request)
        assert result.output == EXPECTED["path_traversal"]
        assert (result.requests, result.tool_calls, result.output_corrections) == (2, 1, 0)
        assert result.mode == "direct" and result.run_id and result.elapsed_seconds >= 0
        # Fixture models report estimated usage, so it is present rather than unknown.
        assert result.usage_reported and result.input_tokens > 0 and result.output_tokens > 0
        converter = DataConverter(payload_converter_class=PydanticAIPayloadConverter)
        restored, restored_request = await converter.decode(
            await converter.encode([result, request]), [IssueAnalysisExecution, IssueAnalysisRequest])
        assert (restored, restored_request) == (result, request)
    asyncio.run(check())


@pytest.mark.parametrize("key,budget,failure_type", [
    ("unadmitted-provider", BUDGET, "ModelKeyNotAdmitted"),
    ("path_traversal", replace(BUDGET, request_limit=4), "BudgetNotAdmitted"),
    ("path_traversal", replace(BUDGET, request_limit=True), "BudgetNotAdmitted"),
    ("path_traversal", replace(BUDGET, request_limit=0), "BudgetNotAdmitted"),
    ("path_traversal", replace(BUDGET, tool_calls_limit=2), "BudgetNotAdmitted"),
    ("path_traversal", replace(BUDGET, total_tokens_limit=5001), "BudgetNotAdmitted"),
])
def test_operator_admission_refuses_before_agent_execution(key, budget, failure_type):
    with capture_run_messages() as messages, pytest.raises(ApplicationError) as refusal:
        asyncio.run(DirectConfiguredWorkflow().run(IssueAnalysisRequest(inputs(), key, budget)))
    assert (refusal.value.type, refusal.value.non_retryable) == (failure_type, True)
    assert messages == []


@pytest.mark.parametrize("agents", [[], [fixture_agent(), fixture_agent()]])
def test_agent_configuration_refuses_before_agent_execution(agents):
    class Misconfigured(DirectConfiguredWorkflow):
        __pydantic_ai_agents__ = agents
    with capture_run_messages() as messages, pytest.raises(ApplicationError) as refusal:
        asyncio.run(Misconfigured().run(IssueAnalysisRequest(inputs(), "path_traversal", BUDGET)))
    assert (refusal.value.type, refusal.value.non_retryable) == ("AgentConfigurationInvalid", True)
    assert messages == []


class UnreportedUsage(WrapperModel):
    """Fixture provider that reports no usage at all."""

    usage = RequestUsage()

    async def request(self, messages, model_settings, model_request_parameters):
        response = await super().request(messages, model_settings, model_request_parameters)
        return replace(response, usage=self.usage)


class InputOnlyUsage(UnreportedUsage):
    """Fixture provider that reports only the input dimension."""

    usage = RequestUsage(input_tokens=7)


class DetailsOnlyUsage(UnreportedUsage):
    """Fixture provider whose usage carries details but no token counts."""

    usage = RequestUsage(details={"reasoning_tokens": 3})


def test_unreported_usage_is_unknown_and_output_corrections_are_counted():
    expected = EXPECTED["missing_source"]

    async def respond(messages, info):
        corrected = any(part.part_kind == "retry-prompt" for message in messages for part in message.parts)
        output = expected if corrected else expected.model_copy(update={"scope": "application_path"})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    corrected = FunctionModel(respond)
    durability = TemporalDurability(models={"corrected": corrected, "unreported": UnreportedUsage(corrected),
                                            "input_only": InputOnlyUsage(corrected),
                                            "details_only": DetailsOnlyUsage(corrected)},
                                    activity_config=ACTIVITY_CONFIG)

    class Correcting(IssueAnalysisWorkflow):
        __pydantic_ai_agents__ = [create_issue_analysis_agent(corrected, output_retries=1, durability=durability)]
        model_keys = ("corrected", "unreported", "input_only", "details_only")
        budget_ceiling = BUDGET

    async def check():
        with models.override_allow_model_requests(False):
            return [await Correcting().run(IssueAnalysisRequest(inputs("missing_source"), key, BUDGET))
                    for key in Correcting.model_keys]
    reported, unreported, input_only, details_only = asyncio.run(check())
    for result in (reported, unreported, input_only, details_only):
        assert result.output == expected
        assert (result.requests, result.tool_calls, result.output_corrections) == (2, 0, 1)
    assert reported.usage_reported and reported.input_tokens > 0 and reported.output_tokens > 0
    # A provider that reports nothing yields unknown token counts, never zero.
    assert not unreported.usage_reported
    assert (unreported.input_tokens, unreported.output_tokens) == (None, None)
    # Partial usage keeps the reported dimension and leaves the other unknown, never zero.
    assert not input_only.usage_reported
    assert (input_only.input_tokens, input_only.output_tokens) == (14, None)
    # Details-only usage has values but no token evidence for either dimension.
    assert not details_only.usage_reported
    assert (details_only.input_tokens, details_only.output_tokens) == (None, None)


def test_native_direct_request_limit_remains_effective():
    async def check():
        with models.override_allow_model_requests(False), pytest.raises(UsageLimitExceeded):
            await fixture_agent().run(
                fixture_prompt(inputs()), model="path_traversal", deps=FixtureDependencies(inputs()),
                usage_limits=UsageLimits(request_limit=1, tool_calls_limit=1, total_tokens_limit=5000))
    asyncio.run(check())
