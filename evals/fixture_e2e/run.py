"""Run one E2E-0 direct composition over the SPEC-0018 pair and keep every stage receipt.

Stages not named in --live use scripted plumbing models. This CLI executes on the reviewed host
workspace, which admits only the reviewed SPEC-0018 test bytes: a live author's own test code is
refused before it reaches an interpreter. The live gate `make qualify-fixture-e2e` runs the same
`record_run` over the OpenShell test workspace instead. Existing evidence directories are refused.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
import base64
from dataclasses import asdict, fields, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys

import logfire
from pydantic import BaseModel, TypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.evidence_assessment import agent as assessment
from corsair.agents.issue_analysis import identification
from corsair.agents.provider import LocalModelConfig, local_model
from corsair.agents.test_authoring import agent as authoring
from corsair.agents.test_authoring.skills import SKILL_SHA256 as AUTHORING_SKILL
from corsair.agents.test_planning import agent as planning
from corsair.agents.test_planning.skills import SKILL_SHA256 as PLANNING_SKILL
from corsair.composition.direct import CompositionBudget, DirectRun, FixtureCase, StageModels, run_direct
from evals.issue_analysis.evaluate import describe_model

from .case import (fixture_case, reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
                   scripted_planning)

STAGES = ("identification", "planning", "authoring", "assessment")
SCRIPTED = {"identification": scripted_identification, "planning": scripted_planning,
            "authoring": scripted_authoring, "assessment": scripted_assessment}
VERSIONS = {
    "identification": (identification.PROMPT_VERSION, identification.CONFIG_VERSION, identification.SKILL_SHA256),
    "planning": (planning.PROMPT_VERSION, planning.CONFIG_VERSION, PLANNING_SKILL),
    "authoring": (authoring.PROMPT_VERSION, authoring.CONFIG_VERSION, AUTHORING_SKILL),
    "assessment": (assessment.PROMPT_VERSION, assessment.CONFIG_VERSION, assessment.SKILL_SHA256),
}


def encode(value):
    """Lossless JSON for native runner observations: dataclasses by field, bytes with digest and base64."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, bytes):
        return {"sha256": sha256(value).hexdigest(), "size": len(value), "base64": base64.b64encode(value).decode()}
    if isinstance(value, (tuple, list)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "detail": str(value)[:4096], "receipt": encode(getattr(value, "receipt", None))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class Journal:
    """Wraps the operator's runners and keeps every complete native observation, failed ones included,
    with its purpose and operation, independently of what any agent later reads."""
    def __init__(self, runners):
        self.runners, self.entries = runners, []

    def __call__(self, purpose):
        inner = self.runners(purpose)
        journal = self

        class Recorded:
            def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation):
                entry = {"purpose": purpose, "operation": str(operation), "patch_sha256": patch.sha256,
                         "observed": None, "failure": None}
                journal.entries.append(entry)
                try:
                    observed = inner.run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                                         discovery_command=discovery_command, operation=operation)
                except BaseException as exc:
                    entry["failure"] = encode(exc)
                    raise
                entry["observed"] = encode(observed)
                return observed
        return Recorded()


def _dump(value):
    return None if value is None else json.loads(value.model_dump_json())


def result_record(run: DirectRun) -> dict:
    executions = [{"revision": e.revision, "operation": str(e.operation),
                   "failure": None if e.failure is None else f"{type(e.failure).__name__}: {e.failure}",
                   "failure_layer": e.observed.failure_layer if e.observed else None,
                   "cleanup": e.observed.cleanup if e.observed else None,
                   "discovered": list(e.observed.discovery.test_ids) if e.observed and e.observed.discovery else [],
                   "cases": [{"test_id": c.test_id, "outcome": c.outcome,
                              "failure": asdict(c.failure) if c.failure else None}
                             for c in (e.observed.execution.cases if e.observed and e.observed.execution else ())],
                   "native_exit": (e.observed.execution.receipt.native_exit
                                   if e.observed and e.observed.execution and e.observed.execution.receipt else None)}
                  for e in run.executions]
    return {"stopped_at": run.stopped_at, "reason": run.reason, "identification": _dump(run.identification),
            "plan": _dump(run.plan), "patch": _dump(run.patch), "observation_plan": _dump(run.observation_plan),
            "executions": executions, "gate": _dump(run.gate), "assessment": _dump(run.assessment),
            "limitations": list(run.limitations)}


