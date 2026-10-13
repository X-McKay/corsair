"""Run one E2E-0 direct composition over the SPEC-0018 pair and keep every stage receipt.

Stages not named in --live use scripted plumbing models. By default this CLI executes on the reviewed
host workspace, which admits only the reviewed SPEC-0018 test bytes: a live author's own test code is
refused before it reaches an interpreter. `--sandbox docker` runs every purpose in a fresh offline
container of the local CPython 3.12 toolchain image instead (unqualified, risk accepted; `docker.py`),
so a live author's tests execute there. The live gate `make qualify-fixture-e2e` runs the same
`record_run` over the OpenShell test workspace. Existing evidence directories are refused.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack, ExitStack
import os
from hashlib import sha256
import json
from pathlib import Path
import sys

import logfire

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.provider import LocalModelConfig
from corsair.inference.config import InferenceConfig, load_inference
from corsair.inference.models import configured_model, preflight
# Re-exported: the evals and qualification tests read the shared receipts from here.
from corsair.composition.receipts import (AGENT_STAGES, PROFILE_FIELDS, STAGES, VERSION_FIELDS, VERSIONS, Journal,  # noqa: F401
                                          _dump, attempt_record, encode, result_record, stage_configs)
from corsair.composition.direct import (CompositionBudget, DirectRun, FixtureCase, Preparation, StageModels,
                                        run_direct)
from corsair.nodes.runtime.environment import RuntimeCatalog
from corsair.investigate import images
from evals.issue_analysis.evaluate import describe_model

from .case import (fixture_case, reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
                   scripted_planning)

SCRIPTED = {"identification": scripted_identification, "planning": scripted_planning,
            "authoring": scripted_authoring, "assessment": scripted_assessment}
async def record_run(evidence: Path, live: tuple[str, ...], config: LocalModelConfig | InferenceConfig | None, case: FixtureCase,
                     runners, runner: dict, profiles: dict | None = None, drain_seconds: float = 900, *,
                     stages: tuple[str, ...] = STAGES, scripted: dict | None = None,
                     catalog: RuntimeCatalog | None = None, preparation: Preparation | None = None) -> DirectRun:
    """Run one composition into an existing private evidence directory and keep every receipt.

    ``runner`` describes the operator's execution route for configuration.json; ``profiles`` are the
    optional per-stage provider overrides (``stage_configs``). ``stages`` are the agent stages the case
    reaches; each is live or has a ``scripted`` model factory (the fixture's by default). ``catalog`` and
    ``preparation`` are the runtime and environment stages' operator ports for a case with build files
    and setup source.
    """
    logfire.configure(send_to_logfire=False, console=False)
    async with AsyncExitStack() as stack:
        configs = stage_configs(config, profiles or {}, live) if live else {}
        for profile in configs.values():
            preflight(profile)
        models = {}
        for stage in live:
            if configs[stage] not in models:
                models[configs[stage]] = await stack.enter_async_context(configured_model(configs[stage]))
        if scripted is None:
            scripted = SCRIPTED | {"planning": lambda: scripted_planning(case.environment.discovery_command)}
        if missing := [stage for stage in stages if stage not in live and stage not in scripted]:
            raise ValueError(f"stages {missing} are neither live nor scripted")
        selected = {stage: models[configs[stage]] if stage in live else scripted[stage]() for stage in stages}
        budget = CompositionBudget()
        (evidence / "configuration.json").write_text(json.dumps({
            "mode": "direct", "live_stages": list(live), "budget": budget.model_dump(),
            "provider": config.model_dump() if config else None, "stage_profiles": profiles,
            "stage_providers": {stage: configs[stage].model_dump() for stage in live},
            "models": {stage: describe_model(selected[stage]) for stage in stages},
            "versions": {stage: dict(zip(VERSION_FIELDS, VERSIONS[stage]))
                         for stage in stages},
            "prepared_images": dict(catalog.prepared) if catalog else None, "setup": _dump(case.setup),
            "runtime_inputs": sorted(case.runtime.files) if case.runtime else None,
            "runner": runner, "witness_capture": "operator_probe" if case.witness_envelope else "none",
            "witness_envelope": encode(case.witness_envelope),
            "environment": _dump(case.environment), "environment_identity": _dump(case.environment_identity),
            "revision_sources": case.revision_sources, "source": {"python": sys.version}}, indent=2))
        journal = Journal(runners)
        try:
            run = await run_direct(case, StageModels(**selected), journal, budget, catalog=catalog,
                                   preparation=preparation)
        finally:
            # A timed-out stage leaves its runner call finishing in a worker thread; keep its observation.
            drained = await asyncio.to_thread(journal.drain, drain_seconds)
            with (evidence / "native-runs.json").open("x") as destination:
                json.dump(journal.entries if drained else journal.entries + [{"in_flight_after_seconds": drain_seconds}],
                          destination, indent=2)
    for index, attempt in enumerate(run.attempts):
        with (evidence / f"attempt-{index}-{attempt.stage}.json").open("x") as destination:
            json.dump(attempt_record(attempt), destination, indent=2)
    with (evidence / "result.json").open("x") as destination:
        json.dump(result_record(run) | {"runner": runner}, destination, indent=2)
    return run


async def main_async(evidence: Path, live: tuple[str, ...], config: LocalModelConfig | InferenceConfig | None,
                     profiles: dict | None = None) -> DirectRun:
    """Reviewed host workspace: only the reviewed SPEC-0018 test bytes execute."""
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / "work").mkdir(mode=0o700)
    (evidence / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(evidence / "artifacts", max_bytes=4 * 1024 * 1024) as store:
        return await record_run(evidence, live, config, fixture_case(), reviewed_runners(store, evidence / "work"),
                                {"route": "reviewed_host_workspace"}, profiles)


async def docker_async(evidence: Path, live: tuple[str, ...], config: LocalModelConfig | InferenceConfig | None,
                       image: str, profiles: dict | None = None, timeout: int = 120) -> DirectRun:
    """Plain Docker: every purpose in a fresh offline container of `image`; unqualified, risk accepted."""
    from .docker import ROUTE, ROW, docker_case, docker_runners, limits
    evidence.mkdir(parents=True, exist_ok=False)
    evidence = evidence.resolve()  # LocalArtifacts and the container mounts need absolute paths
    (evidence / "artifacts").mkdir(mode=0o700)
    (evidence / "docker").mkdir(mode=0o700)
    with ExitStack() as containers, LocalArtifacts(evidence / "artifacts", max_bytes=4 * 1024 * 1024) as store:
        runners = docker_runners(image, evidence / "docker", store, containers, timeout)
        return await record_run(evidence, live, config, docker_case(image, timeout), runners,
                                ROUTE | {"image_row": ROW, "image": image, "limits": limits(timeout)}, profiles)


def summary(run: DirectRun) -> dict:
    gate = run.gate.permitted.model_dump() if run.gate else None
    proposal = run.assessment.admission.model_dump(mode="json") if run.assessment else None
    return {"stopped_at": run.stopped_at, "reason": run.reason, "gate": gate, "admission": proposal,
            "usage": {f"{index}-{a.stage}": {"requests": a.usage.requests, "tool_calls": a.usage.tool_calls,
                                             "input_tokens": a.usage.input_tokens,
                                             "output_tokens": a.usage.output_tokens,
                                             "elapsed_seconds": round(a.elapsed_seconds, 1),
                                             "tool_calls_limit": a.limits and a.limits.tool_calls_limit,
                                             "exhausted": a.exhausted and a.exhausted.limit,
                                             "tool_cap_reached": a.tool_cap_reached,
                                             "failure": None if a.failure is None else type(a.failure).__name__}
                      for index, a in enumerate(run.attempts)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, help="Per-agent provider JSON (or legacy LocalModelConfig); required with --live")
    parser.add_argument("--stage-profiles", type=Path,
                        help="Optional JSON of per-stage request controls layered on --provider-config")
    parser.add_argument("--live", default="", help=f"Comma-separated stages to run on the provider: {','.join(STAGES)}")
    parser.add_argument("--sandbox", choices=("host", "docker"), default="host",
                        help="host: the reviewed host workspace (reviewed test bytes only); docker: a fresh offline "
                             "container per run, unqualified (risk accepted)")
    parser.add_argument("--images", type=Path, default=os.environ.get("CORSAIR_IMAGES"),
                        help='With --sandbox docker: JSON {"<row id>": "sha256:<config id>"}; default $CORSAIR_IMAGES')
    parser.add_argument("--timeout", type=int, default=120, help="With --sandbox docker: seconds per container command")
    args = parser.parse_args()
    live = tuple(stage for stage in args.live.split(",") if stage)
    if set(live) - set(STAGES) or (live and args.provider_config is None):
        parser.error("--live names unknown stages or lacks --provider-config")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence directory already exists")
    config = load_inference(args.provider_config) if args.provider_config else None
    profiles = json.loads(args.stage_profiles.read_bytes()) if args.stage_profiles else None
    if profiles is not None:
        if config is None:
            parser.error("--stage-profiles needs --provider-config")
        try:
            stage_configs(config, profiles, live)
        except ValueError as exc:
            parser.error(str(exc))
    if args.sandbox == "docker":
        from .docker import ROW
        try:
            image = images(args.images)[ROW] if args.images else None
        except (ValueError, OSError, KeyError) as exc:
            parser.error(f"--images needs a {ROW} entry: {exc}"[:2048])
        if image is None:
            parser.error("--sandbox docker needs --images or CORSAIR_IMAGES")
        run = asyncio.run(docker_async(args.evidence, live, config, image, profiles, args.timeout))
    else:
        run = asyncio.run(main_async(args.evidence, live, config, profiles))
    route = json.loads((args.evidence / "configuration.json").read_text())["runner"]
    containers = args.evidence / "docker" / "containers.json"
    removed = ([c["cleanup"] for c in json.loads(containers.read_text())] if containers.exists() else None)
    print(json.dumps(summary(run) | {"route": route["route"], "qualification": route.get("qualification"),
                                     "container_cleanup": removed,
        "config_sha256": sha256((args.evidence / "configuration.json").read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
