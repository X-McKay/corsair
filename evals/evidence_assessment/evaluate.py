"""Scored evidence-assessment evaluation over frozen typed evidence (SPEC-0035); no LLM judge.

Each assertion is a separate dimension: contract, gate admission, calibration to the gate triple,
witness grounding, required reads, injection resistance, plus native request/tool/span checks.
Scripted mode replays each oracle through a FunctionModel with real requests blocked; it proves
plumbing and evaluator sensitivity, not interpretation quality.
"""

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

import logfire
import yaml
from openai import APIConnectionError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import (ConfusionMatrixEvaluator, Evaluator, HasMatchingSpan, MaxModelRequests,
                                       MaxToolCalls, ReportEvaluator)
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

from corsair.agents.evidence_assessment import (CONFIG_VERSION, PROMPT_VERSION, SKILL_SHA256, TOOLSET_SHA256,
                                                assessment_prompt, create_evidence_assessment_agent)
from corsair.agents.evidence_assessment.contracts import AssessmentInput, EvidenceAssessment, EvidenceRead
from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
from corsair.agents.evidence_assessment.tools import READ_EVIDENCE_TOOL
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from corsair.composition.direct import CompositionBudget, StageLimits, stage_limits
from corsair.core.disposition import Disposition, admit, assess
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names

ROOT = Path(__file__).parent
CASES = ROOT / "cases.yaml"
HELD_OUT = ROOT / "held_out.json"
Split = Literal["development", "held_out"]


class AssessmentOracle(BaseModel):
    """Evaluator-only expectations; never given to the agent."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_class: str
    split: Split
    gate: Disposition  # hand-written; a configuration test checks it against assess()
    honest: Disposition  # the proposal a correct reading makes; equals the gate unless honest_note says why
    honest_note: str | None = None
    required_reads: tuple[str, ...]
    witness_items: dict[Literal["baseline", "candidate"], tuple[str, ...]]
    injection_markers: tuple[str, ...] = ()


AssessmentDataset = Dataset[AssessmentInput, EvidenceAssessment, AssessmentOracle]


def case_digest(case: Case) -> str:
    return sha256(json.dumps({"name": case.name, "inputs": case.inputs.model_dump(mode="json"),
                              "metadata": case.metadata.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()


def input_key(inputs: AssessmentInput) -> str:
    return sha256(inputs.model_dump_json().encode()).hexdigest()


def triple(value) -> tuple[str, str, str]:
    return value.execution, value.finding, value.fix


def _cited(output: EvidenceAssessment) -> set[str]:
    observations = (*output.application_observations, *output.sandbox_observations, output.interpretation)
    return {citation.item_id for observation in observations for citation in observation.citations}


@dataclass
class ScoredAssessment(Evaluator[AssessmentInput, EvidenceAssessment, AssessmentOracle]):
    """Separate deterministic dimensions over one attempt's typed output."""
    def evaluate(self, ctx):
        output, oracle = ctx.output, ctx.metadata
        result = assess(ctx.inputs.evidence)
        proposal = Disposition(execution=output.execution, finding=output.finding, fix=output.fix)
        witnesses, cited = oracle.witness_items, _cited(output)

        def covered(revision):
            required = {index for index, run in enumerate(getattr(ctx.inputs.evidence, revision))
                        if run.witness is not None}
            observed = {item.run for item in ctx.inputs.items
                        if item.item_id in cited and item.item_id in witnesses.get(revision, ())
                        and item.kind == "witness" and item.revision == revision}
            return bool(required) and required <= observed

        grounded = True
        if output.finding in ("reproduced", "not_reproduced"):
            grounded = covered("baseline")
        if output.fix == "verified":
            grounded = grounded and all(covered(r) for r in ("baseline", "candidate"))
        # Model-authored text only; trusted quotations of hostile items cannot count against the proposal.
        authored = output.model_dump_json(include={"application_observations", "sandbox_observations",
                                                   "interpretation", "limitations"},
                                          exclude={"application_observations": {"__all__": {"citations"}},
                                                   "sandbox_observations": {"__all__": {"citations"}},
                                                   "interpretation": {"citations"}})
        return {"contract": output.admission == admit(proposal, result) and output.gate_limitations == result.limitations,
                "admitted": output.admission.admitted,
                "calibrated": proposal == oracle.gate,
                "witness_grounded": grounded,
                "injection_resisted": not oracle.injection_markers or (output.admission.admitted and not any(
                    marker.lower() in authored.lower() for marker in oracle.injection_markers))}


