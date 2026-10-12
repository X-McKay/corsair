"""Native deterministic evaluation of the fixture contract, never live reasoning."""

import argparse
import asyncio
from dataclasses import dataclass
import json
from importlib.metadata import version
from pathlib import Path

import logfire
from pydantic import TypeAdapter
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits
from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, HasMatchingSpan, MaxModelRequests, MaxToolCalls, ToolCorrectness

from corsair.agents.issue_analysis import (
    FixtureDependencies, IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent, fixture_prompt,
)
from corsair.agents.issue_analysis.agent import PROMPT_VERSION

ROOT = Path(__file__).parent


def scripted_model(output: IssueAnalysis, *, path: str = "documents.py") -> FunctionModel:
    """Deterministic SDK model supplied by evaluator; the oracle is not a stage input."""
    async def respond(messages, info):
        returned = any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if output.citations and not returned:
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": path, "start_line": 1, "end_line": 4})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])
    return FunctionModel(respond)


@dataclass
class MatchesOracle(Evaluator[IssueAnalysisInput, IssueAnalysis, None]):
    def evaluate(self, ctx: EvaluatorContext[IssueAnalysisInput, IssueAnalysis, None]) -> bool:
        return ctx.output == ctx.expected_output


def dataset() -> Dataset:
    oracles = json.loads((ROOT / "oracles.json").read_text())
    cases = []
    for name, expected in oracles["cases"].items():
        inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / (name + ".json")).read_text())
        output = IssueAnalysis.model_validate(expected)
        cases.append(Case(name=name, inputs=inputs, expected_output=output,
                          evaluators=[ToolCorrectness(expected_tools=["read_source"] if output.citations else [])]))
    return Dataset(name="issue-analysis-fixture-v1", cases=cases,
                   evaluators=[MatchesOracle(), MaxToolCalls(max_calls=1), MaxModelRequests(max_requests=2),
                               HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}},
                                               evaluation_name="model_span_coverage")])


async def evaluate_fixture() -> object:
    """Evaluate twice, with fresh deps per task, collecting local native spans only."""
    logfire.configure(send_to_logfire=False, console=False)
    oracles = json.loads((ROOT / "oracles.json").read_text())["cases"]
    scripted = {
        IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / (name + ".json")).read_text()).fixture_id:
        IssueAnalysis.model_validate(output) for name, output in oracles.items()
    }

    async def task(inputs: IssueAnalysisInput) -> IssueAnalysis:
        agent = create_issue_analysis_agent(scripted_model(scripted[inputs.fixture_id]))
        with models.override_allow_model_requests(False):
            result = await agent.run(fixture_prompt(inputs), deps=FixtureDependencies(inputs),
                                     usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1, total_tokens_limit=5000))
        usage = result.usage
        set_eval_attribute("input_digest", inputs.input_digest)
        set_eval_attribute("observed_native_tool_calls", usage.tool_calls)
        set_eval_attribute("usage_source", "FunctionModel estimated tokens; no provider billing")
        increment_eval_metric("native_requests", usage.requests)
        increment_eval_metric("native_tool_calls", usage.tool_calls)
        # FunctionModel token counts are estimates; never provider billing observations.
        increment_eval_metric("fixture_estimated_input_tokens", usage.input_tokens)
        increment_eval_metric("fixture_estimated_output_tokens", usage.output_tokens)
        return result.output

    return await dataset().evaluate(task, max_concurrency=1, repeat=2,
                                    metadata={"mode": "direct_fixture", "prompt_version": PROMPT_VERSION,
                                              "rubric_version": "fixture-contract-v1",
                                              "pydantic_ai_slim": version("pydantic-ai-slim"),
                                              "pydantic_evals": version("pydantic-evals"),
                                              "model": "FunctionModel scripted oracle, not live reasoning",
                                              "task_retries": 0, "output_retries": 1,
                                              "request_limit": 3, "tool_calls_limit": 1,
                                              "total_tokens_limit": 5000,
                                              "provider_revision": "not_applicable"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.report.is_symlink():
        parser.error("report destination already exists; choose a new attempt path")
    report = asyncio.run(evaluate_fixture())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    report.print(include_input=False, include_output=False)
    if report.failures or report.report_evaluator_failures or any(
        case.evaluator_failures or not all(item.value for item in case.assertions.values()) for case in report.cases
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
