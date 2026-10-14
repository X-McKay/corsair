"""Scored E2E-0 chain over variants of the reviewed SPEC-0018 pair (SPEC-0035); no LLM judge.

Each case names which reviewed variant every purpose's fresh workspace holds, or an issue whose source
is absent. The composition call is injectable so durable mode can pass another coroutine with the
signature of ``run_direct``. Stages not named in ``--live`` use the fixture_e2e scripted plumbing;
the scripted assessment proposes the oracle's gate triple. Existing evidence directories are refused.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from corsair.policy.budget import BUDGET_POLICY_SHA256, budget_sha256
from pathlib import Path
import sys
from typing import Literal
from uuid import uuid4

import logfire
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic_ai import models
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_evals import Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator
from temporalio.client import Client

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import PytestRunnerConfig
from corsair.investigation.frameworks import harness
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.inference.config import InferenceConfig, inference_config, load_inference
from corsair.inference.models import agent_models
from corsair.agents.source.contracts import SourceFile
from corsair.composition.direct import CompositionBudget, DirectRun, FixtureCase, CapturedReviewSource, Stage, StageModels, run_direct
from corsair.core.disposition import Disposition
from evals.fixture_e2e.case import (BASELINE_TEST, _reads_then, fixture_case, scripted_assessment, scripted_control_authoring, scripted_exploit_authoring,
                                    scripted_identification, scripted_planning, split_reviewed_tests)
from evals.fixture_e2e.reviewed import FIXTURE, PREFIX, ReviewedLocalExecution, ReviewedWorkspace
from evals.fixture_e2e.run import STAGES, VERSION_FIELDS, VERSIONS, Journal, attempt_record, result_record
from corsair.workflows.chain import run_durable
from corsair.workflows.chain_runtime import ChainResult, FailureRecord
from evals.issue_analysis.evaluate import describe_model, record_count

ROOT = Path(__file__).parent
CASES = ROOT / "cases.yaml"
Purpose = Literal["development", "baseline", "candidate"]
Variant = Literal["vulnerable", "fixed"]


class ChainInput(BaseModel):
    """Evaluator-owned: which reviewed variant each purpose's workspace holds. Agents see none of it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    revisions: dict[Purpose, Variant]
    source: Literal["saved", "absent"] = "saved"


class ChainOracle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stopped_at: Stage | None
    gate: Disposition | None
    assessment_admitted: bool | None


class StageEfficiency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: Stage
    # None when the stage's usage was not returned (a durable child that timed out): unknown, not zero.
    requests: int | None
    tool_calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    output_corrections: int
    elapsed_seconds: float
    failure: str | None
    # The caps derived from this stage's own input (SPEC-0043) and the cap it ended on, if any.
    request_limit: int | None = None
    tool_calls_limit: int | None = None
    exhausted: str | None = None
    tool_cap_reached: bool = False


class ChainOutcome(BaseModel):
    """The serializable part of one DirectRun; full receipts stay under the evidence directory."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    stopped_at: Stage | None
    reason: str
    gate: Disposition | None
    proposal: Disposition | None
    admitted: bool | None
    stages: tuple[StageEfficiency, ...]


@dataclass
class ChainChecks(Evaluator[ChainInput, ChainOutcome, ChainOracle]):
    def evaluate(self, ctx):
        output, oracle = ctx.output, ctx.metadata
        return {"stopped_as_expected": output.stopped_at == oracle.stopped_at,
                "gate_matches": output.gate == oracle.gate,
                "assessment_admitted": output.admitted == oracle.assessment_admitted,
                "proposal_matches_gate": output.proposal == output.gate}


ChainDataset = Dataset[ChainInput, ChainOutcome, ChainOracle]


def dataset() -> ChainDataset:
    return ChainDataset.from_file(CASES, custom_evaluator_types=(ChainChecks,))


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def chain_case(inputs: ChainInput) -> FixtureCase:
    """The fixture_e2e case over this mapping: the issue sees the baseline variant's saved source, if any."""
    base = fixture_case()
    revisions = inputs.revisions
    sources = (SourceFile(path="test_existing.py", content=BASELINE_TEST),)
    if inputs.source == "saved":
        sources = (SourceFile(path="documents.py", content=(FIXTURE / revisions["baseline"] / "documents.py").read_text()),
                   *sources)
    return replace(base, issue=IssueAnalysisInput(fixture_id=base.issue.fixture_id, issue=base.issue.issue,
                                                  scope=base.issue.scope, source_files=sources),
                   revision_sources={r: _digest(FIXTURE / revisions[r] / "documents.py") for r in ("baseline", "candidate")},
                   review_sources={r: CapturedReviewSource(
                       source_sha256=_digest(FIXTURE / revisions[r] / "documents.py"),
                       files=(SourceFile(path="documents.py", content=(FIXTURE / revisions[r] / "documents.py").read_text()),
                              SourceFile(path="test_existing.py", content=BASELINE_TEST)))
                       for r in ("baseline", "candidate")})