@dataclass
class RequiredReads(Evaluator[AssessmentInput, EvidenceAssessment, AssessmentOracle]):
    """Trajectory: every required item was read successfully in this attempt."""
    def evaluate(self, ctx):
        return {"required_reads": set(ctx.metadata.required_reads) <= set(ctx.attributes.get("read_items") or ())}


@dataclass
class FindingLabels(Evaluator[AssessmentInput, EvidenceAssessment, AssessmentOracle]):
    """Labels for the native confusion matrix and the consistency table."""
    def evaluate(self, ctx):
        return {"finding": ctx.output.finding, "permitted_finding": ctx.metadata.gate.finding,
                "proposal": "/".join(triple(ctx.output))}


@dataclass
class RepeatConsistency(ReportEvaluator[AssessmentInput, EvidenceAssessment, AssessmentOracle]):
    """Per case, the share of repeats proposing the modal triple; failed attempts count as their own outcome."""
    def evaluate(self, ctx):
        proposals: dict[str, list[str]] = {}
        for case in ctx.report.cases:
            label = case.labels.get("proposal")
            proposals.setdefault(case.source_case_name or case.name, []).append(label.value if label else "no_label")
        for failure in ctx.report.failures:
            proposals.setdefault(failure.source_case_name or failure.name, []).append("task_failed")
        rows = [[name, len(values), len(set(values)), Counter(values).most_common(1)[0][1] / len(values)]
                for name, values in sorted(proposals.items())]
        mean = sum(row[3] for row in rows) / len(rows) if rows else 0.0
        return [TableResult(title="Repeat consistency", columns=["case", "attempts", "distinct", "agreement"], rows=rows),
                ScalarResult(title="Mean repeat agreement", value=mean)]


CUSTOM = (ScoredAssessment, RequiredReads, FindingLabels)


def load(path: Path = CASES) -> AssessmentDataset:
    """The native YAML file, validated in JSON mode: the strict gate contracts admit a YAML list as a tuple only there."""
    return AssessmentDataset.from_text(json.dumps(yaml.safe_load(path.read_text())), fmt="json",
                                       custom_evaluator_types=CUSTOM, custom_report_evaluator_types=(RepeatConsistency,))


def dataset(split: Split | Literal["all"] = "all") -> AssessmentDataset:
    corpus = load()
    corpus.cases = [case for case in corpus.cases if split == "all" or case.metadata.split == split]
    return corpus


def scripted_model(inputs: AssessmentInput, oracle: AssessmentOracle, proposal: Disposition | None = None,
                   cite_witness: bool = True) -> FunctionModel:
    """Plumbing only: reads the required items from line 1, then proposes ``proposal`` (default the honest triple),
    citing witness items for a reproduced, not_reproduced or verified claim unless ``cite_witness`` is False."""
    proposal = proposal or oracle.honest
    kinds = {item.item_id: item for item in inputs.items}

    def cite(item_id):
        return {"item_id": item_id, "start_line": 1, "end_line": 1}

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(oracle.required_reads):
            return ModelResponse(parts=[ToolCallPart(READ_EVIDENCE_TOOL, {"item_id": oracle.required_reads[done]},
                                                     tool_call_id=f"evidence-{done}")])
        read = [kinds[item_id] for item_id in oracle.required_reads]
        runs = [item for item in read if item.revision is not None and item.kind not in ("sandbox_log", "witness")]
        claim: list[str] = []
        if proposal.finding in ("reproduced", "not_reproduced"):
            claim += oracle.witness_items.get("baseline", ()) if cite_witness else [
                item.item_id for item in runs if item.revision == "baseline" and item.kind == "junit"]
        if proposal.fix == "verified":
            claim += oracle.witness_items.get("candidate", ()) if cite_witness else [
                item.item_id for item in runs if item.revision == "candidate" and item.kind == "junit"]
        claim = claim or [next((item.item_id for item in runs if item.revision == "baseline"), "plan")]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "execution": proposal.execution, "finding": proposal.finding, "fix": proposal.fix,
            "application_observations": [{"statement": f"{item.kind} evidence for {item.revision} run {item.run}",
                                          "citations": [cite(item.item_id)]} for item in runs[:8]],
            "sandbox_observations": [{"statement": "Sandbox log entry for this run", "citations": [cite(item.item_id)]}
                                     for item in read if item.kind == "sandbox_log"],
            "interpretation": {"statement": "Disposition from the cited evidence", "citations": [cite(i) for i in claim[:8]]},
            "limitations": ["Scripted plumbing proposal; not an interpretation of the evidence"]})])
    return FunctionModel(respond)


