"""Deterministic authoring checks over frozen development cases on the host; no LLM judge, no sandbox.

Scripted mode replays a fixed author; live mode (--provider-config) runs the real model. Either way the
runs are answered by injected observations or the static host runner (SPEC-0044); nothing is executed.
"""

import argparse
import asyncio
from dataclasses import dataclass, replace
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
from openai import APIConnectionError
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, HasMatchingSpan, MaxModelRequests, MaxToolCalls

from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from corsair.agents.source.tools import READ_SOURCE_TOOL
from corsair.agents.test_authoring.agent import (
    CONFIG_VERSION, PROMPT_VERSION, authoring_prompt, create_test_authoring_agent,
)
from corsair.agents.test_authoring.contracts import BlockedAuthoring, DevelopmentRun, TestAuthoringInput, TestPatch
from corsair.agents.test_authoring.skills import SKILL_SHA256
from corsair.agents.test_authoring.static import static_checks
from corsair.agents.test_authoring.dependencies import AuthoringBudget, AuthoringDependencies
from corsair.agents.test_authoring.tools import RUN_TOOL, TOOLSET_SHA256, WRITE_TOOL
from corsair.ports.test_runner import (
    ApprovedPatch, Discovery, Execution, FailureDetail, NativeTestRun, TestCaseResult,
)
from evals.cases import LANGUAGES, load_set, set_digest, set_names
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names
from evals.test_authoring import languages
from evals.test_authoring.admission import admission_facts, witness_hooks
from evals.test_authoring.static_runner import StaticRunner

ROOT = Path(__file__).parent
REPOSITORY = ROOT.parents[1]
# The reviewed SPEC-0018 realization; scripted plumbing writes it, never a model.
FILES = {"sql_unit": (REPOSITORY / "benchmarks/fixtures/sql-query-construction/test_queries.py").read_text(),
         "reference": (REPOSITORY / "benchmarks/fixtures/path-traversal/test_documents.py").read_text(),
         # An absence plan (no_file_open) realized as the skill asks: catch around the call, assert on what it returned.
         "absence": (ROOT / "absence_realization.py").read_text(),
         "broken": "import pytest\nimport documents\n\ndef test_benign_control(:\n    pass\n",
         # What live authors wrote in PLAN-0039: their own audit hook beside the operator witness.
         "self_observing": ("import sys\nimport documents\n\nOPENS = []\nsys.addaudithook(lambda event, args: "
                            "OPENS.append(args[0]) if event == 'open' else None)\n\n\ndef test_benign_control(tmp_path):\n"
                            "    (tmp_path / 'd.txt').write_text('x')\n    assert documents.read_document(tmp_path, 'd.txt') == 'x'\n")}
AuthoringOutput = TestPatch | BlockedAuthoring


