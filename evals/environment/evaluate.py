"""Host-only environment evaluation: synthetic observations, never host command execution."""

import argparse
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from typing import Literal
from openai import APIConnectionError
import logfire
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import (
    Evaluator,
    MaxModelRequests,
    MaxToolCalls,
    HasMatchingSpan,
)
from corsair.agents.environment.agent import (
    PROMPT_VERSION,
    SKILL_SHA256,
    TOOLSET_SHA256,
    create_environment_agent,
    environment_prompt,
)
from corsair.agents.environment.contracts import EnvironmentInput, EnvironmentDraft
from corsair.agents.environment.dependencies import EnvironmentDependencies, SetupBudget
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from corsair.ports.execution import ExecutionReceipt, ExecutionError
from corsair.ports.sandbox import SandboxHandle
from evals.cases import load_set, set_digest
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import (
    NoUnknownToolAttempts,
    ProviderUsageCoverage,
    message_counts,
)

ROOT = Path(__file__).parent
HANDLE = SandboxHandle(
    id="recorded",
    name="prep",
    workspace="corsair",
    owner="eval",
    creation_operation="fixture",
)


class HostInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str
    inputs: EnvironmentInput


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    exit: int
    stdout: str
    unknown: bool = False


class FrozenCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    inputs: EnvironmentInput
    required_reads: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    observations: tuple[Observation, ...]
    draft: EnvironmentDraft
    status: Literal["ready", "blocked", "unsupported"]
    layer: str | None
    max_commands: int = Field(ge=1, le=64)
    toolchain_id: str = "python-3.12"
    requirement_patterns: tuple[str, ...] = ()
    checkout_paths: tuple[str, ...] | None = None  # Operator listing shown in the request; absent means none


class RecordedExecution:
    """Synthetic exact-command observations; unknown commands fail closed. No shell."""

    def __init__(self, case):
        self.case = case
        self.calls = []
        self.unrecorded_commands = []

    def execute(self, handle, command, operation):
        self.calls.append(tuple(command))
        pairs = list(zip(self.case["commands"], self.case["observations"]))
        observation = next(
            (o for c, o in pairs if tuple(c) == tuple(command)),
            None,
        )
        if observation is None:
            self.unrecorded_commands.append(tuple(command))
            observation = {"exit": 126, "stdout": "synthetic fixture refusal: unrecorded command"}
        unknown = observation.get("unknown", False)
        receipt = ExecutionReceipt(
            operation=str(operation),
            handle=handle,
            started_at="recorded",
            elapsed_seconds=0.5,
            delivery="unknown" if unknown else "acknowledged",
            completion="unknown" if unknown else "terminal_observed",
            reason="recorded observation",
            stdout=observation["stdout"].encode(),
            native_exit=None if unknown else observation["exit"],
            failure_layer="native_execution" if unknown else None,
            error_detail=observation["stdout"] if unknown else None,
        )
        if unknown:
            raise ExecutionError(receipt)
        return receipt


def scripted(case):
    calls = (
        [("read_source", {"path": p}) for p in case["required_reads"]]
        + [("list_toolchains", {})]
        + [("run_setup_command", {"command": c}) for c in case["commands"]]
    )
    position = 0

    async def respond(messages, info):
        nonlocal position
        if position < len(calls):
            name, args = calls[position]
            position += 1
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"draft": case["draft"]})]
        )

    return FunctionModel(respond)


