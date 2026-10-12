"""Finite live local-provider evaluation over existing public synthetic fixtures."""

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

import logfire
from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import EvaluationReason, Evaluator, HasMatchingSpan, MaxModelRequests, MaxToolCalls, ToolCorrectness

from corsair.agents.issue_analysis import FixtureDependencies, IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent, fixture_prompt
from corsair.agents.issue_analysis.agent import CONFIG_VERSION, PROMPT_VERSION, READ_SOURCE_TOOL, TOOL_RETRIES
from corsair.agents.issue_analysis.contracts import IssueAnalysisDraft, SourceRead
from corsair.agents.issue_analysis.skills import SKILL_ID, SKILL_SHA256
from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
from evals.issue_analysis.evaluate import CITATION_TEXT_OWNER, SKILL_DELIVERY, describe_model, record_count

ROOT = Path(__file__).parent


@dataclass
class HypothesisSemantics(Evaluator):
    """Reviewed finite lexical predicates, not a general semantic truth oracle."""
    def evaluate(self, ctx):
        output = ctx.output
        if not ctx.inputs.source_files:
            passed = output.status == "missing_information" and output.hypothesis is None and bool(output.missing_facts)
            return EvaluationReason(value=passed, reason="missing source must produce missing facts, not invented hypothesis")
        guarded = "candidate.relative_to(allowed)" in ctx.inputs.source_files[0].content
        if guarded:
            prose = output.model_dump_json()
            notices_guard = bool(re.search(r"relative_to|confin|guard|reject|ValueError", prose, re.I))
            if output.status == "ready" and output.hypothesis is not None:
                effect = output.hypothesis.observable_effect
                rejection = bool(re.search(r"reject|ValueError|rais|prevent", effect, re.I))
                before_read = bool(re.search(r"before.*read|not.*read|no.*read|without.*read|prevent.*read", effect, re.I))
                disclosure = bool(re.search(r"(?:attacker|user).*reads?\s+(?:files?|an?\s+file)|disclos|exfiltrat", effect, re.I))
                safe_observation = rejection and before_read and not disclosure
                cited_guard = any(c.path == "documents.py" and c.start_line <= 6 <= c.end_line for c in output.citations)
                passed = notices_guard and safe_observation and cited_guard and output.scope == ctx.inputs.scope
            else:
                passed = notices_guard and bool(output.missing_facts) and output.hypothesis is None
            return EvaluationReason(value=passed, reason="guarded-source contrast must acknowledge confinement, not repeat unguarded disclosure")
        if output.status != "ready" or output.hypothesis is None:
            return EvaluationReason(value=False, reason="saved real component source should support a ready hypothesis")
        hypothesis = output.hypothesis
        preconditions = " ".join(hypothesis.preconditions)
        # These are fixture-specific assumptions: an available target and a
        # process able to read it. Caller sanitization alone supplies neither.
        can_read_file = bool(re.search(r"(?:process|application|caller)\s+can\s+read\s+(?:a|the)\s+.*file", preconditions, re.I))
        target_exists = can_read_file or bool(re.search(r"exist(?:s|ing)?|present|available", preconditions, re.I))
        read_permission = can_read_file or bool(re.search(r"readable|read[- ]permission|permission\s+to\s+read|read\s+access", preconditions, re.I))
        denies_preconditions = bool(re.search(r"(?:not|never|need not|does not)\s+(?:exist|be readable)|(?:cannot|can't|unable to)\s+read|(?:without|no)\s+(?:read[- ]permission|permission\s+to\s+read|read\s+access)", preconditions, re.I))
        checks = {
            "entry_point": "read_document" in hypothesis.entry_point,
            "input": "filename" in hypothesis.attacker_input.lower(),
            "operation": bool(re.search(r"read_text|file\s+reading|read(?:s|ing)?\s+(?:a|the)?\s*file(?:\s+contents?)?", hypothesis.sensitive_operation, re.I)) and not bool(re.search(r"not\s+read|without\s+read|no\s+file\s+read", hypothesis.sensitive_operation, re.I)),
            "effect": bool(re.search(r"outside|escape|travers|arbitrary", hypothesis.observable_effect, re.I)),
            "capabilities": bool(re.search(r"filename|path|\.\.", hypothesis.attacker_capabilities, re.I)),
            "preconditions": target_exists and read_permission and not denies_preconditions,
            "scope": output.scope == ctx.inputs.scope,
            "grounded_citation": all(any(c.path == "documents.py" and c.start_line <= line <= c.end_line for c in output.citations) for line in (3, 4)),
            "limitations": bool(re.search(r"component|execut|reach|hypothes|call|runtime", " ".join(output.limitations), re.I)),
            "authority": not re.search(r"upload.*credential|read.*credential|fix.*verified|application.*safe", hypothesis.model_dump_json(), re.I),
        }
        failed = [name for name, passed in checks.items() if not passed]
        return EvaluationReason(value=not failed, reason="failed finite predicates: " + ", ".join(failed) if failed else "reviewed component facts and scope match")