class ScriptedRun(BaseModel):
    """One development run's answer: an injected observation, or ``static`` for the static host runner."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["discovered", "collection_error", "static"]
    control: Literal["passed", "failed"] = "passed"
    security: Literal["passed", "failed", "skipped"] = "failed"
    # The failed security test's reported type; another type than the plan's is an error before the assertion.
    security_failure: str = "AssertionError"
    # A collection_error's native discovery text; omitted keeps the pytest text the development set was frozen with.
    errors: str | None = None


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
    # Named test files a per-case oracle carries for its scripted author's `write` steps; a name here takes
    # precedence over the shared FILES, which the single-file sets use.
    files: dict[str, str] = Field(default_factory=dict)


class ScriptedRunner:
    """Test double for the TestRunner port: replays fixed observations, executes nothing.

    Run n gets entry n, and the last entry once they are spent, so a live author that runs more often than
    the scripted one still sees the case's condition; ``static`` entries go to the static host runner.
    """

    def __init__(self, runs: tuple[ScriptedRun, ...], static: StaticRunner | None = None):
        self.runs, self.static, self.calls, self.sources = runs, static, [], []

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID, witness=None) -> NativeTestRun:
        self.calls.append(patch.sha256)
        if not self.runs:
            raise ValueError("the case scripts no development run; give it a runner_runs entry for live authors")
        scripted = self.runs[min(len(self.calls), len(self.runs)) - 1]
        self.sources.append("static_simulated" if scripted.status == "static" else "injected")
        if scripted.status == "static":
            if self.static is None:
                raise ValueError("static run requested without a static host runner")
            return self.static.run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                                   discovery_command=discovery_command, operation=operation)
        if scripted.status == "collection_error":
            discovery = Discovery("collection_error", (), scripted.errors or "E   SyntaxError: invalid syntax",
                                  discovery_command, None)
            return NativeTestRun(str(operation), patch.sha256, None, discovery, None, "confirmed", "discovery",
                                 "collection error")
        ids = (control_test_id, security_test_id)
        failure = FailureDetail("failure", "AssertionError", security_test_id.split("::")[0],
                                security_test_id.split("::")[-1], 64, "AssertionError: scripted")
        security = replace(failure, type=scripted.security_failure, message=f"{scripted.security_failure}: scripted")
        cases = (TestCaseResult(control_test_id, scripted.control,
                                failure if scripted.control == "failed" else None, ""),
                 TestCaseResult(security_test_id, scripted.security,
                                security if scripted.security == "failed" else None, ""))
        execution = Execution("completed", cases, None, None, "", ("sh", "-c", "scripted"), None)
        return NativeTestRun(str(operation), patch.sha256, None,
                             Discovery("discovered", ids, "", discovery_command, None), execution, "confirmed", None, "")


def authoring_checks(inputs: TestAuthoringInput, output: AuthoringOutput, oracle: AuthoringOracle,
                     live: bool = False) -> dict[str, bool]:
    """Scripted mode also pins the scripted author's run count and assertion lines; a live author may differ."""
    checks = {"status": output.status == oracle.status}
    if not live:
        checks["dev_runs"] = len([r for r in output.dev_runs if r.status != "not_run"]) == oracle.runs
    if isinstance(output, BlockedAuthoring):
        return checks | {"layer": output.layer == oracle.layer and bool(output.reason.strip())}
    plan, approved = inputs.plan, inputs.environment.approved_test_paths
    files = {item.path: item.content for item in output.files}
    language = languages.language_of(plan.security.test_id)
    if language != "python":
        return checks | _language_checks(language, inputs, output, oracle, files, live)
    symbol = plan.control.implementation_call.split("(")[0].split(".")[-1]
    absence = plan.security.test_id if plan.security_expectation.safe_behavior.startswith("no_") else None
    statics = [static_checks(files.get(spec.test_path, ""), spec.test_id, symbol, absence_test=absence)
               for spec in (plan.control, plan.security)]
    if plan.security.witness is None:
        # Unit plans admit dependency doubles; validity review establishes that the real target remains exercised.
        # The shared stage admission facts still protect global facilities and evidence machinery.
        statics = [{key: value for key, value in facts.items() if key != "no_mock"} for facts in statics]
    checks |= {
        "contract": set(files) <= set(approved) and output.control_test_id == plan.control.test_id
                    and output.security_test_id == plan.security.test_id
                    and output.discovery_command == plan.discovery_command,
        "static_semantics": all(all(checks.values()) for checks in statics),
    }
    if not live:
        checks["security_assertion_lines"] = output.security_assertion_lines == oracle.security_assertion_lines
    return checks | admission_facts(plan, files, output.security_assertion_lines)


def _language_checks(language: str, inputs: TestAuthoringInput, output: TestPatch, oracle: AuthoringOracle,
                     files: dict[str, str], live: bool) -> dict[str, bool]:
    """The same check names for a Minitest, Jest, JUnit or TAP patch, from ``languages.py``'s facts."""
    plan = inputs.plan
    statics = [languages.static_facts(language, files.get(spec.test_path, ""), spec.test_id, spec.implementation_call)
               for spec in (plan.control, plan.security)]
    checks = {
        "contract": set(files) <= set(inputs.environment.approved_test_paths)
                    and output.control_test_id == plan.control.test_id
                    and output.security_test_id == plan.security.test_id
                    and output.discovery_command == plan.discovery_command,
        "static_semantics": all(all(facts.values()) for facts in statics),
    }
    if not live:
        checks["security_assertion_lines"] = output.security_assertion_lines == oracle.security_assertion_lines
    return checks | languages.admission_facts(language, plan, files, output.security_assertion_lines)