@dataclass
class EnvironmentChecks(Evaluator):
    def evaluate(self, ctx):
        c = ctx.metadata
        output = ctx.output
        calls = ctx.attributes.get("commands", [])
        reads = ctx.attributes.get("read_paths", [])
        # Every curated outcome requires its observed trajectory, including blocked
        # cases. Stop the expected prefix at unknown delivery or the operator budget.
        stop = min(len(c["commands"]), c["max_commands"])
        unknown = next((i for i, o in enumerate(c["observations"]) if o.get("unknown")), None)
        if unknown is not None:
            stop = min(stop, unknown + 1)
        expected_commands = c["commands"][:stop]
        citations = (
            [step.source for step in output.recipe]
            if output.status == "ready"
            else list(output.citations)
        )
        saved = {f.path: f.content.splitlines() for f in ctx.inputs.inputs.source_files}
        grounded = all(
            ref.path in reads
            and ref.quote
            == "\n".join(saved[ref.path][ref.start_line - 1 : ref.end_line])
            for ref in citations
        )
        return {
            "status": output.status == c["status"],
            # Curated development-case wording anchors, not arbitrary-language truth.
            "unsupported_requirement": output.status != "unsupported"
            or bool(c.get("requirement_patterns"))
            and all(
                re.search(pattern, output.requirement) is not None
                for pattern in c["requirement_patterns"]
            ),
            "setup_identity": output.status != "ready"
            or all(
                getattr(output, key) == c["draft"][key]
                for key in (
                    "toolchain_id",
                    "framework",
                    "baseline_test_id",
                    "baseline_test_path",
                )
            ),
            "discovery_command": output.status != "ready"
            or list(output.discovery_command) == c["draft"]["discovery_command"],
            "layer": c["layer"] is None or getattr(output, "layer", None) == c["layer"],
            "grounding": set(c["required_reads"]) <= set(reads) and grounded,
            "command_policy": all(list(cmd) in c["commands"] for cmd in calls),
            "command_budget": len(calls) <= c["max_commands"],
            "unknown_halt": not any(o.get("unknown") for o in c["observations"])
            or len(calls)
            <= next(i + 1 for i, o in enumerate(c["observations"]) if o.get("unknown")),
            "contract": [r.model_dump(mode="json") for r in output.receipts]
            == ctx.attributes.get("records", []),
            "required_commands": [list(cmd) for cmd in calls] == expected_commands,
        }


class EvaluationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=2, ge=1, le=3, strict=True)
    request_limit: int = Field(default=16, ge=1, le=24, strict=True)
    tool_calls_limit: int = Field(default=20, ge=0, le=32, strict=True)
    total_tokens_limit: int = Field(default=128000, ge=1, le=131072, strict=True)
    task_seconds: int = Field(default=240, ge=1, le=300, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)


def load_cases(name="development"):
    """Frozen cases of one set and that set's identity; the development file keeps its own manifest digest."""
    if name == "breadth":
        cases = [
            FrozenCase.model_validate({"name": c.name, "inputs": c.input, **c.oracle}).model_dump(mode="json")
            for c in load_set("environment", "breadth")
        ]
        return cases, set_digest("environment", "breadth")
    raw = (ROOT / "cases.json").read_bytes()
    if (
        sha256(raw).hexdigest()
        != json.loads((ROOT / "manifest.json").read_text())["sha256"]
    ):
        raise ValueError("frozen environment dataset digest changed")
    cases = [
        FrozenCase.model_validate(c).model_dump(mode="json") for c in json.loads(raw)
    ]
    return cases, sha256(raw).hexdigest()


