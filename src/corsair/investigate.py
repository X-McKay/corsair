"""`uv run corsair run --issue-json <file> | --id <issue id>`: one issue investigated end to end.

The request (`corsair-issue-request/v1`) names the issue, the repository and its vulnerable and fixed commits; an
issue id (`github:owner/repo#N`, `azure:org/project#N`) is captured through the ticket readers into the same request
with the repository and commits given as flags (a GitHub issue defaults to its own repository). The
system selects the runtime from the repository's own build files, prepares the environment, identifies, plans,
authors, runs both revisions, gates and assesses. Everything a request does not carry is selected or inferred and
recorded with its basis. Today's route is image-only: the selected row's local image under plain Docker
(`corsair.investigation.docker`), every agent stage live on the provider. A request that cannot start is recorded
at admission with its reason before any model request; nothing is retried. Receipts, `record.json` and the summary
line go to a new private evidence directory; the line is also printed.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack, ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import traceback

import logfire

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.composition.direct import CompositionBudget, DirectRun, StageModels, run_direct
from corsair.composition.receipts import (AGENT_STAGES, VERSION_FIELDS, VERSIONS, Journal, _dump, attempt_record,
                                          result_record, stage_configs)
from corsair.inference.config import InferenceConfig, load_inference
from corsair.inference.models import configured_model, preflight
from corsair.investigation.build import Investigation, Refused, build
from corsair.investigation.docker import SETUP_NETWORK, DockerPreparation, DockerRunners, install
from corsair.investigation.issue_id import capture as capture_issue
from corsair.investigation.request import IssueRequest
from corsair.ports.tickets import TicketError
from corsair.investigation.results import record, summary_line

REPOSITORY = Path(__file__).resolve().parents[2]
IMAGE = re.compile(r"(?P<row>[a-z0-9][a-z0-9.-]*)=(?P<config>sha256:[0-9a-f]{64})")


def images(path: Path) -> dict[str, str]:
    """The operator's prepared local images, `{"<row id>": "sha256:<config id>"}`."""
    loaded = json.loads(path.read_text())
    if not isinstance(loaded, dict) or not all(IMAGE.fullmatch(f"{row}={config}") for row, config in loaded.items()):
        raise ValueError(f'{path}: expected {{"<row id>": "sha256:<config id>"}}')
    return loaded


async def _chain(investigation: Investigation, evidence: Path, config: InferenceConfig | None, models: dict | None,
                 profiles: dict | None, timeout: int, progress: dict) -> DirectRun:
    """`progress["phase"]` names where the run is, so a crash is recorded where it happened."""
    progress["phase"] = "dependency setup"
    revisions = {}
    for revision, commit in investigation.commits.items():
        dependencies = evidence / "dependencies" / revision
        install(investigation.harness, investigation.image, investigation.trees[revision], commit, dependencies,
                evidence / "setup" / revision)
        revisions[revision] = (investigation.trees[revision], dependencies.resolve(), commit)
    for name in ("artifacts", "receipts"):
        (evidence / name).mkdir(mode=0o700)
    receipts = evidence / "receipts"
    logfire.configure(send_to_logfire=False, console=False)
    budget = CompositionBudget()
    progress["phase"] = "model setup"
    async with AsyncExitStack() as stack:
        if models is None:
            configs = stage_configs(config, profiles or {}, AGENT_STAGES)
            for profile in configs.values():
                preflight(profile)
            built = {}
            for stage in AGENT_STAGES:
                if configs[stage] not in built:
                    built[configs[stage]] = await stack.enter_async_context(configured_model(configs[stage]))
            selected = {stage: built[configs[stage]] for stage in AGENT_STAGES}
        else:
            configs, selected = {}, {stage: models[stage]() for stage in AGENT_STAGES}
        (receipts / "configuration.json").write_text(json.dumps({
            "mode": "direct", "route": "docker_image_only", "setup_network": SETUP_NETWORK,
            "test_network": "none", "live_stages": list(configs),
            "stage_providers": {stage: c.model_dump() for stage, c in configs.items()}, "stage_profiles": profiles,
            "budget": budget.model_dump(),
            "versions": {stage: dict(zip(VERSION_FIELDS, VERSIONS[stage])) for stage in AGENT_STAGES},
            "prepared_images": dict(investigation.catalog.prepared), "image": investigation.image,
            "framework": investigation.framework.name, "runner": investigation.framework.runner,
            "repository": investigation.repository, "commits": investigation.commits, "bases": investigation.bases,
            "setup": _dump(investigation.case.setup), "issue_source": [f.path for f in investigation.case.issue.source_files],
            "runtime_inputs": sorted(investigation.case.runtime.files), "timeout_seconds": timeout,
            "source": {"python": sys.version}}, indent=2))
        preparation = DockerPreparation({investigation.row: investigation.image}, investigation.trees["baseline"],
                                        investigation.commits["baseline"], investigation.harness, timeout,
                                        evidence / "overlays")
        with ExitStack() as containers, LocalArtifacts(evidence / "artifacts", max_bytes=8 * 1024 * 1024) as store:
            journal = Journal(DockerRunners(investigation.harness, investigation.image, revisions, store, timeout,
                                            evidence / "runs", containers, preparation))
            progress["phase"], progress["journal"] = "chain", journal
            try:
                run = await run_direct(investigation.case, StageModels(**selected), journal, budget,
                                       catalog=investigation.catalog, preparation=preparation)
            finally:
                drained = await asyncio.to_thread(journal.drain, 900)
                with (receipts / "native-runs.json").open("x") as destination:
                    json.dump(journal.entries if drained else journal.entries + [{"in_flight_after_seconds": 900}],
                              destination, indent=2)
    progress["phase"] = "receipts"
    for index, attempt in enumerate(run.attempts):
        with (receipts / f"attempt-{index}-{attempt.stage}.json").open("x") as destination:
            json.dump(attempt_record(attempt), destination, indent=2)
    with (receipts / "result.json").open("x") as destination:
        json.dump(result_record(run), destination, indent=2)
    return run


