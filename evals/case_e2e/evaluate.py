"""A cohort of benchmark cases through the issue entry; no LLM judge.

`make eval AGENT=chain SET=<cohort>` runs it through the eval wrapper, so runs are indexed, compared and promoted like
every other suite. Each case becomes its issue request plus expected outcome and runs once through
`corsair.investigate` in a fresh run directory, never retried; a request that cannot start is recorded at admission
before any model request. One case record is appended to `cases.jsonl` and its summary line printed as each case
finishes; `cohort.json` and `cohort.md` count the cases reaching each stage per language. Clones come from
`CORSAIR_CASE_SOURCES` (`<dir>/<case id>/repo`) and prepared local images from `CORSAIR_IMAGES`.
"""
import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import logfire
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator
import yaml

from corsair.inference.config import InferenceConfig, inference_config, load_inference
from corsair.composition.receipts import AGENT_STAGES, VERSION_FIELDS, VERSIONS
from corsair.investigate import images
from corsair.investigation.results import STAGES, cohort_summary, markdown
from evals.issue_analysis.evaluate import record_count

from .case import entry
from .run import run_case

ROOT = Path(__file__).parent
COHORTS = ROOT / "cohorts.yaml"
CASES = ROOT.parents[1] / "benchmarks/cases"


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case: str


class CaseOutcome(BaseModel):
    """The serializable part of one case's result line; receipts stay under its run directory."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    reached: str
    stopped_at: str | None
    reason: str
    matches_expected: bool | None


class CaseChecks(Evaluator[CaseInput, CaseOutcome, None]):
    def evaluate(self, ctx):
        checks = {"started": ctx.output.reached != "admission", "stage_reached": STAGES.index(ctx.output.reached)}
        if ctx.output.matches_expected is not None:
            checks["matches_expected"] = ctx.output.matches_expected
        return checks


def cohort(name: str) -> tuple[str, ...]:
    cohorts = yaml.safe_load(COHORTS.read_text())
    if name not in cohorts:
        raise ValueError(f"unknown cohort {name!r}; cohorts: {', '.join(cohorts)}")
    return tuple(cohorts[name])


def _digest(name: str, cases: tuple[str, ...]) -> str:
    """Cohort membership plus every member's manifest bytes: a changed manifest is a changed case set."""
    digest = sha256(json.dumps([name, cases]).encode())
    for case in cases:
        found = entry(case)
        digest.update((found.directory / "case.yaml").read_bytes())
    return digest.hexdigest()


async def evaluate(evidence: Path, name: str, sources: Path, prepared_images: dict[str, str], *,
                   config: InferenceConfig | None = None, models: dict | None = None, timeout: int = 600):
    """`config` serves every agent stage; `models` replaces it with a model factory per stage (offline checks)."""
    if (config is None) == (models is None):
        raise ValueError("a cohort runs every stage on the provider, or on supplied models for offline checks")
    cases = cohort(name)
    evidence.mkdir(parents=True, exist_ok=False)
    logfire.configure(send_to_logfire=False, console=False)
    live = list(AGENT_STAGES) if config else []
    metadata = {"mode": "direct", "dataset": name, "dataset_sha256": _digest(name, cases), "live_stages": live,
                "provider": config.model_dump() if config else None,
                "stage_providers": {stage: inference_config(config).resolve(stage).model_dump() for stage in live},
                "versions": {stage: dict(zip(VERSION_FIELDS, VERSIONS[stage])) for stage in AGENT_STAGES},
                "runner": "docker_image_only", "images": prepared_images, "timeout_seconds": timeout, "repeat": 1,
                "max_concurrency": 1, "task_retries": 0, "source": {"python": sys.version}}
    (evidence / "configuration.json").write_text(json.dumps(metadata, indent=2))
    dataset = Dataset[CaseInput, CaseOutcome, None](name=name, cases=[Case(name=case, inputs=CaseInput(case=case)) for case in cases],
                                                     evaluators=[CaseChecks()])
    items = []

    async def task(inputs: CaseInput) -> CaseOutcome:
        directory = evidence / f"run-{uuid4()}"
        set_eval_attribute("receipts", str(directory))
        item = await asyncio.to_thread(run_case, inputs.case, directory, sources, prepared_images, config=config,
                                       models=models, timeout=timeout)
        for key, usage in item["usage"].items():
            for metric in ("requests", "input_tokens", "output_tokens"):
                if usage[metric] is None:
                    set_eval_attribute(f"{key}_{metric}", None)
                else:
                    record_count(f"{key.split('-', 1)[1]}_{metric}", usage[metric])
        items.append(item)
        with (evidence / "cases.jsonl").open("a") as destination:
            destination.write(json.dumps(item, default=str) + "\n")
        print(item["summary"], flush=True)
        return CaseOutcome(reached=item["reached"], stopped_at=item["stopped_at"], reason=(item["reason"] or "")[:2048],
                           matches_expected=item["matches_expected"])

    report = await dataset.evaluate(task, max_concurrency=1, retry_task=None, metadata=metadata, progress=False)
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    summary = cohort_summary(items)
    (evidence / "cohort.json").write_text(json.dumps(summary, indent=2))
    (evidence / "cohort.md").write_text(markdown(summary))
    return report, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--provider-config", type=Path)
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per runner or setup command")
    parser.add_argument("--repeat", type=int, default=1, help="Only 1: each case runs once per eval run")
    args = parser.parse_args()
    if args.repeat != 1:
        parser.error("each case runs once per eval run; start another run instead of repeating")
    if args.provider_config is None:
        parser.error("a case cohort has no scripted stages: pass PROVIDER_CONFIG")
    missing = [name for name in ("CORSAIR_CASE_SOURCES", "CORSAIR_IMAGES") if not os.environ.get(name)]
    if missing:
        parser.error(f"set {', '.join(missing)}")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    try:
        prepared_images = images(Path(os.environ["CORSAIR_IMAGES"]))
        cohort(args.cohort)
    except ValueError as exc:
        parser.error(str(exc))
    _, summary = asyncio.run(evaluate(args.evidence, args.cohort, Path(os.environ["CORSAIR_CASE_SOURCES"]).resolve(),
                                      prepared_images, config=load_inference(args.provider_config),
                                      timeout=args.timeout))
    print(markdown(summary))


if __name__ == "__main__":
    main()