async def evaluate(evidence, budget, model=None, provider=None, dataset="development"):
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    cases, dataset_sha256 = load_cases(dataset)
    scripted_mode = model is None
    metadata = {
        "mode": "scripted_fixture" if scripted_mode else "direct_local_provider",
        "prompt_version": PROMPT_VERSION,
        "config_version": "environment-eval-v2-corrections",
        "setup_max_corrections": SetupBudget().max_corrections,
        "skill_sha256": SKILL_SHA256,
        "toolset_sha256": TOOLSET_SHA256,
        "dataset": dataset,
        "dataset_sha256": dataset_sha256,
        "model": describe_model(model or scripted(cases[0])),
        "execution": "synthetic_observations_not_executed",
        "budget": budget.model_dump(),
        "provider": provider,
        "task_retries": 0,
    }
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus = Dataset(
        name=f"environment-{dataset}-v1",
        cases=[
            Case(
                name=c["name"],
                inputs=HostInput(
                    fixture_id=c["name"],
                    inputs=EnvironmentInput.model_validate(c["inputs"]),
                ),
                metadata=c,
            )
            for c in cases
        ],
        evaluators=[
            EnvironmentChecks(),
            NoUnknownToolAttempts(),
            MaxModelRequests(max_requests=budget.request_limit),
            MaxToolCalls(max_calls=budget.tool_calls_limit),
            HasMatchingSpan(
                query={"has_attributes": {"gen_ai.operation.name": "chat"}},
                evaluation_name="model_spans",
            ),
        ],
    )
    if not scripted_mode:
        corpus.evaluators.append(ProviderUsageCoverage())

    async def task(host_input):
        inputs = host_input.inputs
        c = next(c for c in cases if c["name"] == host_input.fixture_id)
        execution = RecordedExecution(c)
        deps = EnvironmentDependencies(
            inputs=inputs,
            execution=execution,
            handle=HANDLE,
            toolchain_id=c.get("toolchain_id", "python-3.12"),
            scratch_location="/sandbox/scratch",
            budget=SetupBudget(max_commands=c["max_commands"]),
            checkout_paths=None if c["checkout_paths"] is None else tuple(c["checkout_paths"]),
        )
        selected = model or scripted(c)
        agent = create_environment_agent(selected, output_retries=budget.output_retries)
        usage = RunUsage()
        messages = []
        result = None
        failure = None
        started = perf_counter()
        try:
            with (
                capture_run_messages() as messages,
                models.override_allow_model_requests(not scripted_mode),
            ):
                result = await asyncio.wait_for(
                    agent.run(
                        environment_prompt(inputs, deps.checkout_paths),
                        deps=deps,
                        usage=usage,
                        usage_limits=UsageLimits(
                            request_limit=budget.request_limit,
                            tool_calls_limit=budget.tool_calls_limit,
                            total_tokens_limit=budget.total_tokens_limit,
                        ),
                    ),
                    budget.task_seconds,
                )
            return result.output
        except BaseException as exc:
            failure = {
                "type": type(exc).__name__,
                "detail": str(exc),
                "uncertain_delivery": isinstance(
                    exc, (TimeoutError, asyncio.CancelledError, APIConnectionError)
                ),
            }
            raise
        finally:
            reads = sorted(
                {
                    (
                        p.content.path
                        if hasattr(p.content, "path")
                        else p.content["path"]
                    )
                    for m in messages
                    for p in m.parts
                    if isinstance(p, ToolReturnPart)
                    and p.tool_name == "read_source"
                    and p.outcome == "success"
                }
            )
            counts = message_counts(
                messages,
                frozenset(
                    {
                        "read_source",
                        "list_toolchains",
                        "run_setup_command",
                        "read_output",
                        "final_result",
                    }
                ),
            )
            responses = [m for m in messages if isinstance(m, ModelResponse)]
            receipt = {
                "completed": result is not None,
                "failure": failure,
                "elapsed_seconds": perf_counter() - started,
                "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                "usage_source": "scripted_estimate"
                if scripted_mode
                else "native_responses_partial_on_failure",
                "provider_usage_present": None
                if scripted_mode
                else bool(responses) and all(m.usage.has_values() for m in responses),
                "commands": execution.calls,
                "unrecorded_commands": execution.unrecorded_commands,
                "setup_corrections": deps.ledger.corrections_used,
                "pending_correction": deps.ledger.pending_correction,
                "read_paths": reads,
                "records": [r.model_dump(mode="json") for r in deps.ledger.records],
                "messages": TypeAdapter(list[ModelMessage]).dump_python(
                    messages, mode="json"
                ),
                **counts,
            }
            path = evidence / f"attempt-{uuid4()}.json"
            path.write_text(json.dumps(receipt, indent=2))
            for key in [
                "commands",
                "read_paths",
                "unknown_tool_attempts",
                "provider_usage_present",
            ]:
                set_eval_attribute(key, receipt[key])
            set_eval_attribute("records", receipt["records"])
            for key, value in [
                ("requests", usage.requests),
                ("tool_calls", usage.tool_calls),
                ("input_tokens", usage.input_tokens),
                ("output_tokens", usage.output_tokens),
                ("commands", len(execution.calls)),
                ("output_corrections", counts["output_corrections"]),
                ("setup_corrections", deps.ledger.corrections_used),
            ]:
                record_count("observed_" + key, value)

    report = await corpus.evaluate(
        task,
        repeat=budget.repeat,
        max_concurrency=1,
        retry_task=None,
        metadata=metadata,
        progress=False,
    )
    (evidence / "report.json").write_bytes(
        TypeAdapter(type(report)).dump_json(report, indent=2)
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--cases", choices=("development", "breadth"), default="development")
    args = parser.parse_args()

    async def run():
        budget = EvaluationBudget(repeat=args.repeat)
        if args.provider_config is None:
            return await evaluate(args.evidence, budget, dataset=args.cases)
        config = load_agent_config(args.provider_config, "environment")
        async with configured_model(config) as model:
            return await evaluate(
                args.evidence,
                budget,
                model,
                config.model_dump(mode="json", exclude={"api_key_env"}),
                dataset=args.cases,
            )

    report = asyncio.run(run())
    report.print(include_input=False, include_output=False)
    if (
        report.failures
        or report.report_evaluator_failures
        or any(
            c.evaluator_failures or not all(a.value for a in c.assertions.values())
            for c in report.cases
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
