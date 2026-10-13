"""Repository-scale identification (SPEC-0038): deterministic tool measurement and an explicit local-provider smoke.

Both modes capture the exact commit from an operator bare repository with the existing `GitSource`
into a private artifact store, build a `SourceTree` from that snapshot and run the real toolset.
`measure` drives the tools with a scripted model and records what each call returns against the
run byte budget; `live` runs the identification agent on the frozen cases with a configured model.
Oracles stay in this file's dataset metadata and are never sent to the agent.
"""

import argparse
import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import logfire
from openai import APIConnectionError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, MaxModelRequests, MaxToolCalls

from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
from corsair.agents.issue_analysis.repository_identification import (
    CONFIG_VERSION, PROMPT_VERSION, SKILL_SHA256, RepositoryDependencies, RepositoryIssueInput,
    create_repository_identification_agent, repository_identification_prompt,
)
from corsair.agents.source.repository import RepositoryLimits, SourceTree, UnreadableSource
from corsair.agents.source.repository_tools import REPOSITORY_TOOLS
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names

ROOT = Path(__file__).parent
# The README of benchmarks/cases/jspwiki-forwarding records these capture limits for the same commits.
CAPTURE_LIMITS = SourceLimits(max_files=2048, max_file_bytes=4 * 1024 * 1024, max_total_bytes=20 * 1024 * 1024,
                              wall_seconds=60, cpu_seconds=30)


class AllowedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    symbol: str
    required_lines: tuple[int, ...] = Field(min_length=1)
    max_span: int = 40