def chain_runners(store, root: Path, revisions: dict[Purpose, Variant]):
    """A fresh private reviewed workspace per purpose holding this case's variant."""
    def runner(purpose):
        workspace = root / purpose
        return harness("pytest").runner(ReviewedWorkspace(store, workspace, revisions[purpose], split_reviewed_tests()), ReviewedLocalExecution(workspace),
                            store, PytestRunnerConfig(PREFIX, ".corsair-junit.xml", str(workspace),
                                                      witness_record_path=".corsair-witness.json"))
    return runner


def scripted_abstention():
    return _reads_then(["test_existing.py"], lambda info: {
        "status": "missing_information", "scope": "component", "target": None,
        "reason": "The read_document implementation is not in the saved source inventory"})


def scripted_stages(inputs: ChainInput, oracle: ChainOracle) -> dict[str, object]:
    """Plumbing only; the assessment proposes the oracle gate triple."""
    gate = oracle.gate or Disposition(execution="completed", finding="inconclusive", fix="not_verified")
    return {"identification": scripted_identification() if inputs.source == "saved" else scripted_abstention(),
            "planning": scripted_planning(), "control_authoring": scripted_control_authoring(), "exploit_authoring": scripted_exploit_authoring(),
            "assessment": scripted_assessment(gate.execution, gate.finding, gate.fix)}


def _failure(failure) -> str | None:
    if failure is None:
        return None
    kind = failure.kind if isinstance(failure, FailureRecord) else type(failure).__name__
    return f"{kind}: {failure.message if isinstance(failure, FailureRecord) else failure}"[:2048]


def outcome(run: DirectRun | ChainResult) -> ChainOutcome:
    assessment = run.assessment
    return ChainOutcome(
        stopped_at=run.stopped_at, reason=run.reason, gate=run.gate.permitted if run.gate else None,
        proposal=Disposition(execution=assessment.execution, finding=assessment.finding, fix=assessment.fix)
        if assessment else None, admitted=assessment.admission.admitted if assessment else None,
        stages=tuple(StageEfficiency(
            stage=a.stage, requests=a.usage and a.usage.requests, tool_calls=a.usage and a.usage.tool_calls,
            input_tokens=a.usage and a.usage.input_tokens, output_tokens=a.usage and a.usage.output_tokens,
            elapsed_seconds=a.elapsed_seconds,
            output_corrections=sum(isinstance(part, RetryPromptPart) for m in a.messages for part in m.parts),
            failure=_failure(a.failure), request_limit=a.limits and a.limits.request_limit,
            tool_calls_limit=a.limits and a.limits.tool_calls_limit, exhausted=a.exhausted and a.exhausted.limit,
            tool_cap_reached=a.tool_cap_reached)
            for a in run.attempts))


def input_key(inputs: ChainInput) -> str:
    return sha256(inputs.model_dump_json().encode()).hexdigest()


