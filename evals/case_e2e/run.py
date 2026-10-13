"""Run one benchmark case through the chain: case id in, every stage receipt out (image-only, Docker).

The case's manifest and a local clone holding its baseline and candidate commits become the chain input
(`case.py`); runtime selection picks the matrix row from the baseline's build files and its framework row picks the
runner (`frameworks.py`). Each revision's own dependencies are installed once with registry access, then the
environment stage prepares the selected image with the environment agent and every test run is offline in a fresh
container (`docker.py`). Every agent stage is live on the provider: a real case has no scripted plumbing.
Existing evidence directories are refused.
"""
import argparse
import asyncio
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import re

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.composition.direct import DirectRun
from corsair.inference.config import InferenceConfig, load_inference
from evals.fixture_e2e.run import AGENT_STAGES, record_run, stage_configs, summary

from .case import CaseRefused, CaseRun, build_case, entry
from .docker import DockerPreparation, DockerRunners, install

IMAGE = re.compile(r"(?P<row>[a-z0-9][a-z0-9.-]*)=(?P<config>sha256:[0-9a-f]{64})")


def prepare_case(case: str, repository: Path, evidence: Path, images: dict[str, str], timeout: int) -> CaseRun:
    try:
        return build_case(entry(case), repository, evidence / "trees", images, timeout)
    except CaseRefused as refused:
        (evidence / "refused.json").write_text(json.dumps({"case": case, "reason": str(refused)}, indent=2))
        raise


async def run_case(prepared: CaseRun, evidence: Path, config: InferenceConfig, timeout: int,
                   profiles: dict | None = None, *, models: dict | None = None) -> DirectRun:
    """Install each revision's dependencies, then one chain run over Docker ports into `evidence`.

    `models` replaces the provider with a model factory per stage (offline checks); a real run leaves it None."""
    revisions = {}
    for revision, commit in prepared.commits.items():
        dependencies = evidence / "dependencies" / revision
        install(prepared.harness, prepared.image, prepared.trees[revision], commit, dependencies,
                evidence / "setup" / revision)
        revisions[revision] = (prepared.trees[revision], dependencies.resolve(), commit)
    (evidence / "e2e").mkdir(mode=0o700)
    (evidence / "artifacts").mkdir(mode=0o700)
    route = {"route": "docker_image_only", "row": prepared.row, "image": prepared.image, "framework": prepared.framework.name,
             "runner": prepared.framework.runner, "framework_evidence": prepared.framework.qualification.evidence,
             "commits": prepared.commits, "timeout_seconds": timeout, "network": "none"}
    preparation = DockerPreparation({prepared.row: prepared.image}, prepared.trees["baseline"],
                                    prepared.commits["baseline"], prepared.harness, timeout)
    live = () if models else AGENT_STAGES
    with ExitStack() as stack, LocalArtifacts(evidence / "artifacts", max_bytes=8 * 1024 * 1024) as store:
        runners = DockerRunners(prepared.harness, prepared.image, revisions, store, timeout, evidence / "runs", stack)
        return await record_run(evidence / "e2e", live, None if models else config, prepared.case, runners, route,
                                profiles, stages=AGENT_STAGES, scripted=models, catalog=prepared.catalog,
                                preparation=preparation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Benchmark case id or manifest directory under benchmarks/cases")
    parser.add_argument("--repository", required=True, type=Path, help="Local clone holding both commits")
    parser.add_argument("--image", action="append", required=True,
                        help="Prepared local image per matrix row: <row id>=sha256:<config id>")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--provider-config", required=True, type=Path, help="Per-agent provider JSON")
    parser.add_argument("--stage-profiles", type=Path, help="Optional JSON of per-stage request controls")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per runner or setup command")
    args = parser.parse_args()
    images = {}
    for value in args.image:
        if not (match := IMAGE.fullmatch(value)):
            parser.error(f"--image {value!r} is not <row id>=sha256:<64 hex config id>")
        images[match["row"]] = match["config"]
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    config = load_inference(args.provider_config)
    profiles = json.loads(args.stage_profiles.read_bytes()) if args.stage_profiles else None
    if profiles is not None:
        try:
            stage_configs(config, profiles, AGENT_STAGES)
        except ValueError as exc:
            parser.error(str(exc))
    args.evidence.mkdir(parents=True, mode=0o700)
    try:
        prepared = prepare_case(args.case, args.repository, args.evidence, images, args.timeout)
    except CaseRefused as refused:
        raise SystemExit(f"case refused: {refused}")
    run = asyncio.run(run_case(prepared, args.evidence, config, args.timeout, profiles))
    print(json.dumps(summary(run) | {
        "config_sha256": sha256((args.evidence / "e2e" / "configuration.json").read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