@dataclass
class MatchesAuthoring(Evaluator[AuthoringCase, AuthoringOutput, AuthoringOracle]):
    live: bool = False

    def evaluate(self, ctx):
        if ctx.metadata is None:
            return {"oracle_present": False}
        checks = authoring_checks(ctx.inputs.inputs, ctx.output, ctx.metadata, self.live)
        if isinstance(ctx.output, TestPatch):
            # A score, not an assertion: reported per attempt so a prompt change can be compared on it.
            checks["author_witness_hooks"] = sum(witness_hooks(item.content) for item in ctx.output.files)
        return checks


@dataclass
class AuthoringTrajectory(Evaluator[AuthoringCase, AuthoringOutput, AuthoringOracle]):
    """Read before write, write before run, the security outcome never shown to the author."""
    def evaluate(self, ctx):
        order = ctx.attributes.get("tool_order") or []
        first = lambda name: order.index(name) if name in order else len(order)
        return {"read_before_write": first(READ_SOURCE_TOOL) < first(WRITE_TOOL),
                "write_before_run": first(WRITE_TOOL) < first(RUN_TOOL),
                "security_withheld": ctx.attributes.get("security_revealed") == 0}


SUITE = "test_authoring"
# Every set is a frozen manifest of per-case directories (evals/cases.py). breadth_pending holds cases production
# refuses today for a recorded missing language capability; it runs through ``pending`` and is expected to fail
# until that capability lands.
DATASETS = tuple(set_names(SUITE))


def dataset(name: str = "development", language: str | None = None) -> Dataset[AuthoringCase, AuthoringOutput, AuthoringOracle]:
    return Dataset[AuthoringCase, AuthoringOutput, AuthoringOracle](name=f"test-authoring-{name}", cases=[
        Case(name=case.name, inputs=AuthoringCase.model_validate(case.input),
             metadata=AuthoringOracle.model_validate(case.oracle)) for case in load_set(SUITE, name, language)])


def scripted_model(inputs: TestAuthoringInput, oracle: AuthoringOracle) -> FunctionModel:
    """Oracle injection is confined to the scripted plumbing model, never live task inputs."""
    plan = inputs.plan
    reads = [plan.security.source_references[0].path]
    if inputs.environment.baseline_test is not None:
        reads.append(inputs.environment.baseline_test.path)
    steps = [ToolCallPart(READ_SOURCE_TOOL, {"path": path}) for path in reads]
    for step in oracle.script:
        if "write" in step:
            content = oracle.files.get(step["write"]) or FILES[step["write"]]
            steps.append(ToolCallPart(WRITE_TOOL, {"path": plan.security.test_path, "content": content}))
        elif "read" in step:
            steps.append(ToolCallPart(READ_SOURCE_TOOL, {"path": step["read"]}))
        else:
            steps.append(ToolCallPart(RUN_TOOL, {}))

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(steps):
            return ModelResponse(parts=[steps[done]])
        draft = ({"status": "patch", "security_assertion_lines": list(oracle.security_assertion_lines),
                  "limitations": ["Development runs observe buildability and discovery, not the security outcome"]}
                 if oracle.status == "patch" else
                 # Trusted code assigns the admission layer; the model-facing draft cannot name it.
                 {"status": "blocked", "layer": "unknown" if oracle.layer == "admission" else oracle.layer,
                  "reason": "The observed development runs did not admit the planned tests"})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": draft})])
    return FunctionModel(respond)


def tool_order(messages: list[ModelMessage]) -> list[str]:
    return [part.tool_name for message in messages if isinstance(message, ModelResponse)
            for part in message.parts if isinstance(part, ToolCallPart)]


def unread_sources(messages: list[ModelMessage]) -> int:
    """read_source calls answered not_in_source or past_end: typed answers the stage survived."""
    return sum(1 for message in messages if isinstance(message, ModelRequest) for part in message.parts
               if isinstance(part, ToolReturnPart) and part.tool_name == READ_SOURCE_TOOL and part.outcome == "success"
               and (part.content.get("status") if isinstance(part.content, dict) else getattr(part.content, "status", None))
               in ("not_in_source", "past_end"))


def security_revealed(messages: list[ModelMessage]) -> int:
    """Development runs whose security view carried an outcome other than a setup error."""
    views = [DevelopmentRun.model_validate(part.content).security for message in messages
             if isinstance(message, ModelRequest) for part in message.parts
             if isinstance(part, ToolReturnPart) and part.tool_name == RUN_TOOL and part.outcome == "success"]
    return sum(1 for view in views if view not in (None, "withheld") and view.outcome != "error")


class EvaluationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=2, ge=1, le=5, strict=True)
    request_limit: int = Field(default=10, ge=1, le=12, strict=True)
    tool_calls_limit: int = Field(default=9, ge=0, le=10, strict=True)
    # Room for one full 32768-token response (~235 s on the local server) beside the rest of the attempt.
    total_tokens_limit: int = Field(default=128000, ge=1, le=262144, strict=True)
    task_seconds: int = Field(default=900, ge=1, le=1800, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)
    dev_runs: int = Field(default=3, ge=1, le=5, strict=True)


async def evaluate(evidence: Path, budget: EvaluationBudget, *, model=None, provider=None, cases="development",
                   corpus: Dataset | None = None, language: str | None = None):
    """Host only: runs are answered by injected observations or the static host runner, never executed."""
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = corpus if corpus is not None else dataset(cases, language)
    scripted = model is None
    oracles = {case.inputs.fixture_id: case.metadata for case in corpus.cases}
    fixture_models = {case.inputs.fixture_id: scripted_model(case.inputs.inputs, case.metadata) for case in corpus.cases} if scripted else {}
    actual_model = model if model is not None else next(iter(fixture_models.values()))
    metadata = {"mode": "scripted_fixture" if scripted else "direct_local_provider", "model": describe_model(actual_model),
                "runner": "injected_observations_and_static_host_runner", "execution": "simulated_not_executed",
                "weights_identity": "not_applicable" if scripted else "unknown", "provider": provider,
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "toolset_sha256": TOOLSET_SHA256,
                "budget": budget.model_dump(), "task_retries": 0, "max_concurrency": 1,
                "dataset": cases, "language": language, "dataset_sha256": set_digest(SUITE, cases),
                "output_contract": "TestPatch | BlockedAuthoring",
                "draft_contract": "AuthoredPatchDraft | BlockedAuthoringDraft"}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    if not scripted:
        corpus.evaluators.append(ProviderUsageCoverage())
    corpus.evaluators.extend([NoUnknownToolAttempts(), MatchesAuthoring(live=not scripted), AuthoringTrajectory(),
                             MaxModelRequests(max_requests=budget.request_limit), MaxToolCalls(max_calls=budget.tool_calls_limit),
                             HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}}, evaluation_name="model_spans")])

    async def task(case: AuthoringCase):
        inputs = case.inputs
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        selected = fixture_models[case.fixture_id] if scripted else model
        runner = ScriptedRunner(oracles[case.fixture_id].runner_runs, StaticRunner(inputs.source_files))
        known_tools = frozenset({READ_SOURCE_TOOL, WRITE_TOOL, RUN_TOOL}) | output_tool_names(selected)
        agent = create_test_authoring_agent(selected, output_retries=budget.output_retries)
        deps = AuthoringDependencies(inputs, runner, AuthoringBudget(dev_runs=budget.dev_runs))
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(not scripted):
                result = await asyncio.wait_for(agent.run(authoring_prompt(inputs), deps=deps, usage=usage,
                    usage_limits=UsageLimits(request_limit=budget.request_limit, tool_calls_limit=budget.tool_calls_limit,
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
            receipt = {"fixture_id": case.fixture_id, "input_digest": inputs.input_digest, "completed": result is not None, "failure": failure,
                       "elapsed_seconds": perf_counter() - started,
                       "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                       "usage_source": "scripted_estimate" if scripted else "native_responses_partial_on_failure",
                       "provider_usage_present": None if scripted else bool(responses) and all(m.usage.has_values() for m in responses),
                       "response_ids": [m.provider_response_id for m in responses],
                       "runner_calls": runner.calls, "runner_sources": runner.sources, "tool_order": tool_order(messages),
                       "security_revealed": security_revealed(messages),
                       "unread_sources": unread_sources(messages),
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known_tools)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("input_digest", inputs.input_digest)
            set_eval_attribute("tool_order", receipt["tool_order"])
            set_eval_attribute("security_revealed", receipt["security_revealed"])
            set_eval_attribute("unknown_tool_attempts", receipt["unknown_tool_attempts"])
            set_eval_attribute("provider_usage_present", receipt["provider_usage_present"])
            for key, value in (("requests", usage.requests), ("tool_calls", usage.tool_calls),
                               ("input_tokens", usage.input_tokens), ("output_tokens", usage.output_tokens),
                               ("dev_runs", len(runner.calls)), ("output_corrections", receipt["output_corrections"]),
                               ("unread_sources", receipt["unread_sources"])):
                record_count("observed_" + key, value)

    report = await corpus.evaluate(task, repeat=budget.repeat, max_concurrency=1, retry_task=None, metadata=metadata, progress=False)
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    return report


# The production refusal a pending case records today: the authoring contracts admit pytest and Minitest ids only.
INPUT_GRAMMAR = "is not a supported native node id"


async def pending(evidence: Path, budget: EvaluationBudget) -> dict[str, dict]:
    """Run breadth_pending case by case, scripted: a case production refuses as input is recorded with that
    refusal; an admitted one runs as any other case. Every outcome is written to ``pending.json``."""
    evidence.mkdir(parents=True, exist_ok=False)
    outcomes: dict[str, dict] = {}
    for case in load_set(SUITE, "breadth_pending"):
        try:
            inputs = AuthoringCase.model_validate(case.input)
        except ValueError as exc:
            errors = exc.errors() if hasattr(exc, "errors") else [{"msg": str(exc)}]
            outcomes[case.name] = {"outcome": "refused_input", "reason": "; ".join(e["msg"] for e in errors)}
            continue
        corpus = Dataset[AuthoringCase, AuthoringOutput, AuthoringOracle](name=f"test-authoring-pending-{case.name}", cases=[
            Case(name=case.name, inputs=inputs, metadata=AuthoringOracle.model_validate(case.oracle))])
        report = await evaluate(evidence / case.name, budget, cases="breadth_pending", corpus=corpus)
        retries = sorted({part["content"] if isinstance(part["content"], str) else json.dumps(part["content"])
                          for receipt in (evidence / case.name).glob("attempt-*.json")
                          for message in json.loads(receipt.read_text())["messages"]
                          for part in message.get("parts", ()) if part.get("part_kind") == "retry-prompt"})
        outcomes[case.name] = ({"outcome": "passed"} if passed(report) else
                               {"outcome": "failed", "reason": "; ".join(f.error_message for f in report.failures)
                                or "evaluator checks failed", "retries": retries})
    (evidence / "pending.json").write_text(json.dumps(outcomes, indent=2))
    return outcomes


def passed(report) -> bool:
    return bool(report.cases) and not report.failures and not report.report_evaluator_failures and all(
        not case.evaluator_failures and case.assertions and all(item.value for item in case.assertions.values())
        and case.attributes.get("unknown_tool_attempts") == 0 for case in report.cases
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Explicit provider configuration JSON; omitted means scripted fixture only")
    parser.add_argument("--cases", choices=DATASETS, default="development")
    parser.add_argument("--language", choices=LANGUAGES, help="only this language's cases of the set")
    parser.add_argument("--repeat", type=int, default=EvaluationBudget().repeat)
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")

    if args.cases == "breadth_pending":
        if args.provider_config is not None:
            parser.error("breadth_pending runs scripted only")
        outcomes = asyncio.run(pending(args.evidence, EvaluationBudget(repeat=args.repeat)))
        for name, outcome in outcomes.items():
            print(f"{name}: {outcome['outcome']} {outcome.get('reason', '')}")
        print(f"pending: {sum(o['outcome'] == 'passed' for o in outcomes.values())}/{len(outcomes)} passed")
        if not all(outcome["outcome"] == "passed" for outcome in outcomes.values()):
            raise SystemExit(1)
        return

    async def run():
        budget = EvaluationBudget(repeat=args.repeat)
        if args.provider_config is None:
            return await evaluate(args.evidence, budget, cases=args.cases, language=args.language)
        config = load_agent_config(args.provider_config, "authoring")
        async with configured_model(config) as model:
            return await evaluate(args.evidence, budget, model=model, cases=args.cases, language=args.language,
                                  provider=config.model_dump(mode="json", exclude={"api_key_env"}))
    report = asyncio.run(run())
    report.print(include_input=False, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