class RepositoryOracle(BaseModel):
    """Evaluator-only accepted selections; never given to the agent."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: str
    targets: tuple[AllowedTarget, ...] = ()


def selection_checks(inputs: RepositoryIssueInput, output: IssueIdentification, oracle: RepositoryOracle) -> dict[str, bool]:
    checks = {"status": output.status == oracle.status, "scope": output.scope == inputs.scope,
              "report_identity": output.reported_issue == inputs.issue}
    if oracle.status != "ready":
        return checks | {"abstention": output.target is None and bool(output.reason)}
    source = output.target.source if output.target else None
    matching = [t for t in oracle.targets if source and output.target.symbol == t.symbol and source.path == t.path]
    checks["target_selection"] = bool(matching)
    checks["source_range"] = any(all(source.start_line <= line <= source.end_line for line in t.required_lines)
                                 and source.end_line - source.start_line + 1 <= t.max_span for t in matching)
    return checks


@dataclass
class MatchesRepositorySelection(Evaluator[RepositoryIssueInput, IssueIdentification, RepositoryOracle]):
    def evaluate(self, ctx):
        return selection_checks(ctx.inputs, ctx.output, ctx.metadata) if ctx.metadata else {"oracle_present": False}


def dataset() -> Dataset[RepositoryIssueInput, IssueIdentification, RepositoryOracle]:
    return Dataset[RepositoryIssueInput, IssueIdentification, RepositoryOracle].from_file(
        ROOT / "cases.yaml", custom_evaluator_types=(MatchesRepositorySelection,))


def capture(repository: Path, commit: str, workspace: Path):
    """GitSource capture into a fresh private store; returns the open store context and the snapshot."""
    pin = lambda path: Executable(Path(path), sha256(Path(path).read_bytes()).hexdigest())
    workspace.mkdir(mode=0o700)
    for name in ("objects", "receipts"):
        (workspace / name).mkdir(mode=0o700)
    store = LocalArtifacts(workspace / "objects", max_bytes=CAPTURE_LIMITS.max_file_bytes)
    with GitSource(pin("/usr/bin/git"), pin("/usr/bin/prlimit"), store=store, limits=CAPTURE_LIMITS,
                   receipts=workspace / "receipts") as source:
        started = perf_counter()
        snapshot = source.capture(repository.resolve(), commit, uuid4())
    return store, snapshot, perf_counter() - started


def tree_profile(tree: SourceTree, limits: RepositoryLimits) -> dict:
    readable, skipped, inline_too_long, lines = 0, {}, 0, []
    for path in tree.sizes:
        try:
            count = len(tree.lines(path, limits))
        except UnreadableSource as exc:
            skipped[str(exc)] = skipped.get(str(exc), 0) + 1
            continue
        readable += 1
        lines.append(count)
        inline_too_long += tree.sizes[path] > 16384
    return {"files": len(tree.sizes), "bytes": sum(tree.sizes.values()), "readable_text_files": readable,
            "unreadable": skipped, "max_lines": max(lines, default=0), "total_lines": sum(lines),
            "files_over_inline_16384": inline_too_long}


def call_bytes(messages: list[ModelMessage]) -> list[dict]:
    calls = {p.tool_call_id: p for m in messages for p in m.parts if isinstance(p, ToolCallPart)}
    return [{"tool": p.tool_name, "args": calls[p.tool_call_id].args_as_dict() if p.tool_call_id in calls else None,
             "outcome": p.outcome, "bytes": len(p.model_response_str().encode()),
             "result_kind": type(p.content).__name__}
            for m in messages for p in m.parts if isinstance(p, ToolReturnPart) and p.tool_name in REPOSITORY_TOOLS]


def probe_model(steps: list[tuple[str, dict]], final: dict) -> FunctionModel:
    async def respond(messages, info):
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < len(steps) and {t.name for t in info.function_tools} >= {steps[step][0]}:
            return ModelResponse(parts=[ToolCallPart(*steps[step])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, final)])
    return FunctionModel(respond)


PROBE_STEPS = [
    ("list_source", {}),
    ("list_source", {"pattern": "*WikiServlet*.java"}),
    ("search_source", {"text": "getForwardPage", "pattern": "*.java"}),
    ("search_source", {"text": "forward", "pattern": "*.java", "ignore_case": True}),
    ("read_source", {"path": "jspwiki-main/src/main/java/org/apache/wiki/WikiServlet.java", "start_line": 80}),
    ("read_source", {"path": "jspwiki-main/src/main/java/org/apache/wiki/url/DefaultURLConstructor.java", "start_line": 270}),
    ("read_source", {"path": "jspwiki-main/src/main/java/org/apache/wiki/WikiServlet.java", "start_line": 85}),
]


async def measure(tree: SourceTree, case_inputs: RepositoryIssueInput, limits: RepositoryLimits) -> dict:
    deps = RepositoryDependencies(case_inputs, tree, limits)
    final = {"status": "ready", "scope": case_inputs.scope, "reason": None, "target": {"symbol": "getForwardPage", "source": {
        "path": "jspwiki-main/src/main/java/org/apache/wiki/url/DefaultURLConstructor.java", "start_line": 278, "end_line": 281}}}
    started = perf_counter()
    with capture_run_messages() as messages:
        result = await create_repository_identification_agent(probe_model(PROBE_STEPS, final), output_retries=0).run(
            repository_identification_prompt(case_inputs, tree, limits), deps=deps)
    calls = call_bytes(messages)
    return {"elapsed_seconds": perf_counter() - started, "calls": calls, "returned_bytes": sum(c["bytes"] for c in calls),
            "run_bytes": limits.run_bytes, "prompt_bytes": len(repository_identification_prompt(case_inputs, tree, limits).encode()),
            "output": result.output.model_dump(mode="json")}


class LiveBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=3, ge=1, le=5, strict=True)
    request_limit: int = Field(default=12, ge=1, le=16, strict=True)
    tool_calls_limit: int = Field(default=10, ge=1, le=14, strict=True)
    total_tokens_limit: int = Field(default=160000, ge=1, le=256000, strict=True)
    task_seconds: int = Field(default=300, ge=1, le=600, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)


async def live(evidence: Path, tree: SourceTree, model, budget: LiveBudget, limits: RepositoryLimits):
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset()
    metadata = {"mode": "direct_local_provider", "model": describe_model(model), "weights_identity": "unknown",
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "budget": budget.model_dump(), "repository_limits": asdict(limits), "task_retries": 0, "max_concurrency": 1,
                "dataset_sha256": sha256((ROOT / "cases.yaml").read_bytes()).hexdigest()}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.extend([NoUnknownToolAttempts(), ProviderUsageCoverage(),
                              MaxModelRequests(max_requests=budget.request_limit), MaxToolCalls(max_calls=budget.tool_calls_limit)])

    async def task(inputs: RepositoryIssueInput):
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        known = REPOSITORY_TOOLS | output_tool_names(model)
        deps = RepositoryDependencies(inputs, tree, limits)
        agent = create_repository_identification_agent(model, output_retries=budget.output_retries)
        try:
            with capture_run_messages() as messages:
                result = await asyncio.wait_for(agent.run(
                    repository_identification_prompt(inputs, tree, limits), deps=deps, usage=usage,
                    usage_limits=UsageLimits(request_limit=budget.request_limit, tool_calls_limit=budget.tool_calls_limit,
                                             total_tokens_limit=budget.total_tokens_limit)), timeout=budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "detail": str(exc),
                       "uncertain_delivery": isinstance(exc, (TimeoutError, asyncio.CancelledError, APIConnectionError)),
                       "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None}
            raise
        finally:
            responses = [m for m in messages if isinstance(m, ModelResponse)]
            calls = call_bytes(messages)
            receipt = {"input_digest": inputs.input_digest, "completed": result is not None, "failure": failure,
                       "elapsed_seconds": perf_counter() - started, "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                       "provider_usage_present": bool(responses) and all(m.usage.has_values() for m in responses),
                       "tool_results": calls, "returned_bytes": sum(c["bytes"] for c in calls),
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("unknown_tool_attempts", receipt["unknown_tool_attempts"])
            set_eval_attribute("provider_usage_present", receipt["provider_usage_present"])
            for key, value in (("requests", usage.requests), ("tool_calls", usage.tool_calls),
                               ("input_tokens", usage.input_tokens), ("output_tokens", usage.output_tokens),
                               ("returned_bytes", receipt["returned_bytes"]),
                               ("repeated_reads", sum(c["result_kind"] == "RepeatedRead" for c in calls))):
                record_count("observed_" + key, value)

    with models.override_allow_model_requests(True):
        report = await corpus.evaluate(task, repeat=budget.repeat, max_concurrency=1, retry_task=None,
                                       metadata=metadata, progress=False)
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("measure", "live"))
    parser.add_argument("--repository", type=Path, required=True, help="Complete private operator bare repository")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="LocalModelConfig JSON; required for live")
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")
    if (args.mode == "live") != (args.provider_config is not None):
        parser.error("--provider-config is required for live and refused for measure")
    args.evidence.mkdir(parents=True, mode=0o700)
    corpus = dataset()
    commits = {case.inputs.repository.commit for case in corpus.cases}
    if len(commits) != 1:
        parser.error("one repository commit per run")
    limits = RepositoryLimits()
    store, snapshot, capture_seconds = capture(args.repository, commits.pop(), args.evidence / "capture")
    with store:
        tree = SourceTree.from_snapshot(snapshot, store)
        if any(tree.identity != (c.inputs.repository.commit, c.inputs.repository.tree) for c in corpus.cases):
            raise SystemExit("captured tree does not match the case repository identity")
        summary = {"commit": snapshot.commit, "tree": snapshot.tree, "manifest": asdict(snapshot.manifest),
                   "capture_seconds": capture_seconds, "profile": tree_profile(tree, limits), "limits": asdict(limits)}
        if args.mode == "measure":
            with models.override_allow_model_requests(False):
                summary["probe"] = asyncio.run(measure(tree, corpus.cases[0].inputs, limits))
            (args.evidence / "measure.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps({k: v for k, v in summary.items() if k != "probe"} | {"probe": {
                k: v for k, v in summary["probe"].items() if k != "output"}}, indent=2))
            return
        (args.evidence / "tree.json").write_text(json.dumps(summary, indent=2))
        config = LocalModelConfig.model_validate_json(args.provider_config.read_text())

        async def run():
            async with local_model(config) as model:
                return await live(args.evidence, tree, model, LiveBudget(), limits)
        report = asyncio.run(run())
        report.print(include_input=False, include_output=False)


if __name__ == "__main__":
    os.umask(0o077)
    main()
