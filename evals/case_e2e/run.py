"""`make run CASE=<id>`: one benchmark case through the chain for diagnosis, never a baseline (image-only, Docker).
Cohorts, comparisons and baselines go through `make eval AGENT=chain SET=<cohort>` (`evaluate.py`).

The case's manifest and a local clone holding its baseline and candidate commits become the chain input
(`case.py`); runtime selection picks the matrix row from the baseline's build files and its framework row picks the
runner (`frameworks.py`). Each revision's own dependencies are installed once with registry access, then the
environment stage prepares the selected image with the environment agent and every test run is offline in a fresh
container (`docker.py`). Every agent stage is live on the provider: a real case has no scripted plumbing. The case
runs once, never retried; a case that cannot start is recorded with its reason before any model request. The result
line (`results.py`) is printed and kept beside the receipts. Existing evidence directories are refused.
"""
import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.composition.direct import DirectRun
from corsair.inference.config import InferenceConfig, load_inference
from evals.fixture_e2e.run import AGENT_STAGES, record_run, stage_configs

from .case import REPOSITORY, CaseRefused, CaseRun, build_case, entry
from .docker import DockerPreparation, DockerRunners, install
from .results import result_line

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


def images(path: Path) -> dict[str, str]:
    """The operator's prepared local images, `{"<row id>": "sha256:<config id>"}`."""
    loaded = json.loads(path.read_text())
    if not isinstance(loaded, dict) or not all(IMAGE.fullmatch(f"{row}={config}") for row, config in loaded.items()):
        raise ValueError(f"{path}: expected {{\"<row id>\": \"sha256:<config id>\"}}")
    return loaded


def main():
    """`make run CASE=<id>`: one case for diagnosis, never a baseline; the result line goes to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Benchmark case id or manifest directory under benchmarks/cases")
    parser.add_argument("--evidence", type=Path, help="New private directory; default .runs/cases/<case>-<UTC stamp>")
    parser.add_argument("--provider-config", required=True, type=Path, help="Per-agent provider JSON")
    parser.add_argument("--repository", type=Path, help="Local clone holding both commits; default "
                        "$CORSAIR_CASE_SOURCES/<case id>/repo")
    parser.add_argument("--images", type=Path, default=os.environ.get("CORSAIR_CASE_IMAGES"),
                        help='JSON {"<row id>": "sha256:<config id>"}; default $CORSAIR_CASE_IMAGES')
    parser.add_argument("--stage-profiles", type=Path, help="Optional JSON of per-stage request controls")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per runner or setup command")
    args = parser.parse_args()
    try:
        found = entry(args.case)
        prepared_images = images(args.images) if args.images else None
    except (CaseRefused, ValueError, OSError) as exc:
        parser.error(str(exc))
    if prepared_images is None:
        parser.error("pass --images or set CORSAIR_CASE_IMAGES")
    case_id = found.inventory.case_id
    repository = args.repository or (Path(os.environ["CORSAIR_CASE_SOURCES"]) / case_id.replace("/", "_") / "repo"
                                     if os.environ.get("CORSAIR_CASE_SOURCES") else None)
    if repository is None:
        parser.error("pass --repository or set CORSAIR_CASE_SOURCES")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = args.evidence or REPOSITORY / ".runs/cases" / f"{case_id.replace('/', '_')}-{stamp}"
    if evidence.exists() or evidence.is_symlink():
        parser.error("evidence directory already exists")
    config = load_inference(args.provider_config)
    profiles = json.loads(args.stage_profiles.read_bytes()) if args.stage_profiles else None
    if profiles is not None:
        try:
            stage_configs(config, profiles, AGENT_STAGES)
        except ValueError as exc:
            parser.error(str(exc))
    evidence.mkdir(parents=True, mode=0o700)
    expected = found.manifest.evaluator.expected
    context = dict(case_id=case_id, language=found.inventory.language, expected=expected.chain if expected else None,
                   evidence=evidence)
    try:
        prepared = prepare_case(args.case, repository, evidence, prepared_images, args.timeout)
    except CaseRefused as refused:
        line = result_line(**context, refused=str(refused))
    else:
        line = result_line(**context, prepared=prepared,
                           run=asyncio.run(run_case(prepared, evidence, config, args.timeout, profiles)))
    (evidence / "result-line.json").write_text(json.dumps(line, indent=2, default=str))
    print(json.dumps(line, indent=2, default=str))


if __name__ == "__main__":
    main()
