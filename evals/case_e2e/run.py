"""`make run CASE=<id>`: one benchmark case through the issue entry for diagnosis, never a baseline.

Writes the case's issue request (`issue.json`) and expected outcome (`expected.json`, never read by the
investigation) into a new run directory, calls `corsair.investigate` on the request with the case-source root as the
only allowed local repository root, then joins the expectation to the investigation's record. Cohorts, comparisons
and baselines go through `make eval AGENT=chain SET=<cohort>` (`evaluate.py`). Clones come from
`CORSAIR_CASE_SOURCES` (`<dir>/<case id>/repo`) and prepared local images from `CORSAIR_IMAGES`.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from corsair.inference.config import InferenceConfig, load_inference
from corsair.investigate import REPOSITORY, images, investigate
from corsair.investigation.results import with_expected

from .case import CaseRefused, case_request, entry, expected


def run_case(case: str, directory: Path, sources: Path, prepared_images: dict[str, str], *,
             config: InferenceConfig | None = None, models: dict | None = None, profiles: dict | None = None,
             timeout: int = 600) -> dict:
    """One case into the new private `directory`: the request and expectation, then the investigation under
    `directory/investigation`; returns the case record (also `case.json`)."""
    found = entry(case)
    request, oracle = case_request(found, sources), expected(found)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    (directory / "issue.json").write_text(request.model_dump_json(by_alias=True, indent=2))
    (directory / "expected.json").write_text(json.dumps(None if oracle is None else oracle.model_dump(mode="json"), indent=2))
    item = investigate(request, directory / "investigation", prepared_images, roots=(sources,), config=config,
                       models=models, profiles=profiles, timeout=timeout)
    item = with_expected(item, found.inventory.case_id, oracle) | {"case_language": found.inventory.language}
    (directory / "case.json").write_text(json.dumps(item, indent=2, default=str))
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Benchmark case id or manifest directory under benchmarks/cases")
    parser.add_argument("--provider-config", required=True, type=Path, help="Per-agent provider JSON")
    parser.add_argument("--evidence", type=Path, help="New directory; default .runs/cases/<case>-<UTC stamp>")
    parser.add_argument("--stage-profiles", type=Path, help="Optional JSON of per-stage request controls")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per runner or setup command")
    args = parser.parse_args()
    missing = [name for name in ("CORSAIR_CASE_SOURCES", "CORSAIR_IMAGES") if not os.environ.get(name)]
    if missing:
        parser.error(f"set {', '.join(missing)}")
    try:
        found = entry(args.case)
        prepared_images = images(Path(os.environ["CORSAIR_IMAGES"]))
    except (CaseRefused, ValueError, OSError) as error:
        parser.error(str(error))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = args.evidence or REPOSITORY / ".runs/cases" / f"{found.inventory.case_id.replace('/', '_')}-{stamp}"
    if directory.exists() or directory.is_symlink():
        parser.error("evidence directory already exists")
    profiles = json.loads(args.stage_profiles.read_bytes()) if args.stage_profiles else None
    item = run_case(args.case, directory, Path(os.environ["CORSAIR_CASE_SOURCES"]).resolve(), prepared_images,
                    config=load_inference(args.provider_config), profiles=profiles, timeout=args.timeout)
    print(item["summary"])
    print(f"expected: {item['expected']}; matches: {item['matches_expected']}")


if __name__ == "__main__":
    main()