def acquisition_for(hosts: frozenset[str], receipts: Path):
    """SPEC-0037 host acquisition for https repositories on the operator's allowed hosts; the host's proxy and CA
    come from `CORSAIR_GIT_PROXY` and `CORSAIR_GIT_CA`, never a credential."""
    import hashlib
    from corsair.adapters.git_acquire import AcquireLimits, GitAcquisition, HostTransport
    from corsair.adapters.git_source import Executable

    def pin(path):
        with open(path, "rb") as stream:
            return Executable(Path(path), hashlib.file_digest(stream, "sha256").hexdigest())
    ca = os.environ.get("CORSAIR_GIT_CA")
    transport = HostTransport(hosts, proxy=os.environ.get("CORSAIR_GIT_PROXY"), ca_bundle=Path(ca) if ca else None)
    receipts.mkdir(mode=0o700)
    return GitAcquisition(pin("/usr/bin/git"), pin("/usr/bin/prlimit"), transport=transport, limits=AcquireLimits(),
                          receipts=receipts)


def investigate(request: IssueRequest, evidence: Path, images: dict[str, str], *, roots: tuple[Path, ...] = (),
                hosts: frozenset[str] = frozenset(), config: InferenceConfig | None = None, models: dict | None = None,
                profiles: dict | None = None, timeout: int = 600) -> dict:
    """One investigation into the new private directory `evidence`; returns its record (`record.json`).

    `config` serves every agent stage; `models` replaces it with a model factory per stage (offline checks)."""
    if (config is None) == (models is None):
        raise ValueError("an investigation runs every stage on the provider, or on supplied models for offline checks")
    evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
    (evidence / "request.json").write_text(request.model_dump_json(by_alias=True, indent=2))
    try:
        with ExitStack() as stack:
            acquisition = stack.enter_context(acquisition_for(hosts, evidence / "acquisition")) if hosts else None
            investigation = build(request, evidence / "trees", images, roots=roots, acquisition=acquisition,
                                  timeout=timeout)
    except Refused as refused:
        item = record(request.label, evidence, refused=str(refused))
    else:
        progress = {"phase": "dependency setup"}
        try:
            run = asyncio.run(_chain(investigation, evidence, config, models, profiles, timeout, progress))
        except Exception as failure:
            if isinstance(failure, RuntimeError) and "dependency setup" in str(failure):
                item = record(request.label, evidence, investigation=investigation, refused=str(failure))
            else:
                # A crash (Docker, harness, provider setup, receipts) is recorded as ERROR where it happened, with
                # its traceback beside the record; never retried.
                (evidence / "error.txt").write_text(traceback.format_exc())
                phase = progress["phase"]
                if phase == "chain":
                    phase += f" after {len(progress['journal'].entries)} runner calls"
                item = record(request.label, evidence, investigation=investigation,
                              error=f"{type(failure).__name__}: {failure}"[:2048], crashed_in=phase)
        else:
            item = record(request.label, evidence, investigation=investigation, run=run)
    item["summary"] = summary_line(item)
    (evidence / "record.json").write_text(json.dumps(item, indent=2, default=str))
    return item


