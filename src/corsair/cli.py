"""Finite commands; production investigations always go through Temporal."""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from corsair.contracts import (
    BatchItem,
    BatchRequest,
    EvidenceInput,
    Identifier,
    InvestigationRequest,
    InvestigationResult,
    Submission,
    digest,
)
from corsair.observability.evaluation import load_dataset, save_report, score
from corsair.observability.logging import configure_logging, event, safe_text
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.terminal import Terminal
from corsair.settings import load_settings


def run_id(value: str) -> str:
    TypeAdapter(Identifier).validate_python(value)
    if len(value) > 60:
        raise ValueError("run identity must leave space for operation suffixes")
    return value


def request_from_file(path: Path) -> InvestigationRequest:
    request = InvestigationRequest.model_validate_json(path.read_bytes())
    base = path.parent.resolve()
    source = request.case.source.model_copy(
        update={"path": str((base / request.case.source.path).absolute())}
    )
    fixed = request.case.fixed_source
    if fixed:
        fixed = fixed.model_copy(update={"path": str((base / fixed.path).absolute())})
    return request.model_copy(
        update={"case": request.case.model_copy(update={"source": source, "fixed_source": fixed})}
    )


async def execute(args, terminal: Terminal | None = None) -> int:
    ui = terminal or Terminal(args)
    if args.command == "report":
        report = json.loads(Path(args.report).read_text())
        if "summary" not in report:
            raise ValueError("report must contain a summary object")
        ui.emit(report["summary"])
        return 0
    settings = load_settings(args.settings)
    if args.command == "doctor":
        from corsair.runtime.diagnostics import diagnose

        report = await ui.wait(
            diagnose(settings), "Checking real Docker and Temporal infrastructure"
        )
        ui.emit(report)
        return 0 if report["ready"] else 1
    if args.command == "worker":
        from corsair.runtime.worker import run_worker

        await ui.wait(run_worker(settings), "Temporal worker lifecycle · Ctrl+C to stop")
        return 0
    store = ArtifactStore(settings.artifact_root)
    if args.command == "verify":
        from corsair.runtime.manifest import build_manifest
        from corsair.runtime.native_evidence import run_evidence
        from corsair.tools.security.sandbox import DockerSandbox
        from corsair.tools.security.sources import prepare_case

        request = request_from_file(Path(args.request))
        submission = Submission.model_validate_json(Path(args.submission).read_bytes())
        identity = run_id(args.run_id or f"reference-{uuid4().hex}")
        sandbox = DockerSandbox(settings)
        image_id = await ui.wait(
            asyncio.to_thread(lambda: sandbox.image_id), "Resolving native Docker image"
        )
        prepared = await ui.wait(
            asyncio.to_thread(
                prepare_case,
                request.case,
                settings,
                store,
                build_manifest(request, settings, image_id),
            ),
            "Admitting immutable source snapshot",
        )
        event("reference.started", run_id=identity, case_id=prepared.case_id, image_id=image_id)
        observation = await ui.wait(
            run_evidence(
                EvidenceInput(
                    run_id=identity,
                    operation_id=f"{identity}.reference",
                    prepared=prepared,
                    submission=submission,
                    budget=request.budget,
                    fixed=args.fixed,
                ),
                settings,
                store,
                sandbox=sandbox,
            ),
            "Executing native control and adversarial inputs · no security verdict",
        )
        ui.emit(observation)
        healthy = (
            observation.feedback is None
            and observation.cleanup_confirmed
            and observation.control is not None
            and observation.adversarial is not None
            and observation.control.outcome.value == "PROPERTY_HELD"
            and observation.adversarial.outcome.value in {"PROPERTY_HELD", "VIOLATION"}
        )
        event(
            "reference.completed",
            run_id=identity,
            cleanup_confirmed=observation.cleanup_confirmed,
            gate=observation.feedback.gate if observation.feedback else None,
            status="pass" if healthy else "fail",
        )
        return 0 if healthy else 1
    if args.command == "inspect" and not args.online:
        if args.watch:
            raise ValueError("--watch requires --online")
        ref = store.reconcile(f"result.{args.run_id}")
        if ref is None:
            raise ValueError("No committed result; use --online to query the Temporal workflow")
        ui.emit(InvestigationResult.model_validate(store.get_json(ref)))
        return 0
    if args.command == "rescore":
        _, _, oracles = load_dataset(Path(args.dataset))
        rows = []
        for identity in args.run_ids:
            try:
                ref = store.reconcile(f"result.{identity}")
                if ref is None:
                    raise ValueError("No committed result")
                result = InvestigationResult.model_validate(store.get_json(ref))
                rows.append(score(result, oracles[result.case_id], store))
            except (OSError, ValueError, KeyError) as error:
                rows.append(
                    {"run_id": identity, "status": "unavailable", "reason": safe_text(error)}
                )
        report = save_report(Path(args.output), rows)
        ui.emit({"report": args.output, "summary": report["summary"]})
        return 0 if report["summary"]["failed"] == 0 else 1

    from datetime import timedelta

    from corsair.runtime.worker import connect
    from corsair.workflows.evaluation import EvaluationWorkflow
    from corsair.workflows.investigation import InvestigationWorkflow

    client = await ui.wait(connect(settings), "Connecting to Temporal")
    if args.command == "investigate":
        request = request_from_file(Path(args.request))
        identity = run_id(args.run_id or f"run-{uuid4().hex}")
        handle = await client.start_workflow(
            InvestigationWorkflow.run,
            request,
            id=identity,
            task_queue=settings.task_queue,
            execution_timeout=timedelta(seconds=request.budget.max_elapsed_seconds + 120),
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        event(
            "investigation.submitted",
            run_id=handle.id,
            case_id=request.case.case_id,
            task_queue=settings.task_queue,
        )
        if args.wait:
            result = await ui.wait(
                handle.result(),
                f"Investigation {handle.id}",
                query=lambda: handle.query(InvestigationWorkflow.status),
            )
            ui.emit(result)
            event(
                "investigation.completed",
                run_id=handle.id,
                execution_status=result.execution_status,
                disposition=result.disposition,
            )
            return 0 if result.execution_status.value == "COMPLETED" else 1
        ui.emit({"run_id": handle.id, "state": "submitted", "security_disposition": None})
        return 0
    if args.command == "inspect":
        initial = client.get_workflow_handle(args.run_id)
        description = await initial.describe()
        is_batch = description.workflow_type == "corsair.evaluation"
        if description.workflow_type not in {"corsair.investigation", "corsair.evaluation"}:
            raise ValueError("Workflow is not a Corsair investigation or evaluation")
        handle = client.get_workflow_handle(
            args.run_id, result_type=list[BatchItem] if is_batch else InvestigationResult
        )
        query = EvaluationWorkflow.status if is_batch else InvestigationWorkflow.status
        if args.watch:
            ui.emit(
                await ui.wait(
                    handle.result(),
                    f"{'Evaluation' if is_batch else 'Investigation'} {handle.id}",
                    query=lambda: handle.query(query),
                )
            )
        else:
            ui.emit(await handle.query(query, rpc_timeout=timedelta(seconds=5)))
        return 0
    if args.command == "cancel":
        await client.get_workflow_handle(args.run_id).cancel()
        event("cancellation.requested", run_id=args.run_id)
        ui.emit(
            {"run_id": args.run_id, "state": "cancellation_requested", "cleanup_confirmed": False}
        )
        return 0
    if args.command == "eval":
        dataset, requests, oracles = load_dataset(Path(args.dataset))
        identity = run_id(args.run_id or f"eval-{uuid4().hex}")
        batch = BatchRequest(
            batch_id=identity, requests=requests, repeats=args.repeats, concurrency=args.concurrency
        )
        handle = await client.start_workflow(
            EvaluationWorkflow.run,
            batch,
            id=identity,
            task_queue=settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        event("evaluation.submitted", run_id=identity, total=len(requests) * args.repeats)
        items: list[BatchItem] = await ui.wait(
            handle.result(),
            f"Evaluation {handle.id}",
            query=lambda: handle.query(EvaluationWorkflow.status),
        )
        rows = []
        for item in items:
            try:
                if item.artifact is None:
                    raise ValueError(item.error or "Result artifact unavailable")
                result = InvestigationResult.model_validate(store.get_json(item.artifact))
                if result.case_id != item.case_id or result.run_id != item.run_id:
                    raise ValueError("Child result identity differs from its batch receipt")
                rows.append(score(result, oracles[item.case_id], store))
            except (OSError, ValueError, KeyError) as error:
                rows.append(
                    {
                        "case_id": item.case_id,
                        "run_id": item.run_id,
                        "status": "unavailable",
                        "reason": safe_text(error),
                    }
                )
        output = Path(args.output or f".runs/evaluations/{identity}.json")
        report = save_report(output, rows)
        report["dataset_digest"] = digest(dataset)
        output.write_text(json.dumps(report, indent=2) + "\n")
        ui.emit({"report": str(output), "summary": report["summary"]})
        event("evaluation.completed", run_id=identity, completed=len(items), total=len(items))
        return 0 if report["summary"]["failed"] == 0 else 1
    raise ValueError("Unknown command")


def _presentation_options(parser, *, defaults=False):
    absent = None if defaults else argparse.SUPPRESS
    parser.add_argument(
        "--settings", default=absent, help="Worker/client settings JSON; no credentials"
    )
    parser.add_argument(
        "--format",
        choices=("auto", "human", "json"),
        default="auto" if defaults else argparse.SUPPRESS,
        help="auto: human on a terminal, JSON in pipes",
    )
    parser.add_argument(
        "--no-color", action="store_true", default=False if defaults else argparse.SUPPRESS
    )
    parser.add_argument(
        "--no-animation", action="store_true", default=False if defaults else argparse.SUPPRESS
    )
    parser.add_argument(
        "--log-format",
        choices=("text", "json"),
        default="text" if defaults else argparse.SUPPRESS,
        help="stderr log encoding",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO" if defaults else argparse.SUPPRESS,
    )
    parser.add_argument("--log-file", default=absent, help="Mirror safe metadata to a JSONL file")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Corsair · Evidence-first investigation with Google ADK + Temporal"
    )
    _presentation_options(root, defaults=True)
    root.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = root.add_subparsers(dest="command", required=True, title="commands")
    descriptions = {
        "doctor": "Check actual Docker, namespace and worker poller readiness; no model calls",
        "worker": "Run the native Temporal worker; Ctrl+C stops gracefully",
        "investigate": "Submit a durable investigation; use --wait for live phase updates",
        "inspect": "Read a committed result or query/watch the native Temporal workflow",
        "cancel": "Request cancellation; this does not assert completed cleanup",
        "verify": "Execute a frozen reference submission natively; no security verdict",
        "eval": "Run frozen cases with bounded child workflows and external oracles",
        "rescore": "Revalidate saved native evidence and apply current verdict policy",
        "report": "Display an existing evaluation summary without contacting services",
    }
    commands = {}
    for name, description in descriptions.items():
        commands[name] = sub.add_parser(name, help=description, description=description)
        _presentation_options(commands[name])
    investigate = commands["investigate"]
    investigate.add_argument(
        "request", help="Case request JSON; source paths relative to this file"
    )
    investigate.add_argument("--run-id")
    investigate.add_argument("--wait", action="store_true")
    inspect = commands["inspect"]
    inspect.add_argument("run_id")
    inspect.add_argument("--online", action="store_true")
    inspect.add_argument(
        "--watch", action="store_true", help="Wait for actual completion; requires --online"
    )
    commands["cancel"].add_argument("run_id")
    verify = commands["verify"]
    verify.add_argument("request")
    verify.add_argument("submission")
    verify.add_argument("--run-id")
    verify.add_argument("--fixed", action="store_true")
    evaluation = commands["eval"]
    evaluation.add_argument("dataset")
    evaluation.add_argument("--run-id")
    evaluation.add_argument("--repeats", type=int, default=1)
    evaluation.add_argument("--concurrency", type=int, default=2)
    evaluation.add_argument("--output")
    rescore = commands["rescore"]
    rescore.add_argument("dataset")
    rescore.add_argument("run_ids", nargs="+")
    rescore.add_argument("--output", default=".runs/evaluations/rescored.json")
    commands["report"].add_argument("report")
    return root


def main() -> None:
    args = parser().parse_args()
    terminal = Terminal(args)
    try:
        configure_logging(
            terminal.err, level=args.log_level, format=args.log_format, path=args.log_file
        )
        code = asyncio.run(execute(args, terminal))
    except KeyboardInterrupt:
        event(
            "cli.interrupted",
            level=logging.WARNING,
            message="Local wait stopped; workflows continue. Use corsair cancel RUN_ID.",
        )
        raise SystemExit(130) from None
    except Exception as error:
        if isinstance(error, ValidationError):
            detail = "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                for item in error.errors(include_input=False, include_url=False)
            )
        else:
            detail = safe_text(error)
        event("cli.failed", level=logging.ERROR, error_type=type(error).__name__, message=detail)
        raise SystemExit(2) from None
    raise SystemExit(code)


if __name__ == "__main__":
    main()