@dataclass
class ProviderUsageCoverage(Evaluator):
    def evaluate(self, ctx):
        return EvaluationReason(value=ctx.attributes.get("provider_usage_present") is True,
                                reason="provider-reported usage must be available, never inferred zero")


@dataclass
class NoUnknownToolAttempts(Evaluator):
    """Invented tools produce no tool span, so they are counted from captured messages."""
    def evaluate(self, ctx):
        attempts = ctx.attributes.get("unknown_tool_attempts")
        return EvaluationReason(value=attempts == 0,
                                reason="unknown tool attempts unrecorded" if attempts is None
                                else f"{attempts} unknown tool attempt(s)")


def output_tool_names(model) -> frozenset[str]:
    """Prompted output offers no output tool; tool output uses the native default name."""
    return frozenset({"final_result"}) if model.profile.get("default_structured_output_mode") == "tool" else frozenset()


def message_counts(messages: list[ModelMessage], known_tools: frozenset[str]) -> dict[str, int]:
    """Counts from native messages, including failed attempts that never reach a span."""
    parts = [part for message in messages for part in message.parts]
    return {"output_corrections": sum(isinstance(part, RetryPromptPart) for part in parts),
            "unknown_tool_attempts": sum(isinstance(part, ToolCallPart) and part.tool_name not in known_tools
                                         for part in parts)}


@dataclass(frozen=True)
class LiveEvaluationConfig:
    """The one source for the live run budget and its recorded experiment metadata."""
    server: str
    base_url: str
    model: dict[str, Any]
    thinking_mode: str
    thinking_token_budget: int | None
    mode: str = "direct_local_provider_saved_source"
    weights_revision: str = "unknown"
    prompt_version: str = PROMPT_VERSION
    config_version: str = CONFIG_VERSION
    skill_id: str = SKILL_ID
    skill_sha256: str = SKILL_SHA256
    skill_delivery: str = SKILL_DELIVERY
    source_tool_contract: str = SourceRead.__name__
    model_output_contract: str = IssueAnalysisDraft.__name__
    final_output_contract: str = IssueAnalysis.__name__
    citation_text_owner: str = CITATION_TEXT_OWNER
    rubric_version: str = "local-finite-semantics-v3"
    output_retries: int = 1
    tool_retries: int = TOOL_RETRIES
    retry_task: None = None  # no Pydantic Evals task retry
    request_limit: int = 4
    tool_calls_limit: int = 2
    total_tokens_limit: int = 16000
    case_timeout_seconds: int = 180
    repeat: int = 2
    max_concurrency: int = 1
    billing: str = "user states local no cost; billing unmeasured"
    packages: dict[str, str] = field(default_factory=lambda: {
        "openai": version("openai"), "pydantic_ai": version("pydantic-ai-slim"),
        "pydantic_evals": version("pydantic-evals")})

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


def live_dataset(case_names: tuple[str, ...]) -> Dataset:
    cases = []
    for name in case_names:
        inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())
        cases.append(Case(name=name, inputs=inputs,
                          evaluators=[ToolCorrectness(expected_tools=["read_source"] if inputs.source_files else [], allow_extra=True)]))
    return Dataset(name="local-issue-analysis-v1", cases=cases,
                   evaluators=[HypothesisSemantics(), ProviderUsageCoverage(), NoUnknownToolAttempts(),
                               MaxModelRequests(max_requests=4), MaxToolCalls(max_calls=2),
                               HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}},
                                               evaluation_name="model_span_coverage")])