def attempt_record(attempt) -> dict:
    return {"stage": attempt.stage, "elapsed_seconds": attempt.elapsed_seconds,
            "failure": None if attempt.failure is None else {"type": type(attempt.failure).__name__,
                                                             "detail": str(attempt.failure)[:4096]},
            "output": _dump(attempt.output) if hasattr(attempt.output, "model_dump_json") else None,
            "usage": TypeAdapter(RunUsage).dump_python(attempt.usage, mode="json"),
            "messages": TypeAdapter(list[ModelMessage]).dump_python(list(attempt.messages), mode="json")}


async def record_run(evidence: Path, live: tuple[str, ...], config: LocalModelConfig | None, case: FixtureCase,
                     runners, runner: dict) -> DirectRun:
    """Run one composition into an existing private evidence directory and keep every receipt.

    ``runner`` describes the operator's execution route for configuration.json.
    """
    logfire.configure(send_to_logfire=False, console=False)
    async with AsyncExitStack() as stack:
        model = await stack.enter_async_context(local_model(config)) if live else None
        scripted = SCRIPTED | {"planning": lambda: scripted_planning(case.environment.discovery_command)}
        selected = {stage: model if stage in live else scripted[stage]() for stage in STAGES}
        budget = CompositionBudget()
        (evidence / "configuration.json").write_text(json.dumps({
            "mode": "direct", "live_stages": list(live), "budget": budget.model_dump(),
            "provider": config.model_dump() if config else None,
            "models": {stage: describe_model(selected[stage]) for stage in STAGES},
            "versions": {stage: dict(zip(("prompt_version", "config_version", "skill_sha256"), VERSIONS[stage]))
                         for stage in STAGES},
            "runner": runner, "witness_capture": "none",
            "environment": _dump(case.environment), "environment_identity": _dump(case.environment_identity),
            "revision_sources": case.revision_sources, "source": {"python": sys.version}}, indent=2))
        journal = Journal(runners)
        try:
            run = await run_direct(case, StageModels(**selected), journal, budget)
        finally:
            with (evidence / "native-runs.json").open("x") as destination:
                json.dump(journal.entries, destination, indent=2)
    for index, attempt in enumerate(run.attempts):
        with (evidence / f"attempt-{index}-{attempt.stage}.json").open("x") as destination:
            json.dump(attempt_record(attempt), destination, indent=2)
    with (evidence / "result.json").open("x") as destination:
        json.dump(result_record(run), destination, indent=2)
    return run


async def main_async(evidence: Path, live: tuple[str, ...], config: LocalModelConfig | None) -> DirectRun:
    """Reviewed host workspace: only the reviewed SPEC-0018 test bytes execute."""
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / "work").mkdir(mode=0o700)
    (evidence / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(evidence / "artifacts", max_bytes=4 * 1024 * 1024) as store:
        return await record_run(evidence, live, config, fixture_case(), reviewed_runners(store, evidence / "work"),
                                {"route": "reviewed_host_workspace"})


def summary(run: DirectRun) -> dict:
    gate = run.gate.permitted.model_dump() if run.gate else None
    proposal = run.assessment.admission.model_dump(mode="json") if run.assessment else None
    return {"stopped_at": run.stopped_at, "reason": run.reason, "gate": gate, "admission": proposal,
            "usage": {f"{index}-{a.stage}": {"requests": a.usage.requests, "tool_calls": a.usage.tool_calls,
                                             "input_tokens": a.usage.input_tokens,
                                             "output_tokens": a.usage.output_tokens,
                                             "elapsed_seconds": round(a.elapsed_seconds, 1),
                                             "failure": None if a.failure is None else type(a.failure).__name__}
                      for index, a in enumerate(run.attempts)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Explicit LocalModelConfig JSON; required with --live")
    parser.add_argument("--live", default="", help=f"Comma-separated stages to run on the provider: {','.join(STAGES)}")
    args = parser.parse_args()
    live = tuple(stage for stage in args.live.split(",") if stage)
    if set(live) - set(STAGES) or (live and args.provider_config is None):
        parser.error("--live names unknown stages or lacks --provider-config")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    config = LocalModelConfig.model_validate_json(args.provider_config.read_bytes()) if args.provider_config else None
    run = asyncio.run(main_async(args.evidence, live, config))
    print(json.dumps(summary(run) | {
        "config_sha256": sha256((args.evidence / "configuration.json").read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
