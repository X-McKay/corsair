"""Native deterministic evaluation of the fixture contract, never live reasoning."""

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

import logfire
from pydantic import TypeAdapter
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits
from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, HasMatchingSpan, MaxModelRequests, MaxToolCalls, ToolCorrectness

from corsair.agents.issue_analysis import (
    FixtureDependencies, IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent, fixture_prompt,
)
from corsair.agents.issue_analysis.agent import CONFIG_VERSION, PROMPT_VERSION, TOOL_RETRIES

ROOT = Path(__file__).parent


def scripted_model(output: IssueAnalysis, *, path: str = "documents.py") -> FunctionModel:
    """Deterministic SDK model supplied by evaluator; the oracle is not a stage input."""
    async def respond(messages, info):
        returned = any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if output.citations and not returned:
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": path, "start_line": 1, "end_line": 4})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])
    return FunctionModel(respond)


PROFILE_FLAGS = ("default_structured_output_mode", "supports_json_schema_output", "supports_json_object_output",
                 "json_schema_transformer", "openai_chat_supports_multiple_system_messages",
                 "openai_supports_strict_tool_definition")


def describe_model(model: Model) -> dict[str, Any]:
    """Read the request-shaping configuration from the model actually used."""
    profile = model.profile
    def flag(name):
        if name not in profile:
            return "unset"
        value = profile[name]
        return value.__name__ if isinstance(value, type) else value
    client = getattr(model, "client", None)
    return {"model_name": model.model_name, "system": model.system,
            "profile": {name: flag(name) for name in PROFILE_FLAGS},
            "model_settings": dict(model.settings or {}),
            "sdk_max_retries": client.max_retries if client is not None else "not_applicable"}


def record_count(name: str, value: int) -> None:
    """Pydantic Evals drops zero-valued metric increments; the attribute keeps a measured zero."""
    set_eval_attribute(name, value)
    increment_eval_metric(name, value)


@dataclass(frozen=True)
class FixtureEvaluationConfig:
    """The one source for the fixture run budget and its recorded experiment metadata."""
    model: dict[str, Any]
    mode: str = "direct_fixture"
    model_kind: str = "FunctionModel scripted oracle, not live reasoning"
    prompt_version: str = PROMPT_VERSION
    config_version: str = CONFIG_VERSION
    rubric_version: str = "fixture-contract-v1"
    output_retries: int = 1
    tool_retries: int = TOOL_RETRIES
    retry_task: None = None  # no Pydantic Evals task retry
    request_limit: int = 3
    tool_calls_limit: int = 1
    total_tokens_limit: int = 5000
    repeat: int = 2
    max_concurrency: int = 1
    provider_revision: str = "not_applicable"
    packages: dict[str, str] = field(default_factory=lambda: {
        "pydantic_ai_slim": version("pydantic-ai-slim"), "pydantic_evals": version("pydantic-evals")})

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


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
    # MatchesOracle fails closed; a case without an oracle is a dataset defect, not a pass.
    assert cases and all(case.expected_output is not None for case in cases), "every fixture case needs an oracle"
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

    config = FixtureEvaluationConfig(model=describe_model(scripted_model(next(iter(scripted.values())))))

    async def task(inputs: IssueAnalysisInput) -> IssueAnalysis:
        model = scripted_model(scripted[inputs.fixture_id])
        if describe_model(model) != config.model:
            raise RuntimeError("fixture model configuration differs from recorded metadata")
        agent = create_issue_analysis_agent(model, output_retries=config.output_retries)
        with models.override_allow_model_requests(False):
            result = await agent.run(fixture_prompt(inputs), deps=FixtureDependencies(inputs),
                                     usage_limits=config.usage_limits())
        usage = result.usage
        set_eval_attribute("input_digest", inputs.input_digest)
        set_eval_attribute("observed_native_tool_calls", usage.tool_calls)
        set_eval_attribute("usage_source", "FunctionModel estimated tokens; no provider billing")
        record_count("native_requests", usage.requests)
        increment_eval_metric("native_tool_calls", usage.tool_calls)
        # FunctionModel token counts are estimates; never provider billing observations.
        increment_eval_metric("fixture_estimated_input_tokens", usage.input_tokens)
        increment_eval_metric("fixture_estimated_output_tokens", usage.output_tokens)
        return result.output

    return await dataset().evaluate(task, max_concurrency=config.max_concurrency, repeat=config.repeat,
                                    retry_task=config.retry_task, metadata=config.metadata())


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