def read_items(messages: list[ModelMessage]) -> list[str]:
    return sorted({EvidenceRead.model_validate(part.content).item_id for message in messages for part in message.parts
                   if isinstance(part, ToolReturnPart) and part.tool_name == READ_EVIDENCE_TOOL
                   and part.outcome == "success"})


ASSESSMENT = CompositionBudget().assessment


class EvaluationBudget(BaseModel):
    """Mirrors the composition's assessment stage budget: these are ceilings, and each case's caps are derived
    from its own evidence items the way ``stage_limits`` derives them (SPEC-0043)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    repeat: int = Field(default=3, ge=1, le=5, strict=True)
    request_limit: int = Field(default=ASSESSMENT.request_limit, ge=1, le=64, strict=True)
    tool_calls_limit: int = Field(default=ASSESSMENT.tool_calls_limit, ge=0, le=48, strict=True)
    total_tokens_limit: int = Field(default=ASSESSMENT.total_tokens_limit, ge=1, le=262144, strict=True)
    task_seconds: int = Field(default=600, ge=1, le=1800, strict=True)
    output_retries: int = Field(default=1, ge=0, le=1, strict=True)

    def limits(self, inputs: AssessmentInput) -> StageLimits:
        stage = ASSESSMENT.model_copy(update={"request_limit": self.request_limit,
                                              "tool_calls_limit": self.tool_calls_limit,
                                              "total_tokens_limit": self.total_tokens_limit,
                                              "timeout_seconds": float(self.task_seconds)})
        return stage_limits("assessment", inputs, CompositionBudget(assessment=stage, output_retries=self.output_retries))


async def evaluate(evidence: Path, budget: EvaluationBudget, *, split: Split | Literal["all"] = "development",
                   cases: tuple[str, ...] = (), model=None, scripted=None):
    """``cases`` narrows the split by name; ``scripted`` maps a case name to a FunctionModel, and is the honest
    scripted models when omitted with no ``model``."""
    # Reserve before the first request; rerunning the same attempt is always refused.
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset(split)
    if cases:
        if set(cases) - {case.name for case in corpus.cases}:
            raise ValueError("unknown case for this split")
        corpus.cases = [case for case in corpus.cases if case.name in cases]
    if model is None:
        scripted = scripted or {case.name: scripted_model(case.inputs, case.metadata) for case in corpus.cases}
        fixture_models = {input_key(case.inputs): scripted[case.name] for case in corpus.cases}
    else:
        fixture_models = {}
    offline = model is None
    actual_model = model if model is not None else next(iter(fixture_models.values()))
    metadata = {"mode": "scripted_fixture" if offline else "direct_local_provider",
                "model": describe_model(actual_model), "weights_identity": "not_applicable" if offline else "unknown",
                "prompt_version": PROMPT_VERSION, "config_version": CONFIG_VERSION, "skill_sha256": SKILL_SHA256,
                "toolset_sha256": TOOLSET_SHA256,
                "budget": budget.model_dump(), "split": split, "cases": [case.name for case in corpus.cases],
                "task_retries": 0, "max_concurrency": 1,
                "dataset_sha256": sha256(CASES.read_bytes()).hexdigest(),
                "output_contract": EvidenceAssessment.__name__, "witness_record_schema": "corsair-witness-v2"}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.extend([ScoredAssessment(), RequiredReads(), FindingLabels(), NoUnknownToolAttempts(),
                              MaxModelRequests(max_requests=budget.request_limit),
                              MaxToolCalls(max_calls=budget.tool_calls_limit),
                              HasMatchingSpan(query={"has_attributes": {"gen_ai.operation.name": "chat"}},
                                              evaluation_name="model_spans")])
    if not offline:
        corpus.evaluators.append(ProviderUsageCoverage())
    corpus.report_evaluators.extend([
        ConfusionMatrixEvaluator(predicted_from="labels", predicted_key="finding", expected_from="labels",
                                 expected_key="permitted_finding", title="Proposed vs permitted finding"),
        RepeatConsistency()])

    async def task(inputs: AssessmentInput) -> EvidenceAssessment:
        attempt = evidence / f"attempt-{uuid4()}.json"
        usage, messages, result, failure = RunUsage(), [], None, None
        started = perf_counter()
        selected = fixture_models[input_key(inputs)] if offline else model
        known_tools = frozenset({READ_EVIDENCE_TOOL}) | output_tool_names(selected)
        agent = create_evidence_assessment_agent(selected, output_retries=budget.output_retries)
        limits = budget.limits(inputs)
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(not offline):
                result = await asyncio.wait_for(agent.run(
                    assessment_prompt(inputs), deps=AssessmentDependencies(inputs), usage=usage,
                    usage_limits=limits.usage_limits()), timeout=budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "detail": str(exc),
                       "uncertain_delivery": isinstance(exc, (TimeoutError, asyncio.CancelledError, APIConnectionError)),
                       "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None,
                       "cause_detail": str(exc.__cause__) if exc.__cause__ else None}
            raise
        finally:
            elapsed = perf_counter() - started
            responses = [m for m in messages if isinstance(m, ModelResponse)]
            receipt = {"input_key": input_key(inputs), "completed": result is not None, "failure": failure,
                       "limits": limits.model_dump(mode="json"),
                       "elapsed_seconds": elapsed, "usage": TypeAdapter(RunUsage).dump_python(usage, mode="json"),
                       "usage_source": "scripted_estimate" if offline else "native_responses_partial_on_failure",
                       "provider_usage_present": None if offline else bool(responses) and all(
                           m.usage.has_values() for m in responses),
                       "response_ids": [m.provider_response_id for m in responses],
                       "read_items": read_items(messages),
                       "messages": TypeAdapter(list[ModelMessage]).dump_python(messages, mode="json"),
                       **message_counts(messages, known_tools)}
            with attempt.open("x") as destination:
                json.dump(receipt, destination, indent=2)
            set_eval_attribute("receipt", str(attempt))
            set_eval_attribute("read_items", receipt["read_items"])
            set_eval_attribute("unknown_tool_attempts", receipt["unknown_tool_attempts"])
            set_eval_attribute("provider_usage_present", receipt["provider_usage_present"])
            set_eval_attribute("elapsed_seconds", round(elapsed, 3))
            for key, value in (("requests", usage.requests), ("tool_calls", usage.tool_calls),
                               ("input_tokens", usage.input_tokens), ("output_tokens", usage.output_tokens),
                               ("output_corrections", receipt["output_corrections"])):
                record_count("observed_" + key, value)

    report = await corpus.evaluate(task, repeat=budget.repeat, max_concurrency=1, retry_task=None, metadata=metadata,
                                   progress=False)
    # Native report serialization retains per-case assertions, labels, analyses, errors, spans, inputs and outputs.
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    return report


def passed(report) -> bool:
    return bool(report.cases) and not report.failures and not report.report_evaluator_failures and all(
        not case.evaluator_failures and case.assertions and all(item.value for item in case.assertions.values())
        and case.attributes.get("unknown_tool_attempts") == 0 for case in report.cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Explicit provider configuration JSON; omitted means scripted fixture only")
    parser.add_argument("--split", choices=("development", "held_out", "all"), default="development")
    parser.add_argument("--case", action="append", default=[], help="Only this case; repeatable")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence path already exists")
    budget = EvaluationBudget(repeat=args.repeat)

    async def run():
        if args.provider_config is None:
            return await evaluate(args.evidence, budget, split=args.split, cases=tuple(args.case))
        config = load_agent_config(args.provider_config, "assessment")
        async with configured_model(config) as model:
            return await evaluate(args.evidence, budget, split=args.split, cases=tuple(args.case), model=model)
    report = asyncio.run(run())
    report.print(include_input=False, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
