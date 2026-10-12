"""Deterministic authoring checks over frozen development cases with a scripted runner; no LLM judge."""

import argparse
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

import logfire
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, HasMatchingSpan, MaxModelRequests, MaxToolCalls

from corsair.agents.source.tools import READ_SOURCE_TOOL
from corsair.agents.test_authoring.agent import (
    CONFIG_VERSION, PROMPT_VERSION, authoring_prompt, create_test_authoring_agent,
)
from corsair.agents.test_authoring.contracts import BlockedAuthoring, DevelopmentRun, TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.skills import SKILL_SHA256
from corsair.agents.test_authoring.static import static_checks
from corsair.agents.test_authoring.tools import RUN_TOOL, WRITE_TOOL, AuthoringBudget, AuthoringDependencies
from corsair.ports.test_runner import (
    ApprovedPatch, Discovery, Execution, FailureDetail, NativeTestRun, TestCaseResult,
)
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, message_counts, output_tool_names

ROOT = Path(__file__).parent
REPOSITORY = ROOT.parents[1]
# The reviewed SPEC-0018 realization; scripted plumbing writes it, never a model.
FILES = {"reference": (REPOSITORY / "benchmarks/fixtures/path-traversal/test_documents.py").read_text(),
         "broken": "import pytest\nimport documents\n\ndef test_benign_control(:\n    pass\n"}
AuthoringOutput = TestPatch | BlockedAuthoring


class ScriptedRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["discovered", "collection_error"]
    control: Literal["passed", "failed"] = "passed"
    security: Literal["passed", "failed"] = "failed"


class AuthoringCase(BaseModel):
    """Dataset input: the agent sees only ``inputs``; fixture_id selects the scripted runner, never the prompt."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str = Field(min_length=1, max_length=128)
    inputs: TestAuthoringInput


class AuthoringOracle(BaseModel):
    """Evaluator-only expectations, the scripted author's steps and the scripted runner's observations."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    script: tuple[dict, ...]
    runner_runs: tuple[ScriptedRun, ...]
    status: Literal["patch", "blocked"]
    runs: int
    layer: str | None = None
    security_assertion_lines: tuple[int, ...] = ()


class ScriptedRunner:
    """Test double for the TestRunner port: replays fixed observations, executes nothing."""

    def __init__(self, runs: tuple[ScriptedRun, ...]):
        self.runs, self.calls = list(runs), []

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID) -> NativeTestRun:
        self.calls.append(patch.sha256)
        scripted = self.runs.pop(0)
        if scripted.status == "collection_error":
            discovery = Discovery("collection_error", (), "E   SyntaxError: invalid syntax", discovery_command, None)
            return NativeTestRun(str(operation), patch.sha256, None, discovery, None, "confirmed", "discovery",
                                 "collection error")
        ids = (control_test_id, security_test_id)
        failure = FailureDetail("failure", "AssertionError", security_test_id.split("::")[0],
                                security_test_id.split("::")[-1], 64, "AssertionError: scripted")
        cases = (TestCaseResult(control_test_id, scripted.control,
                                failure if scripted.control == "failed" else None, ""),
                 TestCaseResult(security_test_id, scripted.security,
                                failure if scripted.security == "failed" else None, ""))
        execution = Execution("completed", cases, None, None, "", ("sh", "-c", "scripted"), None)
        return NativeTestRun(str(operation), patch.sha256, None,
                             Discovery("discovered", ids, "", discovery_command, None), execution, "confirmed", None, "")


def authoring_checks(inputs: TestAuthoringInput, output: AuthoringOutput, oracle: AuthoringOracle) -> dict[str, bool]:
    checks = {"status": output.status == oracle.status, "dev_runs": len([r for r in output.dev_runs if r.status != "not_run"]) == oracle.runs}
    if isinstance(output, BlockedAuthoring):
        return checks | {"layer": output.layer == oracle.layer and bool(output.reason.strip())}
    plan, approved = inputs.plan, inputs.environment.approved_test_paths
    files = {item.path: item.content for item in output.files}
    symbol = plan.control.implementation_call.split("(")[0].split(".")[-1]
    statics = [static_checks(files.get(spec.test_path, ""), spec.test_id, symbol) for spec in (plan.control, plan.security)]
    return checks | {
        "contract": set(files) <= set(approved) and output.control_test_id == plan.control.test_id
                    and output.security_test_id == plan.security.test_id
                    and output.discovery_command == plan.discovery_command,
        "security_assertion_lines": output.security_assertion_lines == oracle.security_assertion_lines,
        "static_semantics": all(all(checks.values()) for checks in statics),
    }


@dataclass
class MatchesAuthoring(Evaluator[AuthoringCase, AuthoringOutput, AuthoringOracle]):
    def evaluate(self, ctx):
        if ctx.metadata is None:
            return {"oracle_present": False}
        return authoring_checks(ctx.inputs.inputs, ctx.output, ctx.metadata)


@dataclass
class AuthoringTrajectory(Evaluator[AuthoringCase, AuthoringOutput, AuthoringOracle]):
    """Read before write, write before run, the security outcome never shown to the author."""
    def evaluate(self, ctx):
        order = ctx.attributes.get("tool_order") or []
        first = lambda name: order.index(name) if name in order else len(order)
        return {"read_before_write": first(READ_SOURCE_TOOL) < first(WRITE_TOOL),
                "write_before_run": first(WRITE_TOOL) < first(RUN_TOOL),
                "security_withheld": ctx.attributes.get("security_revealed") == 0}


def dataset() -> Dataset[AuthoringCase, AuthoringOutput, AuthoringOracle]:
    return Dataset[AuthoringCase, AuthoringOutput, AuthoringOracle].from_file(
        ROOT / "cases.yaml", custom_evaluator_types=(MatchesAuthoring, AuthoringTrajectory),
    )


