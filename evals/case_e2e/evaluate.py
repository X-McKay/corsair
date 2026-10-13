"""A cohort of benchmark cases through the chain (image-only Docker ports, every agent stage live); no LLM judge.

`make eval AGENT=chain SET=<cohort>` runs it through the eval wrapper, so runs are indexed, compared and promoted like
every other suite. Each case runs once with a fresh run directory, never retried; a case that cannot start is
recorded with its reason before any model request. One result line per case is appended to `results.jsonl` and
printed as the case finishes; `cohort.json` and `cohort.md` count the cases reaching each stage per language.
Clones come from `CORSAIR_CASE_SOURCES` (`<dir>/<case id>/repo`, the layout evals/benchmark/sources.py uses) and
prepared local images from the JSON file `CORSAIR_CASE_IMAGES` (`{"<row id>": "sha256:<config id>"}`).
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
from evals.benchmark.sources import case_dir
from evals.fixture_e2e.run import AGENT_STAGES, VERSION_FIELDS, VERSIONS
from evals.issue_analysis.evaluate import record_count

from .case import CaseRefused, entry
from .results import STAGES, cohort_summary, markdown, result_line
from .run import images, prepare_case, run_case

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
        checks = {"started": ctx.output.reached != "case", "stage_reached": STAGES.index(ctx.output.reached)}
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
    lines = []

    async def task(inputs: CaseInput) -> CaseOutcome:
        directory = evidence / f"run-{uuid4()}"
        directory.mkdir(mode=0o700)
        set_eval_attribute("receipts", str(directory))
        found = entry(inputs.case)
        expected = found.manifest.evaluator.expected
        context = dict(case_id=found.inventory.case_id, language=found.inventory.language,
                       expected=expected.chain if expected else None, evidence=directory)
        try:
            prepared = prepare_case(inputs.case, case_dir(sources, found.inventory.case_id) / "repo", directory,
                                    prepared_images, timeout)
        except CaseRefused as refused:
            line = result_line(**context, refused=str(refused))
        else:
            run = await run_case(prepared, directory, config, timeout, models=models)
            line = result_line(**context, prepared=prepared, run=run)
            for key, usage in line["usage"].items():
                for metric in ("requests", "input_tokens", "output_tokens"):
                    if usage[metric] is None:
                        set_eval_attribute(f"{key}_{metric}", None)
                    else:
                        record_count(f"{key.split('-', 1)[1]}_{metric}", usage[metric])
        lines.append(line)
        with (evidence / "results.jsonl").open("a") as destination:
            destination.write(json.dumps(line, default=str) + "\n")
        print(json.dumps({k: line[k] for k in ("case", "reached", "reason", "matches_expected", "evidence")}), flush=True)
        return CaseOutcome(reached=line["reached"], stopped_at=line["stopped_at"], reason=line["reason"][:2048],
                           matches_expected=line["matches_expected"])

    report = await dataset.evaluate(task, max_concurrency=1, retry_task=None, metadata=metadata, progress=False)
    with (evidence / "report.json").open("xb") as destination:
        destination.write(TypeAdapter(type(report)).dump_json(report, indent=2))
    summary = cohort_summary(lines)
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
    missing = [name for name in ("CORSAIR_CASE_SOURCES", "CORSAIR_CASE_IMAGES") if not os.environ.get(name)]
    if missing:
        parser.error(f"set {', '.join(missing)}")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    try:
        prepared_images = images(Path(os.environ["CORSAIR_CASE_IMAGES"]))
        cohort(args.cohort)
    except ValueError as exc:
        parser.error(str(exc))
    _, summary = asyncio.run(evaluate(args.evidence, args.cohort, Path(os.environ["CORSAIR_CASE_SOURCES"]).resolve(),
                                      prepared_images, config=load_inference(args.provider_config),
                                      timeout=args.timeout))
    print(markdown(summary))


if __name__ == "__main__":
    main()
