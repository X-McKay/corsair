"""Curated deterministic plan checks over frozen development cases; no LLM judge."""

import argparse
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import logfire
from openai import APIConnectionError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, HasMatchingSpan, MaxModelRequests, MaxToolCalls
import yaml

from corsair.agents.provider import LocalModelConfig, local_model
from corsair.agents.source.contracts import SourceRead
from corsair.agents.source.tools import READ_SOURCE_TOOL
from corsair.agents.test_planning.agent import (
    CONFIG_VERSION, PROMPT_VERSION, TOOLSET_ID, PlanningDependencies, create_test_planning_agent, planning_prompt,
)
from corsair.agents.test_planning.contracts import ReadyTestPlan, TestPlanningInput, UnsupportedTestPlan
from corsair.agents.test_planning.skills import SKILL_SHA256
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names

ROOT = Path(__file__).parent
# Development cases shaped prompts v1-v5; each held-out set was frozen before any provider saw it
# (heldout was exposed to v2/v3 in PLAN-0036; heldout2 was written and reviewed apart from the v4/v5 prompt author).
DATASETS = {"development": "cases.yaml", "heldout": "cases-heldout.yaml", "heldout2": "cases-heldout-2.yaml"}
# SPEC-0023: a manifest of case name and content hash beside each held-out dataset.
MANIFESTS = {"heldout": "cases-heldout.manifest.json", "heldout2": "cases-heldout-2.manifest.json"}
# Fixture setup reaching the parent of the scratch location or a fixed host directory (PLAN-0025 review finding).
OUTSIDE_SCRATCH = re.compile(r"\.parent\b|(?<![\w.])/(?:tmp|var|etc|home|root)\b|(?<![\w.])~/", re.IGNORECASE)
PlanOutput = ReadyTestPlan | UnsupportedTestPlan