def scripted_model(inputs: TestAuthoringInput, oracle: AuthoringOracle) -> FunctionModel:
    """Oracle injection is confined to the scripted plumbing model, never live task inputs."""
    plan = inputs.plan
    reads = [plan.security.source_references[0].path]
    if inputs.environment.baseline_test is not None:
        reads.append(inputs.environment.baseline_test.path)
    steps = [ToolCallPart(READ_SOURCE_TOOL, {"path": path}) for path in reads]
    for step in oracle.script:
        if "write" in step:
            steps.append(ToolCallPart(WRITE_TOOL, {"path": plan.security.test_path, "content": FILES[step["write"]]}))
        else:
            steps.append(ToolCallPart(RUN_TOOL, {}))

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(steps):
            return ModelResponse(parts=[steps[done]])
        draft = ({"status": "patch", "security_assertion_lines": list(oracle.security_assertion_lines),
                  "limitations": ["Development runs observe buildability and discovery, not the security outcome"]}
                 if oracle.status == "patch" else
                 {"status": "blocked", "layer": oracle.layer, "reason": "The observed development runs did not admit the planned tests"})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": draft})])
    return FunctionModel(respond)


def tool_order(messages: list[ModelMessage]) -> list[str]:
    return [part.tool_name for message in messages if isinstance(message, ModelResponse)
            for part in message.parts if isinstance(part, ToolCallPart)]


def security_revealed(messages: list[ModelMessage]) -> int:
    """Development runs whose security view carried an outcome other than a setup error."""
    views = [DevelopmentRun.model_validate(part.content).security for message in messages
             if isinstance(message, ModelRequest) for part in message.parts
             if isinstance(part, ToolReturnPart) and part.tool_name == RUN_TOOL and part.outcome == "success"]
    return sum(1 for view in views if view not in (None, "withheld") and view.outcome != "error")


class EvaluationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=2, ge=1, le=3, strict=True)
    request_limit: int = Field(default=10, ge=1, le=12, strict=True)
    tool_calls_limit: int = Field(default=9, ge=0, le=10, strict=True)
    total_tokens_limit: int = Field(default=64000, ge=1, le=128000, strict=True)
    task_seconds: int = Field(default=300, ge=1, le=600, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)
    dev_runs: int = Field(default=3, ge=1, le=5, strict=True)


async def evaluate(evidence: Path, budget: EvaluationBudget):
    """Scripted fixture mode only: live authoring needs a qualified sandbox runner, which does not exist yet."""
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset()
    oracles = {case.inputs.fixture_id: case.metadata for case in corpus.cases}
    fixture_models = {case.inputs.fixture_id: scripted_model(case.inputs.inputs, case.metadata) for case in corpus.cases}
    metadata = {"mode": "scripted_fixture", "model": describe_model(next(iter(fixture_models.values()))),
                "runner": "scripted_observations", "weights_identity": "not_applicable",
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "budget": budget.model_dump(), "task_retries": 0, "max_concurrency": 1,
                "dataset_sha256": sha256((ROOT / "cases.yaml").read_bytes()).hexdigest(),
                "output_contract": "TestPatch | BlockedAuthoring",
                "draft_contract": "AuthoredPatchDraft | BlockedAuthoringDraft"}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.extend([NoUnknownToolAttempts(), MatchesAuthoring(), AuthoringTrajectory(),
                             MaxModelRequests(max_requests=budget.request_limit), MaxToolCalls(max_calls=budget.tool_calls_limit),
                             HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}}, evaluation_name="model_spans")])

    async def task(case: AuthoringCase):
        inputs = case.inputs
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        selected = fixture_models[case.fixture_id]
        runner = ScriptedRunner(oracles[case.fixture_id].runner_runs)
        known_tools = frozenset({READ_SOURCE_TOOL, WRITE_TOOL, RUN_TOOL}) | output_tool_names(selected)
        agent = create_test_authoring_agent(selected, output_retries=budget.output_retries)
        deps = AuthoringDependencies(inputs, runner, AuthoringBudget(dev_runs=budget.dev_runs))
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(False):
                result = await asyncio.wait_for(agent.run(authoring_prompt(inputs), deps=deps, usage=usage,
                    usage_limits=UsageLimits(request_limit=budget.request_limit, tool_calls_limit=budget.tool_calls_limit,
                                             total_tokens_limit=budget.total_tokens_limit)), timeout=budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "detail": str(exc)}
            raise
        finally:
            receipt = {"fixture_id": case.fixture_id, "input_digest": inputs.input_digest, "completed": result is not None, "failure": failure,
                       "elapsed_seconds": perf_counter() - started,
                       "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"), "usage_source": "scripted_estimate",
                       "runner_calls": runner.calls, "tool_order": tool_order(messages),
                       "security_revealed": security_revealed(messages),
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known_tools)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("input_digest", inputs.input_digest)
            set_eval_attribute("tool_order", receipt["tool_order"])
            set_eval_attribute("security_revealed", receipt["security_revealed"])
            set_eval_attribute("unknown_tool_attempts", receipt["unknown_tool_attempts"])
            for key, value in (("requests", usage.requests), ("tool_calls", usage.tool_calls),
                               ("dev_runs", len(runner.calls)), ("output_corrections", receipt["output_corrections"])):
                record_count("observed_" + key, value)

    report = await corpus.evaluate(task, repeat=budget.repeat, max_concurrency=1, retry_task=None, metadata=metadata, progress=False)
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
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")
    report = asyncio.run(evaluate(args.evidence, EvaluationBudget()))
    report.print(include_input=False, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
