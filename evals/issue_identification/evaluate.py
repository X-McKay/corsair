"""Deterministic selection checks on curated cases; no LLM judge or semantic regex."""

import argparse
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from typing import Literal

import logfire
from openai import APIConnectionError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, HasMatchingSpan, MaxModelRequests, MaxToolCalls

from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.issue_identification import (
    CONFIG_VERSION, PROMPT_VERSION, TOOLSET_SHA256, create_issue_identification_agent, identification_prompt,
)
from corsair.agents.issue_identification.skills import SKILL_SHA256
from corsair.agents.issue_identification.contracts import IssueIdentification, IssueIdentificationDraft
from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
from corsair.agents.issue_analysis.tools import FixtureDependencies
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names

ROOT = Path(__file__).parent


class SelectionOracle(BaseModel):
    """Evaluator-only allowed selections; never given to the agent."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ready", "missing_information", "unsupported"]
    symbol: str | None = None
    path: str | None = None
    required_lines: tuple[int, ...] = ()
    max_span: int = 8


def selection_checks(inputs: IssueAnalysisInput, output: IssueIdentification, oracle: SelectionOracle) -> dict[str, bool]:
    checks = {"status": output.status == oracle.status, "scope": output.scope == inputs.scope,
              "report_identity": output.reported_issue == inputs.issue}
    if oracle.status != "ready":
        return checks | {"abstention": output.target is None and bool(output.reason)}
    target = output.target
    checks["target_selection"] = target is not None and target.symbol == oracle.symbol and target.source.path == oracle.path
    checks["source_range"] = target is not None and bool(oracle.required_lines) and all(
        target.source.start_line <= line <= target.source.end_line for line in oracle.required_lines
    ) and target.source.end_line - target.source.start_line + 1 <= oracle.max_span
    saved = next((item for item in inputs.source_files if target and item.path == target.source.path), None)
    lines = saved.content.splitlines() if saved else []
    checks["source_quote"] = bool(target and saved and 1 <= target.source.start_line <= target.source.end_line <= len(lines)
                                  and target.source.quote == "\n".join(lines[target.source.start_line - 1:target.source.end_line]))
    return checks


@dataclass
class MatchesSelection(Evaluator[IssueAnalysisInput, IssueIdentification, SelectionOracle]):
    def evaluate(self, ctx):
        if ctx.metadata is None:
            return {"oracle_present": False}
        return selection_checks(ctx.inputs, ctx.output, ctx.metadata)


def dataset() -> Dataset[IssueAnalysisInput, IssueIdentification, SelectionOracle]:
    return Dataset[IssueAnalysisInput, IssueIdentification, SelectionOracle].from_file(
        ROOT / "cases.yaml", custom_evaluator_types=(MatchesSelection,),
    )


def scripted_model(inputs: IssueAnalysisInput, oracle: SelectionOracle) -> FunctionModel:
    """Oracle injection is confined to the scripted plumbing model, never live task inputs."""
    async def respond(messages, info):
        if oracle.status != "ready":
            draft = {"status": oracle.status, "scope": inputs.scope, "target": None, "reason": "The supplied inventory does not establish the requested target."}
        else:
            start, end = min(oracle.required_lines), max(oracle.required_lines)
            if not any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
                return ModelResponse(parts=[ToolCallPart("read_source", {"path": oracle.path, "start_line": start})])
            draft = {"status": "ready", "scope": inputs.scope, "target": {"symbol": oracle.symbol, "source": {"path": oracle.path, "start_line": start, "end_line": end}},
                     "reason": None}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, draft)])
    return FunctionModel(respond)


class EvaluationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=2, ge=1, le=3, strict=True)
    request_limit: int = Field(default=4, ge=1, le=6, strict=True)
    tool_calls_limit: int = Field(default=3, ge=0, le=4, strict=True)
    total_tokens_limit: int = Field(default=32000, ge=1, le=64000, strict=True)
    task_seconds: int = Field(default=180, ge=1, le=300, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)


async def evaluate(evidence: Path, budget: EvaluationBudget, *, model=None):
    # Reserve before the first request; rerunning the same attempt is always refused.
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset()
    scripted = model is None
    fixture_models = {case.inputs.input_digest: scripted_model(case.inputs, case.metadata) for case in corpus.cases} if scripted else {}
    actual_model = model if model is not None else next(iter(fixture_models.values()))
    metadata = {"mode": "scripted_fixture" if scripted else "direct_local_provider",
                "model": describe_model(actual_model), "weights_identity": "not_applicable" if scripted else "unknown",
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "toolset_sha256": TOOLSET_SHA256,
                "budget": budget.model_dump(), "task_retries": 0, "max_concurrency": 1,
                "dataset_sha256": sha256((ROOT / "cases.yaml").read_bytes()).hexdigest(),
                "output_contract": IssueIdentification.__name__, "draft_contract": IssueIdentificationDraft.__name__}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.append(NoUnknownToolAttempts())
    if not scripted:
        corpus.evaluators.append(ProviderUsageCoverage())
    corpus.evaluators.extend([MaxModelRequests(max_requests=budget.request_limit), MaxToolCalls(max_calls=budget.tool_calls_limit),
                             HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}}, evaluation_name="model_spans")])

    async def task(inputs):
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        selected = fixture_models[inputs.input_digest] if scripted else model
        known_tools = frozenset({"read_source"}) | output_tool_names(selected)
        agent = create_issue_identification_agent(selected, output_retries=budget.output_retries)
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(not scripted):
                result = await asyncio.wait_for(agent.run(identification_prompt(inputs), deps=FixtureDependencies(inputs),
                    usage=usage, usage_limits=UsageLimits(request_limit=budget.request_limit, tool_calls_limit=budget.tool_calls_limit,
                                                         total_tokens_limit=budget.total_tokens_limit)), timeout=budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "detail": str(exc),
                       "uncertain_delivery": isinstance(exc, (TimeoutError, asyncio.CancelledError, APIConnectionError)),
                       "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None,
                       "cause_detail": str(exc.__cause__) if exc.__cause__ else None}
            raise
        finally:
            responses = [m for m in messages if isinstance(m, ModelResponse)]
            receipt = {"input_digest": inputs.input_digest, "completed": result is not None, "failure": failure,
                       "elapsed_seconds": perf_counter() - started,
                       "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                       "usage_source": "scripted_estimate" if scripted else "native_responses_partial_on_failure",
                       "provider_usage_present": None if scripted else bool(responses) and all(m.usage.has_values() for m in responses),
                       "response_ids": [m.provider_response_id for m in responses],
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known_tools)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("input_digest", inputs.input_digest)
            set_eval_attribute("unknown_tool_attempts", receipt["unknown_tool_attempts"])
            set_eval_attribute("provider_usage_present", receipt["provider_usage_present"])
            for key, value in (("requests", usage.requests), ("tool_calls", usage.tool_calls),
                               ("input_tokens", usage.input_tokens), ("output_tokens", usage.output_tokens),
                               ("output_corrections", receipt["output_corrections"])):
                record_count("observed_" + key, value)

    report = await corpus.evaluate(task, repeat=budget.repeat, max_concurrency=1, retry_task=None, metadata=metadata, progress=False)
    # Native report serialization retains per-case assertions, errors, spans, inputs and outputs.
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    return report


def passed(report) -> bool:
    return bool(report.cases) and not report.failures and not report.report_evaluator_failures and all(
        not case.evaluator_failures and case.assertions and all(item.value for item in case.assertions.values())
        and case.attributes.get("unknown_tool_attempts") == 0 for case in report.cases
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Explicit LocalModelConfig JSON; omitted means scripted fixture only")
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")
    async def run():
        if args.provider_config is None:
            return await evaluate(args.evidence, EvaluationBudget())
        config = LocalModelConfig.model_validate_json(args.provider_config.read_text())
        async with local_model(config) as model:
            return await evaluate(args.evidence, EvaluationBudget(), model=model)
    report = asyncio.run(run())
    report.print(include_input=False, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