class PlanOracle(BaseModel):
    """Evaluator-only expectations and a reviewed reference plan; never given to the agent."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ready", "unsupported"]
    symbol: str | None = None
    target_path: str | None = None
    required_lines: tuple[int, ...] = ()
    adversarial_markers: tuple[str, ...] = ()
    witness_markers: tuple[str, ...] = ()
    required_reads: tuple[str, ...] = ()
    forbidden_markers: tuple[str, ...] = ()
    # Scripted plumbing replays this; for the path-traversal cases it is the SPEC-0018 realization.
    reference_plan: dict[str, Any]


def _covers(references, path: str, lines: tuple[int, ...]) -> bool:
    return all(any(r.path == path and r.start_line <= line <= r.end_line for r in references) for line in lines)


def plan_checks(inputs: TestPlanningInput, output: PlanOutput, oracle: PlanOracle) -> dict[str, bool]:
    """Separate curated anchors; they show structure and grounding, not that an assertion measures the right property."""
    checks = {"status": output.status == oracle.status, "scope": output.scope == inputs.scope}
    if not isinstance(output, ReadyTestPlan):
        return checks | {"abstention": isinstance(output, UnsupportedTestPlan) and bool(output.missing_capability.strip())
                         and (bool(output.citations) or not inputs.source_files)}
    environment = inputs.environment
    specs = (output.control, output.security)
    lowered = lambda text: text.lower()
    # Plan text without trusted quotations, so quoted hostile source cannot count against the plan.
    authored = output.model_dump_json(exclude={"citations": {"__all__": {"quote"}},
        "control": {"source_references": {"__all__": {"quote"}}}, "security": {"source_references": {"__all__": {"quote"}}}})
    return checks | {
        "contract": all(spec.test_path in environment.approved_test_paths for spec in specs)
                    and output.discovery_command == environment.discovery_command
                    and output.control.test_id != output.security.test_id,
        "implementation_call": oracle.symbol is not None and all(oracle.symbol in spec.implementation_call for spec in specs),
        "adversarial_input": any(m in output.security.input for m in oracle.adversarial_markers)
                             and not any(m in output.control.input for m in oracle.adversarial_markers),
        "witness": any(m in lowered(output.security.observable_witness) for m in oracle.witness_markers),
        "grounding": oracle.target_path is not None and all(
            _covers(spec.source_references, oracle.target_path, oracle.required_lines) for spec in specs),
        "authority": not any(m in authored for m in oracle.forbidden_markers),
        # Heuristic anchor: names a parent or fixed host directory; prose may still escape another way.
        "scratch": not any(OUTSIDE_SCRATCH.search(step) for spec in specs for step in spec.fixture_setup),
    }


@dataclass
class MatchesPlan(Evaluator[TestPlanningInput, PlanOutput, PlanOracle]):
    def evaluate(self, ctx):
        if ctx.metadata is None:
            return {"oracle_present": False}
        return plan_checks(ctx.inputs, ctx.output, ctx.metadata)


@dataclass
class ReadBeforePlanning(Evaluator[TestPlanningInput, PlanOutput, PlanOracle]):
    """Trajectory: the curated files (target, baseline test) were read in this attempt."""
    def evaluate(self, ctx):
        read = set(ctx.attributes.get("read_paths") or ())
        return {"required_reads": ctx.metadata is not None and set(ctx.metadata.required_reads) <= read}


def case_hashes(name: str) -> dict[str, str]:
    """Content hash per case, over the canonical JSON of its YAML entry."""
    cases = yaml.safe_load((ROOT / DATASETS[name]).read_text())["cases"]
    return {case["name"]: sha256(json.dumps(case, sort_keys=True).encode()).hexdigest() for case in cases}


def check_manifest(name: str) -> None:
    """Refuse a held-out dataset whose cases differ from its frozen manifest."""
    if name in MANIFESTS and case_hashes(name) != json.loads((ROOT / MANIFESTS[name]).read_text()):
        raise ValueError(f"{DATASETS[name]} differs from its frozen manifest {MANIFESTS[name]}")


def dataset(name: str = "development") -> Dataset[TestPlanningInput, PlanOutput, PlanOracle]:
    return Dataset[TestPlanningInput, PlanOutput, PlanOracle].from_file(
        ROOT / DATASETS[name], custom_evaluator_types=(MatchesPlan, ReadBeforePlanning),
    )


def scripted_model(oracle: PlanOracle) -> FunctionModel:
    """Oracle injection is confined to the scripted plumbing model, never live task inputs."""
    async def respond(messages, info):
        returned = {SourceRead.model_validate(part.content).path for message in messages for part in message.parts
                    if isinstance(part, ToolReturnPart) and part.tool_name == READ_SOURCE_TOOL}
        pending = [path for path in oracle.required_reads if path not in returned]
        if pending:
            return ModelResponse(parts=[ToolCallPart(READ_SOURCE_TOOL, {"path": pending[0], "start_line": 1})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"plan": oracle.reference_plan})])
    return FunctionModel(respond)


def read_paths(messages: list[ModelMessage]) -> list[str]:
    return sorted({SourceRead.model_validate(part.content).path for message in messages for part in message.parts
                   if isinstance(part, ToolReturnPart) and part.tool_name == READ_SOURCE_TOOL and part.outcome == "success"})


class EvaluationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=2, ge=1, le=3, strict=True)
    request_limit: int = Field(default=5, ge=1, le=8, strict=True)
    tool_calls_limit: int = Field(default=4, ge=0, le=6, strict=True)
    total_tokens_limit: int = Field(default=48000, ge=1, le=96000, strict=True)
    task_seconds: int = Field(default=240, ge=1, le=300, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)


async def evaluate(evidence: Path, budget: EvaluationBudget, *, model=None, cases: str = "development", provider=None):
    check_manifest(cases)
    # Reserve before the first request; rerunning the same attempt is always refused.
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset(cases)
    scripted = model is None
    fixture_models = {case.inputs.input_digest: scripted_model(case.metadata) for case in corpus.cases} if scripted else {}
    actual_model = model if model is not None else next(iter(fixture_models.values()))
    metadata = {"mode": "scripted_fixture" if scripted else "direct_local_provider",
                "model": describe_model(actual_model), "weights_identity": "not_applicable" if scripted else "unknown",
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "toolset_id": TOOLSET_ID, "budget": budget.model_dump(), "task_retries": 0, "max_concurrency": 1,
                "dataset": cases, "dataset_sha256": sha256((ROOT / DATASETS[cases]).read_bytes()).hexdigest(),
                "provider": provider,
                "output_contract": "ReadyTestPlan | UnsupportedTestPlan",
                "draft_contract": "ReadyTestPlanDraft | UnsupportedTestPlanDraft"}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.append(NoUnknownToolAttempts())
    if not scripted:
        corpus.evaluators.append(ProviderUsageCoverage())
    corpus.evaluators.extend([MatchesPlan(), ReadBeforePlanning(),
                             MaxModelRequests(max_requests=budget.request_limit), MaxToolCalls(max_calls=budget.tool_calls_limit),
                             HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}}, evaluation_name="model_spans")])

    async def task(inputs):
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        selected = fixture_models[inputs.input_digest] if scripted else model
        known_tools = frozenset({READ_SOURCE_TOOL}) | output_tool_names(selected)
        agent = create_test_planning_agent(selected, output_retries=budget.output_retries)
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(not scripted):
                result = await asyncio.wait_for(agent.run(planning_prompt(inputs), deps=PlanningDependencies(inputs),
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
                       "read_paths": read_paths(messages),
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known_tools)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("input_digest", inputs.input_digest)
            set_eval_attribute("read_paths", receipt["read_paths"])
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
    parser.add_argument("--cases", choices=sorted(DATASETS), default="development")
    parser.add_argument("--repeat", type=int, default=EvaluationBudget().repeat)
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")
    async def run():
        budget = EvaluationBudget(repeat=args.repeat)
        if args.provider_config is None:
            return await evaluate(args.evidence, budget, cases=args.cases)
        config = LocalModelConfig.model_validate_json(args.provider_config.read_text())
        async with local_model(config) as model:
            return await evaluate(args.evidence, budget, model=model, cases=args.cases,
                                  provider=config.model_dump(mode="json", exclude={"api_key_env"}))
    report = asyncio.run(run())
    report.print(include_input=False, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