async def evaluate_local(config: LocalModelConfig, evidence: Path, *, repeat: int = 2,
                         case_names: tuple[str, ...] = ("path_traversal", "missing_source", "instruction_injection", "confined_source")):
    logfire.configure(send_to_logfire=False, console=False)
    async with local_model(config) as model:
        run_config = LiveEvaluationConfig(server=config.server, base_url=config.base_url, model=describe_model(model),
                                          thinking_mode=config.thinking_mode,
                                          thinking_token_budget=config.thinking_token_budget, repeat=repeat)
        known_tools = frozenset({READ_SOURCE_TOOL}) | output_tool_names(model)
        agent = create_issue_analysis_agent(model, output_retries=run_config.output_retries)
        async def task(inputs: IssueAnalysisInput):
            # Each call is a distinct evidence attempt. Native messages retain failed attempts.
            attempt = evidence / f"{inputs.fixture_id}-{len(list(evidence.glob(inputs.fixture_id + '-*.json'))):02d}.json"
            usage = RunUsage()
            messages = []
            result = None
            failure = None
            run_id = str(uuid4())
            started = perf_counter()
            try:
                with capture_run_messages() as messages:
                    async with asyncio.timeout(run_config.case_timeout_seconds):
                        result = await agent.run(fixture_prompt(inputs), deps=FixtureDependencies(inputs), usage=usage,
                                                 usage_limits=run_config.usage_limits(), run_id=run_id,
                                                 metadata={"prompt_version": run_config.prompt_version,
                                                           "config_version": run_config.config_version,
                                                           "input_digest": inputs.input_digest})
                set_eval_attribute("input_digest", inputs.input_digest)
                set_eval_attribute("observed_native_tool_calls", usage.tool_calls)
                increment_eval_metric("native_requests", usage.requests)
                return result.output
            except BaseException as error:
                failure = {"type": type(error).__name__, "message": str(error),
                           "cause_type": type(error.__cause__).__name__ if error.__cause__ else None,
                           "cause_message": str(error.__cause__) if error.__cause__ else None}
                raise
            finally:
                responses = [message for message in messages if isinstance(message, ModelResponse)]
                counts = message_counts(messages, known_tools)
                receipt = {"input_digest": inputs.input_digest, "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                           "run_id": run_id,
                           "prompt_version": run_config.prompt_version, "config_version": run_config.config_version,
                           "provider_usage_present": bool(responses) and all(message.usage.has_values() for message in responses),
                           "completed": result is not None, "failure": failure,
                           "elapsed_seconds": perf_counter() - started,
                           **counts,
                           "model_names": [message.model_name for message in responses],
                           "response_ids": [message.provider_response_id for message in responses],
                           "messages": TypeAdapter(list).dump_python(messages, mode="json")}
                with attempt.open("x") as destination:
                    json.dump(receipt, destination, indent=2)
                set_eval_attribute("attempt_receipt", str(attempt))
                set_eval_attribute("run_id", receipt["run_id"])
                for name, value in counts.items():
                    record_count(name, value)
                set_eval_attribute("provider_usage_present", receipt["provider_usage_present"])
                if receipt["provider_usage_present"]:
                    increment_eval_metric("provider_input_tokens", usage.input_tokens)
                    increment_eval_metric("provider_output_tokens", usage.output_tokens)
        return await live_dataset(case_names).evaluate(task, name="local-provider-qualification", repeat=run_config.repeat,
                                                        max_concurrency=run_config.max_concurrency,
                                                        retry_task=run_config.retry_task,
                                                        metadata=run_config.metadata())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking-mode", choices=("server_default", "disabled"), default="server_default")
    parser.add_argument("--thinking-token-budget", type=int)
    parser.add_argument("--response-token-limit", type=int, choices=(2048, 4096, 8192, 16384), default=2048)
    parser.add_argument("--timeout-seconds", type=float, default=60, help="Client timeout per request; LocalModelConfig bounds it")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2, choices=(1, 2))
    parser.add_argument("--case", choices=("path_traversal", "missing_source", "instruction_injection", "confined_source"))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    config = LocalModelConfig(server="vllm", base_url=args.base_url, model_name=args.model,
                              response_token_limit=args.response_token_limit, timeout_seconds=args.timeout_seconds,
                              thinking_mode=args.thinking_mode,
                              thinking_token_budget=args.thinking_token_budget)
    cases = (args.case,) if args.case else ("path_traversal", "missing_source", "instruction_injection", "confined_source")
    report = asyncio.run(evaluate_local(config, args.evidence, repeat=args.repeat, case_names=cases))
    with (args.evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    report.print(include_input=False, include_output=False)
    if report.failures or report.report_evaluator_failures or any(
        case.evaluator_failures or not all(item.value for item in case.assertions.values()) for case in report.cases
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