async def evaluate(evidence: Path, budget: CompositionBudget = CompositionBudget(), *, mode: str = "direct",
                   run=run_direct, live: tuple[str, ...] = (), model=None, config: InferenceConfig | None = None,
                   repeat: int = 1):
    """``run`` is the composition coroutine, ``run(case, models, runners, budget) -> DirectRun``; ``model`` serves
    the stages named in ``live``."""
    if set(live) - set(STAGES) or bool(live) != (model is not None):
        raise ValueError("live stages need a provider model and only known stage names")
    if isinstance(model, dict) and set(model) != set(live):
        raise ValueError("model mapping must exactly match live stages")
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    corpus = dataset()
    stages = {input_key(case.inputs): (case.inputs, case.metadata) for case in corpus.cases}
    metadata = {"mode": mode, "composition": f"{run.__module__}.{run.__qualname__}", "live_stages": list(live),
                "budget": budget.model_dump(), "budget_policy_sha256": BUDGET_POLICY_SHA256,
                "effective_budget_sha256": budget_sha256(budget), "provider": config.model_dump() if config else None,
                "model": ({stage: describe_model(model[stage]) for stage in live} if isinstance(model, dict)
                          else describe_model(model) if model is not None else "scripted"),
                "stage_providers": {stage: inference_config(config).resolve(stage).model_dump() for stage in live} if config else {},
                "versions": {stage: dict(zip(VERSION_FIELDS, VERSIONS[stage]))
                             for stage in STAGES},
                "runner": "reviewed_host_workspace", "witness_capture": "none", "repeat": repeat, "max_concurrency": 1,
                "task_retries": 0, "dataset_sha256": _digest(CASES), "source": {"python": sys.version}}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    corpus.evaluators.append(ChainChecks())

    async def task(inputs: ChainInput) -> ChainOutcome:
        directory = evidence / f"run-{uuid4()}"
        directory.mkdir()
        (directory / "work").mkdir(mode=0o700)
        (directory / "artifacts").mkdir(mode=0o700)
        (directory / "inputs.json").write_text(inputs.model_dump_json(indent=2))
        scripted = scripted_stages(*stages[input_key(inputs)])
        selected = StageModels(**{stage: (model[stage] if isinstance(model, dict) else model) if stage in live else scripted[stage] for stage in STAGES})
        set_eval_attribute("receipts", str(directory))
        with LocalArtifacts(directory / "artifacts", max_bytes=4 * 1024 * 1024) as store, \
                models.override_allow_model_requests(bool(live)):
            journal = Journal(chain_runners(store, directory / "work", inputs.revisions))
            try:
                result = await run(chain_case(inputs), selected, journal, budget)
            finally:
                with (directory / "native-runs.json").open("x") as destination:
                    json.dump(journal.entries, destination, indent=2)
        if isinstance(result, DirectRun):
            for index, attempt in enumerate(result.attempts):
                with (directory / f"attempt-{index}-{attempt.stage}.json").open("x") as destination:
                    json.dump(attempt_record(attempt), destination, indent=2)
            with (directory / "result.json").open("x") as destination:
                json.dump(result_record(result), destination, indent=2)
        else:
            # Durable results are typed records already: attempts, messages, executions and failures together.
            with (directory / "result.json").open("xb") as destination:
                destination.write(TypeAdapter(ChainResult).dump_json(result, indent=2))
        summary = outcome(result)
        for stage in summary.stages:
            for key in ("requests", "tool_calls", "input_tokens", "output_tokens", "output_corrections"):
                value = getattr(stage, key)
                if value is None:
                    set_eval_attribute(f"{stage.stage}_{key}", None)
                else:
                    record_count(f"{stage.stage}_{key}", value)
            set_eval_attribute(f"{stage.stage}_elapsed_seconds", round(stage.elapsed_seconds, 3))
        return summary

    report = await corpus.evaluate(task, repeat=repeat, max_concurrency=1, retry_task=None, metadata=metadata,
                                   progress=False)
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    return report


def passed(report) -> bool:
    return bool(report.cases) and not report.failures and all(
        not case.evaluator_failures and case.assertions and all(item.value for item in case.assertions.values())
        for case in report.cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Per-agent provider JSON (or legacy LocalModelConfig); required with --live")
    parser.add_argument("--live", default="", help=f"Comma-separated stages to run on the provider: {','.join(STAGES)}")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--temporal-address", help="Explicitly owned Temporal service; runs the durable chain")
    args = parser.parse_args()
    live = tuple(stage for stage in args.live.split(",") if stage)
    if set(live) - set(STAGES) or (live and args.provider_config is None):
        parser.error("--live names unknown stages or lacks --provider-config")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    config = load_inference(args.provider_config) if args.provider_config else None

    async def go():
        async with AsyncExitStack() as stack:
            model = await stack.enter_async_context(agent_models(config, live)) if live else None
            if args.temporal_address is None:
                return await evaluate(args.evidence, live=live, model=model, config=config, repeat=args.repeat)
            client = await Client.connect(args.temporal_address, plugins=[PydanticAIPlugin()])

            async def durable(case, stage_models, runners, budget):
                return await run_durable(case, stage_models, runners, budget, client=client)
            return await evaluate(args.evidence, mode="durable", run=durable, live=live, model=model, config=config,
                                  repeat=args.repeat)
    report = asyncio.run(go())
    report.print(include_input=True, include_output=False)
    if not passed(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
