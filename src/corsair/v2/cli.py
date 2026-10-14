"""`corsair-v2`: run one case through the v2 chain, directly or as a Temporal workflow.

Stage progress goes to stderr. --format json emits one final versioned object
on completion or client cancellation; text mode adds recorded agent telemetry.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path("benchmarks/corpus/infosec-harness/manifest.json")
DEFAULT_PROVIDERS = Path("config/v2/providers.local.json")
DEFAULT_MATRIX = Path("deploy/v2/runtime-matrix.yaml")
CLI_SCHEMA = "corsair-v2-cli/1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corsair-v2", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="investigate one case")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="case name in the manifest")
    source.add_argument("--issue-json", type=Path, help="an issue snapshot file")
    run.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run.add_argument("--mode", choices=("direct", "temporal"), default="direct")
    run.add_argument("--run-root", type=Path, default=None, help="default: ./.runs/v2/runs")
    worker = commands.add_parser("worker", help="serve the three v2 task queues")
    runs = commands.add_parser("runs", help="inspect recorded runs")
    runs_commands = runs.add_subparsers(dest="runs_command", required=True)
    compare = runs_commands.add_parser("compare", help="outcome, cost and prompt versions per recorded run")
    compare.add_argument("run_dirs", type=Path, nargs="+")
    compare.add_argument("--agents", action="store_true", help="include recorded per-agent telemetry")
    for command in (run, compare):
        command.add_argument("--format", choices=("text", "json"), default="text")
    for command in (run, worker, compare):
        command.add_argument("--color", choices=("auto", "never"), default="auto")
    for command in (run, worker):
        command.add_argument("--provider-config", type=Path, default=DEFAULT_PROVIDERS)
        command.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
        command.add_argument("--temporal-address", default="localhost:7233")
        command.add_argument("--workspace-slots", type=int, default=4)
    return parser


def _intake(args):
    """Intake strips evaluator-only fields; nothing here prints manifest labels/oracles."""
    from . import intake
    if args.issue_json is not None:
        return intake.from_issue_json(args.issue_json)
    return intake.load_corpus_case(args.manifest, args.case)


def _print_json(record, verdict, data, *, interrupted: bool = False) -> None:
    print(json.dumps({"schema": CLI_SCHEMA, "state": data["state"], "run_id": record.run_id,
                      "run_dir": str(record.run_dir), "verdict": verdict.model_dump(mode="json") if verdict else None,
                      "totals": data["totals"] or None, "agents": data["agents"],
                      **({"client_interrupted": True} if interrupted else {})}))


async def _run(args) -> int:
    from .chain import default_stages, run_case
    from .models import agent_models, load_provider_config
    from .presentation import StageReporter, render_result
    from .record import RunRecorder
    from .runs import details

    case = _intake(args)
    config = load_provider_config(args.provider_config)
    record = RunRecorder.create(args.run_root)
    stages = default_stages()
    try:
        with StageReporter(color=args.color, animate=args.format == "text") as progress:
            progress.announce(f"corsair-v2: case {case.case_id} ({args.mode}); run {record.run_dir}")
            async with agent_models(config) as models:
                if args.mode == "direct":
                    verdict = await run_case(case, stages=stages, models=models, matrix_path=args.matrix, record=record,
                                             progress=progress, provider_config=args.provider_config)
                else:
                    from . import workflow
                    workflow.configure(stages, models, args.matrix, progress, args.provider_config)
                    client = await workflow.connect(args.temporal_address)
                    serving = asyncio.ensure_future(workflow.serve(client, workspace_slots=args.workspace_slots))
                    try:
                        verdict = await workflow.run_workflow(
                            client, workflow.RunRequest(case=case, run_dir=str(record.run_dir.resolve())),
                            workflow_id=f"corsair-v2-{record.run_id}")
                    finally:
                        serving.cancel()
                        await asyncio.gather(serving, return_exceptions=True)
    except asyncio.CancelledError:
        if args.format == "json":
            try:
                data = details(record.run_dir)
            except (OSError, ValueError):
                data = {"state": "incomplete", "totals": {}, "agents": {}}
            # Persisted state only: interrupting a client does not prove a remote workflow/command stopped.
            _print_json(record, None, data, interrupted=True)
        raise
    data = details(record.run_dir)
    if args.format == "json":
        _print_json(record, verdict, data)
    else:
        render_result(verdict, record.run_dir, data, color=args.color)
    return 0


async def _worker(args) -> int:
    from .chain import default_stages
    from .models import agent_models, load_provider_config
    from .presentation import StageReporter
    from . import workflow

    with StageReporter(color=args.color) as progress:
        async with agent_models(load_provider_config(args.provider_config)) as models:
            workflow.configure(default_stages(), models, args.matrix, progress, args.provider_config)
            client = await workflow.connect(args.temporal_address)
            progress.announce(f"corsair-v2 worker: serving {workflow.MODEL_QUEUE}, {workflow.WORKSPACE_QUEUE}, "
                              f"{workflow.CONTROL_QUEUE} on {args.temporal_address}")
            await workflow.serve(client, workspace_slots=args.workspace_slots)
    return 0


def _compare(args) -> int:
    from .presentation import agent_table, console
    from .runs import printable, row, table

    rows = [row(path) for path in args.run_dirs]  # validate every input before emitting any success output
    if args.format == "json":
        print(json.dumps({"schema": CLI_SCHEMA, "runs": rows}))
    else:
        print(table(args.run_dirs))
        if args.agents:
            out = console(color=args.color)
            for data in rows:
                out.print("\nRun", printable(data["run"]), markup=False)
                out.print(agent_table(data["agents"]))
            out.print("Agent seconds sum recorded calls, not elapsed run time. Missing telemetry is unknown.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "runs":
            return _compare(args)
        return asyncio.run(_run(args) if args.command == "run" else _worker(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130
    except (OSError, ValueError) as exc:
        from .presentation import console
        from .runs import printable
        console(color=args.color, stderr=True).print(printable(f"corsair-v2: {exc}"), markup=False)
        return 2


if __name__ == "__main__":
    sys.exit(main())