async def request_for_id(issue: str, provider_config: Path, **fields) -> IssueRequest:
    """The issue request for an issue id: the captured ticket plus the given repository, commits and scope; the
    operator's `tickets` source (if the provider file has one) supplies the token and limits."""
    from corsair.configuration import ProviderConfig
    value = json.loads(provider_config.read_text())
    configured = ProviderConfig.model_validate(value).tickets if isinstance(value, dict) and "inference" in value else None
    snapshot = await capture_issue(issue, configured)
    return IssueRequest.model_validate({"schema": "corsair-issue-request/v1", "issue": snapshot.model_dump(mode="json"),
                                        **{k: v for k, v in fields.items() if v is not None}})


def main(argv: list[str] | None = None, prog: str = "corsair run") -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    issue = parser.add_mutually_exclusive_group(required=True)
    issue.add_argument("--issue-json", type=Path, help="A corsair-issue-request/v1 file")
    issue.add_argument("--id", dest="issue", help="github:owner/repo#N or azure:org/project#N, captured read-only")
    parser.add_argument("--repository", help="With --id: https repository (default: a GitHub issue's own)")
    parser.add_argument("--revision", help="With --id: the vulnerable commit (40 hex)")
    parser.add_argument("--fixed-revision", help="With --id: the fix's commit (40 hex)")
    parser.add_argument("--scope", choices=("component", "application_path"), help="With --id: identification scope")
    parser.add_argument("--provider-config", required=True, type=Path, help="Per-agent provider JSON")
    parser.add_argument("--images", type=Path, default=os.environ.get("CORSAIR_IMAGES"),
                        help='JSON {"<row id>": "sha256:<config id>"}; default $CORSAIR_IMAGES')
    parser.add_argument("--local-root", type=Path, action="append", default=[],
                        help="Allowed root for file:// repositories (eval clones); repeatable")
    parser.add_argument("--repository-host", action="append", default=[],
                        help="Allowed host for https repositories, e.g. github.com; repeatable")
    parser.add_argument("--evidence", type=Path, help="New directory; default .runs/investigations/<UTC stamp>")
    parser.add_argument("--stage-profiles", type=Path, help="Optional JSON of per-stage request controls")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per runner or setup command")
    args = parser.parse_args(argv)
    given = [name for name in ("repository", "revision", "fixed_revision", "scope") if getattr(args, name)]
    if args.issue_json and given:
        parser.error(f"--issue-json carries {', '.join(given)} itself")
    try:
        prepared = images(args.images) if args.images else None
        if args.issue_json:
            request = IssueRequest.model_validate_json(args.issue_json.read_bytes())
        else:
            request = asyncio.run(request_for_id(args.issue, args.provider_config, repository=args.repository,
                                                 revision=args.revision, fixed_revision=args.fixed_revision,
                                                 scope=args.scope))
    except (ValueError, OSError, TicketError) as error:
        parser.error(str(error)[:2048])
    if prepared is None:
        parser.error("pass --images or set CORSAIR_IMAGES")
    evidence = args.evidence or REPOSITORY / ".runs/investigations" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if evidence.exists() or evidence.is_symlink():
        parser.error("evidence directory already exists")
    profiles = json.loads(args.stage_profiles.read_bytes()) if args.stage_profiles else None
    config = load_inference(args.provider_config)
    item = investigate(request, evidence, prepared, roots=tuple(args.local_root),
                       hosts=frozenset(args.repository_host), config=config, profiles=profiles,
                       timeout=args.timeout)
    print(item["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
