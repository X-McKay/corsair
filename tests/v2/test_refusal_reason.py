"""Why an agent's last final answer was refused, read from its native message history."""
import asyncio

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.output import PromptedOutput

from corsair.agents.common.prompted_output import prompted_output
from corsair.agents.common.usage import refusal_reason, run_recorded


class Plan(BaseModel):
    steps: int


def _answers(*parts):
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=list(parts))
    return FunctionModel(respond)


@pytest.mark.parametrize("parts, kind", [
    ((ThinkingPart("x" * 40),), "reasoning_only"),
    ((TextPart('{"steps": 1} {"steps": 2}'),), "multiple_objects"),
    ((TextPart("I would plan two probes."),), "invalid_output"),
    ((TextPart('{"steps": "two"}'),), "invalid_output"),
])
def test_an_exhausted_run_names_its_last_refusal(parts, kind):
    model = _answers(*parts)
    agent = Agent(model, output_type=PromptedOutput(Plan), retries={"output": 1}, capabilities=[prompted_output()])
    with capture_run_messages() as messages:
        output, usage = asyncio.run(run_recorded(agent, "investigator", "plan", model=model))
    assert output is None and usage.status == "output_invalid"
    assert refusal_reason(messages).startswith(f"{kind}: ")


def test_a_run_without_refusals_has_no_reason():
    model = _answers(TextPart('{"steps": 1}'))
    agent = Agent(model, output_type=PromptedOutput(Plan), capabilities=[prompted_output()])
    with capture_run_messages() as messages:
        output, _ = asyncio.run(run_recorded(agent, "investigator", "plan", model=model))
    assert output == Plan(steps=1) and refusal_reason(messages) is None
