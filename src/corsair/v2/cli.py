"""`corsair-v2`: run one case through the v2 chain, directly or as a Temporal workflow.

    corsair-v2 run --case <name> [--manifest benchmarks/corpus/infosec-harness/manifest.json]
    corsair-v2 run --issue-json <file>
        [--provider-config config/v2/providers.local.json] [--mode direct|temporal] [--run-root DIR]
        [--matrix deploy/v2/runtime-matrix.yaml] [--temporal-address localhost:7233] [--workspace-slots N]
    corsair-v2 worker [--provider-config ...] [--matrix ...] [--temporal-address ...] [--workspace-slots N]
    corsair-v2 runs compare <run_dir> [<run_dir> ...]

Prints one progress line per stage, then the label, rule id, terminal reason and run directory. Only the
verdict is printed: a manifest's labels and oracles are never read out.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path("benchmarks/corpus/infosec-harness/manifest.json")
DEFAULT_PROVIDERS = Path("config/v2/providers.local.json")
DEFAULT_MATRIX = Path("deploy/v2/runtime-matrix.yaml")


def _progress(step: str, text: str) -> None:
    print(f"  {step:<28} {text}", flush=True)


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
    compare = runs_commands.add_parser("compare", help="one line per run: outcome, cost and prompt versions")
    compare.add_argument("run_dirs", type=Path, nargs="+")
    for command in (run, worker):
        command.add_argument("--provider-config", type=Path, default=DEFAULT_PROVIDERS)
        command.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
        command.add_argument("--temporal-address", default="localhost:7233")
        command.add_argument("--workspace-slots", type=int, default=4)
    return parser


def _intake(args):
    """Case from the manifest or an issue file. Intake strips evaluator-only fields; nothing here prints them."""
    from . import intake

    if args.issue_json is not None:
        return intake.from_issue_json(args.issue_json)
    return intake.load_corpus_case(args.manifest, args.case)


async def _run(args) -> int:
    from .chain import default_stages, run_case
    from .models import agent_models, load_provider_config
    from .record import RunRecorder

    case = _intake(args)
    config = load_provider_config(args.provider_config)
    record = RunRecorder.create(args.run_root)
    print(f"corsair-v2: case {case.case_id} ({args.mode}); run {record.run_dir}", flush=True)
    stages = default_stages()
    async with agent_models(config) as models:
        if args.mode == "direct":
            verdict = await run_case(case, stages=stages, models=models, matrix_path=args.matrix, record=record,
                                     progress=_progress, provider_config=args.provider_config)
        else:
            from . import workflow

            workflow.configure(stages, models, args.matrix, _progress, args.provider_config)
            client = await workflow.connect(args.temporal_address)
            serving = asyncio.ensure_future(workflow.serve(client, workspace_slots=args.workspace_slots))
            try:
                verdict = await workflow.run_workflow(
                    client, workflow.RunRequest(case=case, run_dir=str(record.run_dir.resolve())),
                    workflow_id=f"corsair-v2-{record.run_id}")
            finally:
                serving.cancel()
                await asyncio.gather(serving, return_exceptions=True)
    print(f"label: {verdict.label.value}\nrule: {verdict.rule_id}\nterminal reason: {verdict.terminal_reason.value}\n"
          f"run dir: {record.run_dir}", flush=True)
    return 0


async def _worker(args) -> int:
    from .chain import default_stages
    from .models import agent_models, load_provider_config
    from . import workflow

    async with agent_models(load_provider_config(args.provider_config)) as models:
        workflow.configure(default_stages(), models, args.matrix, _progress, args.provider_config)
        client = await workflow.connect(args.temporal_address)
        print(f"corsair-v2 worker: serving {workflow.MODEL_QUEUE}, {workflow.WORKSPACE_QUEUE}, "
              f"{workflow.CONTROL_QUEUE} on {args.temporal_address}", flush=True)
        await workflow.serve(client, workspace_slots=args.workspace_slots)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "runs":
        from .runs import table

        print(table(args.run_dirs))
        return 0
    try:
        return asyncio.run(_run(args) if args.command == "run" else _worker(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
