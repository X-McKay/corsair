"""Finite commands; production investigations always go through Temporal."""

import argparse
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from pydantic import TypeAdapter
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from corsair.contracts import (
    BatchItem,
    BatchRequest,
    EvidenceInput,
    Identifier,
    InvestigationResult,
    Submission,
    digest,
)
from corsair.observability.evaluation import Oracle, load_dataset, save_report, score
from corsair.observability.logging import configure_logging, event, safe_error_detail, safe_text
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.requests import load_investigation_request
from corsair.runtime.terminal import Terminal
from corsair.settings import Settings, load_settings


class CliArguments(argparse.Namespace):
    """Arguments admitted by :func:`parser` after argparse command selection."""

    command: str
    settings: str | None
    format: Literal["auto", "human", "json"]
    no_color: bool
    no_animation: bool
    log_format: Literal["text", "json"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    log_file: str | None
    request: str
    submission: str
    run_id: str | None
    wait: bool
    online: bool
    watch: bool
    fixed: bool
    dataset: str
    repeats: int
    concurrency: int
    output: str | None
    run_ids: list[str]
    report: str


def validate_run_id(value: str) -> str:
    """Validate an operator-supplied Temporal identity before any service request."""
    TypeAdapter(Identifier).validate_python(value)
    if len(value) > 60:
        raise ValueError("run identity must leave space for operation suffixes")
    return value


def _settings(args: CliArguments) -> Settings:
    """Load settings only for commands that require local runtime configuration."""
    return load_settings(args.settings)


def _result_from_store(store: ArtifactStore, identity: str) -> InvestigationResult:
    """Read and validate the committed result receipt for one completed run."""
    ref = store.reconcile(f"result.{identity}")
    if ref is None:
        raise ValueError("No committed result; use --online to query the Temporal workflow")
    return InvestigationResult.model_validate(store.get_json(ref))


def _score_saved_result(
    store: ArtifactStore, identity: str, oracles: Mapping[str, Oracle]
) -> dict[str, object]:
    """Score one reconciled result while keeping unavailable receipts explicit."""
    try:
        result = _result_from_store(store, identity)
        oracle = oracles[result.case_id]
        return score(result, oracle, store)
    except (OSError, ValueError, KeyError) as error:
        return {"run_id": identity, "status": "unavailable", "reason": safe_text(error)}


async def _handle_report(args: CliArguments, ui: Terminal) -> int:
    """Display a saved evaluation summary without touching runtime services."""
    report = json.loads(Path(args.report).read_bytes())
    if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
        raise ValueError("report must contain a summary object")
    ui.emit(report["summary"])
    return 0


async def _handle_doctor(args: CliArguments, ui: Terminal) -> int:
    """Run the read-only infrastructure diagnosis."""
    from corsair.runtime.diagnostics import diagnose

    report = await ui.wait(
        diagnose(_settings(args)), "Checking real Docker and Temporal infrastructure"
    )
    ui.emit(report)
    return 0 if report["ready"] else 1


async def _handle_worker(args: CliArguments, ui: Terminal) -> int:
    """Run the Temporal worker until its local lifecycle ends."""
    from corsair.runtime.worker import run_worker

    await ui.wait(run_worker(_settings(args)), "Temporal worker lifecycle · Ctrl+C to stop")
    return 0


async def _handle_verify(args: CliArguments, ui: Terminal) -> int:
    """Execute one frozen native reference submission without a security verdict."""
    from corsair.runtime.manifest import build_manifest
    from corsair.runtime.native_evidence import run_evidence
    from corsair.tools.security.sandbox import DockerSandbox
    from corsair.tools.security.sources import prepare_case

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    request = load_investigation_request(Path(args.request))
    submission = Submission.model_validate_json(Path(args.submission).read_bytes())
    identity = validate_run_id(args.run_id or f"reference-{uuid4().hex}")
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


async def _handle_inspect(args: CliArguments, ui: Terminal) -> int:
    """Read a committed result, or query/watch its admitted Temporal workflow."""
    identity = validate_run_id(args.run_id or "")
    if args.watch and not args.online:
        raise ValueError("--watch requires --online")

    settings = _settings(args)
    if not args.online:
        store = ArtifactStore(settings.artifact_root)
        ui.emit(_result_from_store(store, identity))
        return 0

    from corsair.runtime.worker import connect
    from corsair.workflows.evaluation import EvaluationWorkflow
    from corsair.workflows.investigation import InvestigationWorkflow

    client = await ui.wait(connect(settings), "Connecting to Temporal")
    initial = client.get_workflow_handle(identity)
    description = await initial.describe()
    is_batch = description.workflow_type == "corsair.evaluation"
    if description.workflow_type not in {"corsair.investigation", "corsair.evaluation"}:
        raise ValueError("Workflow is not a Corsair investigation or evaluation")
    handle = client.get_workflow_handle(
        identity, result_type=list[BatchItem] if is_batch else InvestigationResult
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


async def _handle_cancel(args: CliArguments, ui: Terminal) -> int:
    """Request durable workflow cancellation without asserting cleanup completion."""
    from corsair.runtime.worker import connect

    identity = validate_run_id(args.run_id or "")
    client = await ui.wait(connect(_settings(args)), "Connecting to Temporal")
    await client.get_workflow_handle(identity).cancel()
    event("cancellation.requested", run_id=identity)
    ui.emit({"run_id": identity, "state": "cancellation_requested", "cleanup_confirmed": False})
    return 0


async def _handle_investigate(args: CliArguments, ui: Terminal) -> int:
    """Submit one investigation and optionally wait for its actual result."""
    from corsair.runtime.worker import connect
    from corsair.workflows.investigation import InvestigationWorkflow

    settings = _settings(args)
    request = load_investigation_request(Path(args.request))
    identity = validate_run_id(args.run_id or f"run-{uuid4().hex}")
    client = await ui.wait(connect(settings), "Connecting to Temporal")
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
    if not args.wait:
        ui.emit({"run_id": handle.id, "state": "submitted", "security_disposition": None})
        return 0

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


async def _handle_eval(args: CliArguments, ui: Terminal) -> int:
    """Run a frozen batch, score returned native receipts, and save its report."""
    from corsair.runtime.worker import connect
    from corsair.workflows.evaluation import EvaluationWorkflow

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    dataset, requests, oracles = load_dataset(Path(args.dataset))
    identity = validate_run_id(args.run_id or f"eval-{uuid4().hex}")
    batch = BatchRequest(
        batch_id=identity,
        requests=requests,
        repeats=args.repeats,
        concurrency=args.concurrency,
    )
    client = await ui.wait(connect(settings), "Connecting to Temporal")
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
    rows: list[dict[str, object]] = []
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


async def _handle_rescore(args: CliArguments, ui: Terminal) -> int:
    """Rescore committed evidence locally, retaining unavailable results in the report."""
    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    _, _, oracles = load_dataset(Path(args.dataset))
    rows = [
        _score_saved_result(store, validate_run_id(identity), oracles) for identity in args.run_ids
    ]
    output = Path(args.output or ".runs/evaluations/rescored.json")
    report = save_report(output, rows)
    ui.emit({"report": str(output), "summary": report["summary"]})
    return 0 if report["summary"]["failed"] == 0 else 1


CommandHandler = Callable[[CliArguments, Terminal], Awaitable[int]]
_COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "report": _handle_report,
    "doctor": _handle_doctor,
    "worker": _handle_worker,
    "verify": _handle_verify,
    "inspect": _handle_inspect,
    "cancel": _handle_cancel,
    "investigate": _handle_investigate,
    "eval": _handle_eval,
    "rescore": _handle_rescore,
}


async def execute(args: argparse.Namespace, terminal: Terminal | None = None) -> int:
    """Run exactly one parser-admitted command through its explicit handler."""
    command_args = cast(CliArguments, args)
    ui = terminal if terminal is not None else Terminal(command_args)
    handler = _COMMAND_HANDLERS.get(command_args.command)
    if handler is None:
        raise ValueError("Unknown command")
    return await handler(command_args, ui)


def _presentation_options(parser: argparse.ArgumentParser, *, defaults: bool = False) -> None:
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
    commands: dict[str, argparse.ArgumentParser] = {}
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
    args = cast(CliArguments, parser().parse_args())
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
        code = 130
    except Exception as error:
        detail = safe_error_detail(error)
        event("cli.failed", level=logging.ERROR, error_type=type(error).__name__, message=detail)
        code = 2
    # Exit after the handler: retaining exception tracebacks can retain native SDK clients.
    raise SystemExit(code)


if __name__ == "__main__":
    main()
