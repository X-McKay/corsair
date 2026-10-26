"""Finite commands; production investigations always go through Temporal.

Module scope imports only the standard library and the sanitized logger, so ``--help``,
``--version`` and argument errors exit before Rich, Pydantic contracts, the scorer or any SDK
loads. Each handler imports what its command uses.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

from corsair.observability.logging import configure_logging, event, safe_text

if TYPE_CHECKING:
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import BatchItem, InvestigationResult
    from corsair.entrypoints.terminal import Terminal
    from corsair.evaluation.scoring import Oracle
    from corsair.settings import Settings


class CliArguments(argparse.Namespace):
    """Arguments admitted by :func:`parser` after argparse command selection."""

    command: str
    settings: str | None
    format: Literal["auto", "human", "json", "markdown"]
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
    baseline: str
    candidate: str
    allow_dataset_mismatch: bool
    case: str | None
    limit: int | None
    evidence: bool
    model: bool
    dataset_command: str
    datasets: list[str]
    fix_digests: bool
    agent_command: str
    role: Literal["producer", "auditor"]
    round: int
    previous: str | None
    feedback: tuple[str, str] | None
    review_submission: str | None
    diff: str | None
    full: bool
    structured_tools: bool | None


def validate_run_id(value: str) -> str:
    """Validate an operator-supplied Temporal identity before any service request."""
    from corsair.contracts import validate_root_identity

    return validate_root_identity(value)


def _settings(args: CliArguments) -> Settings:
    """Load settings only for commands that require local runtime configuration."""
    from corsair.settings import load_settings

    return load_settings(args.settings)


def _result_from_store(store: ArtifactStore, identity: str) -> InvestigationResult:
    """Read and validate the committed result receipt for one completed run."""
    from corsair.contracts import InvestigationResult

    ref = store.reconcile(f"result.{identity}")
    if ref is None:
        raise ValueError("No committed result; use --online to query the Temporal workflow")
    return InvestigationResult.model_validate(store.get_json(ref))


def _score_saved_result(
    store: ArtifactStore, identity: str, oracles: Mapping[str, Oracle]
) -> dict[str, object]:
    """Score one reconciled result while keeping unavailable receipts explicit."""
    from corsair.evaluation.scoring import score

    try:
        result = _result_from_store(store, identity)
        oracle = oracles[result.case_id]
        return score(result, oracle, store)
    except (OSError, ValueError, KeyError) as error:
        return {"run_id": identity, "status": "unavailable", "reason": safe_text(error)}


async def _handle_report(args: CliArguments, ui: Terminal) -> int:
    """Display a saved evaluation report and its per-case rows without runtime services."""
    from corsair.evaluation.comparison import read_report

    ui.emit(read_report(Path(args.report)))
    return 0


async def _handle_compare(args: CliArguments, ui: Terminal) -> int:
    """Compare two saved reports by case; exit 1 when the candidate regressed."""
    from corsair.evaluation.comparison import compare_reports, read_report

    diff = compare_reports(
        read_report(Path(args.baseline)),
        read_report(Path(args.candidate)),
        allow_dataset_mismatch=args.allow_dataset_mismatch,
    )
    if not diff["dataset_match"]:
        digests = diff["dataset_digest"]
        event(
            "compare.dataset_mismatch",
            level=logging.WARNING,
            message=f"baseline={digests['baseline']} candidate={digests['candidate']}",
        )
    ui.emit({"baseline_report": args.baseline, "candidate_report": args.candidate, **diff})
    return 1 if diff["regression"] else 0


async def _handle_doctor(args: CliArguments, ui: Terminal) -> int:
    """Run the read-only infrastructure diagnosis."""
    from corsair.entrypoints.diagnostics import diagnose

    message = (
        "Checking real Docker, Temporal and model provider routes"
        if args.model
        else "Checking real Docker and Temporal infrastructure"
    )
    report = await ui.wait(diagnose(_settings(args), model=args.model), message)
    ui.emit(report)
    return 0 if report["ready"] else 1


async def _handle_worker(args: CliArguments, ui: Terminal) -> int:
    """Run the Temporal worker until its local lifecycle ends."""
    from corsair.entrypoints.worker import run_worker

    await ui.wait(run_worker(_settings(args)), "Temporal worker lifecycle · Ctrl+C to stop")
    return 0


async def _handle_verify(args: CliArguments, ui: Terminal) -> int:
    """Execute one frozen native reference submission without a security verdict."""
    from corsair.adapters.sandboxing.docker import DockerSandbox
    from corsair.adapters.scm.local import prepare_case
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import EvidenceInput, Submission
    from corsair.entrypoints.requests import load_investigation_request
    from corsair.steps.evidence import run_evidence
    from corsair.steps.manifest import build_manifest

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    request = load_investigation_request(Path(args.request))
    submission = Submission.model_validate_json(Path(args.submission).read_bytes())
    identity = validate_run_id(args.run_id or f"reference-{uuid4().hex}")
    sandbox = DockerSandbox(settings, store=store)
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

    if args.evidence and args.online:
        raise ValueError("--evidence reads the artifact store; it cannot be used with --online")

    settings = _settings(args)
    if not args.online:
        from corsair.adapters.storage.filesystem import ArtifactStore

        store = ArtifactStore(settings.artifact_root)
        result = _result_from_store(store, identity)
        if args.evidence:
            from corsair.entrypoints.runs import inspect_evidence

            ui.emit(inspect_evidence(store, result))
        else:
            ui.emit(result)
        return 0

    from corsair.adapters.temporal.client import connect, wait_for_result
    from corsair.contracts import BatchItem, InvestigationResult
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
                wait_for_result(handle),
                f"{'Evaluation' if is_batch else 'Investigation'} {handle.id}",
                query=lambda: handle.query(query),
            )
        )
    else:
        ui.emit(await handle.query(query, rpc_timeout=timedelta(seconds=5)))
    return 0


async def _handle_cancel(args: CliArguments, ui: Terminal) -> int:
    """Request durable workflow cancellation without asserting cleanup completion."""
    from corsair.adapters.temporal.client import connect

    identity = validate_run_id(args.run_id or "")
    client = await ui.wait(connect(_settings(args)), "Connecting to Temporal")
    await client.get_workflow_handle(identity).cancel()
    event("cancellation.requested", run_id=identity)
    ui.emit({"run_id": identity, "state": "cancellation_requested", "cleanup_confirmed": False})
    return 0


async def _handle_investigate(args: CliArguments, ui: Terminal) -> int:
    """Submit one investigation and optionally wait for its actual result."""
    from corsair.adapters.temporal.client import connect, wait_for_result
    from corsair.entrypoints.requests import load_investigation_request
    from corsair.workflows.investigation import InvestigationWorkflow

    settings = _settings(args)
    request = load_investigation_request(Path(args.request))
    identity = validate_run_id(args.run_id or f"run-{uuid4().hex}")
    client = await ui.wait(connect(settings), "Connecting to Temporal")
    from corsair.entrypoints.api import start_investigation

    handle = await start_investigation(client, request, settings, run_id=identity)
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
        wait_for_result(handle),
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
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.adapters.temporal.client import connect, wait_for_result
    from corsair.contracts import BatchRequest, InvestigationResult, digest
    from corsair.evaluation.scoring import load_dataset, save_report, score
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
    from corsair.entrypoints.api import start_evaluation

    handle = await start_evaluation(client, batch, settings)
    event("evaluation.submitted", run_id=identity, total=len(requests) * args.repeats)
    items: list[BatchItem] = await ui.wait(
        wait_for_result(handle),
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
    report = save_report(output, rows, dataset_digest=digest(dataset))
    ui.emit({"report": str(output), "summary": report["summary"]})
    event("evaluation.completed", run_id=identity, completed=len(items), total=len(items))
    return 0 if report["summary"]["failed"] == 0 else 1


async def _handle_rescore(args: CliArguments, ui: Terminal) -> int:
    """Rescore committed evidence locally, retaining unavailable results in the report."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import digest
    from corsair.evaluation.scoring import load_dataset, save_report

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    dataset, _, oracles = load_dataset(Path(args.dataset))
    rows = [
        _score_saved_result(store, validate_run_id(identity), oracles) for identity in args.run_ids
    ]
    output = Path(args.output or ".runs/evaluations/rescored.json")
    report = save_report(output, rows, dataset_digest=digest(dataset))
    ui.emit({"report": str(output), "summary": report["summary"]})
    return 0 if report["summary"]["failed"] == 0 else 1


async def _handle_dataset(args: CliArguments, ui: Terminal) -> int:
    """Validate frozen dataset manifests offline; exit 1 on any failed entry or manifest."""
    from corsair.evaluation.datasets import validate_datasets

    settings = _settings(args) if args.settings else None
    report = validate_datasets(
        [Path(path) for path in args.datasets], settings, fix=args.fix_digests
    )
    ui.emit(report)
    return 0 if report["valid"] else 1


async def _handle_runs(args: CliArguments, ui: Terminal) -> int:
    """List committed results from the artifact store without contacting services."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.entrypoints.runs import list_runs

    store = ArtifactStore(_settings(args).artifact_root)
    ui.emit(list_runs(store, case_id=args.case, limit=args.limit))
    return 0


async def _handle_agent(args: CliArguments, ui: Terminal) -> int:
    """Render what one role would receive, without a model; optionally diff a saved preview."""
    import json

    from corsair.contracts import Feedback, Submission
    from corsair.evaluation.preview import diff_previews, load_preview, preview_request

    def submission(path: str | None) -> Submission | None:
        return None if path is None else Submission.model_validate_json(Path(path).read_bytes())

    baseline = load_preview(Path(args.diff)) if args.diff else None
    preview = await preview_request(
        args.role,
        Path(args.request),
        _settings(args),
        round_index=args.round,
        previous=submission(args.previous),
        feedback=None
        if args.feedback is None
        else Feedback(gate=args.feedback[0], reason=args.feedback[1]),
        submission=submission(args.review_submission),
        structured_tools=args.structured_tools,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n")
    shown = preview if baseline is None else diff_previews(baseline, preview)
    ui.preview(shown, full=args.full)
    return 0


type CommandHandler = Callable[[CliArguments, Terminal], Awaitable[int]]
_COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "report": _handle_report,
    "compare": _handle_compare,
    "doctor": _handle_doctor,
    "worker": _handle_worker,
    "verify": _handle_verify,
    "inspect": _handle_inspect,
    "runs": _handle_runs,
    "cancel": _handle_cancel,
    "investigate": _handle_investigate,
    "eval": _handle_eval,
    "rescore": _handle_rescore,
    "dataset": _handle_dataset,
    "agent": _handle_agent,
}


async def execute(args: argparse.Namespace, terminal: Terminal | None = None) -> int:
    """Run exactly one parser-admitted command through its explicit handler."""
    from corsair.entrypoints.terminal import Terminal

    command_args = cast(CliArguments, args)
    ui = terminal if terminal is not None else Terminal(command_args)
    handler = _COMMAND_HANDLERS.get(command_args.command)
    if handler is None:
        raise ValueError("Unknown command")
    return await handler(command_args, ui)


def positive_limit(value: str) -> int:
    """Admit a ``--limit`` of at least one row."""
    limit = int(value)
    if limit < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return limit


def positive_round(value: str) -> int:
    """Admit a producer round index of at least one."""
    index = int(value)
    if index < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return index


def gate_reason(value: str) -> tuple[str, str]:
    """Split ``GATE:REASON`` retry feedback; both halves must be present."""
    gate, separator, reason = value.partition(":")
    if not separator or not gate.strip() or not reason.strip():
        raise argparse.ArgumentTypeError("expected GATE:REASON, for example audit:wrong path")
    return gate.strip(), reason.strip()


def _presentation_options(parser: argparse.ArgumentParser, *, defaults: bool = False) -> None:
    absent = None if defaults else argparse.SUPPRESS
    parser.add_argument(
        "--settings", default=absent, help="Worker/client settings JSON; no credentials"
    )
    parser.add_argument(
        "--format",
        choices=("auto", "human", "json", "markdown"),
        default="auto" if defaults else argparse.SUPPRESS,
        help="auto: human on a terminal, JSON in pipes; markdown: report/compare records",
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
        "doctor": "Check actual Docker, namespace and worker poller readiness; "
        "--model also probes the model routes",
        "worker": "Run the native Temporal worker; Ctrl+C stops gracefully",
        "investigate": "Submit a durable investigation; use --wait for live phase updates",
        "inspect": "Read a committed result or query/watch the native Temporal workflow",
        "runs": "List committed results in the artifact store, newest first; no services",
        "cancel": "Request cancellation; this does not assert completed cleanup",
        "verify": "Execute a frozen reference submission natively; no security verdict",
        "eval": "Run frozen cases with bounded child workflows and external oracles",
        "rescore": "Revalidate saved native evidence and apply current verdict policy",
        "report": "Display an existing evaluation report and its per-case rows",
        "compare": "Compare two evaluation reports by case; exit 1 on a regression",
        "dataset": "Check frozen evaluation datasets offline; no model, target or services",
        "agent": "Inspect agent roles offline; no model provider, target or services",
    }
    commands: dict[str, argparse.ArgumentParser] = {}
    for name, description in descriptions.items():
        commands[name] = sub.add_parser(name, help=description, description=description)
        _presentation_options(commands[name])
    commands["doctor"].add_argument(
        "--model",
        action="store_true",
        help="Also send minimal requests (32-token text, one trivial tool) to each role model",
    )
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
    inspect.add_argument(
        "--evidence", action="store_true", help="Per-role native receipts; never payloads"
    )
    runs = commands["runs"]
    runs.add_argument("--case", help="Only results for this case id")
    runs.add_argument("--limit", type=positive_limit, help="At most N rows")
    commands["cancel"].add_argument("run_id")
    verify = commands["verify"]
    verify.add_argument("request")
    verify.add_argument("submission")
    verify.add_argument("--run-id")
    verify.add_argument("--fixed", action="store_true")
    evaluation = commands["eval"]
    evaluation.add_argument("dataset")
    evaluation.add_argument("--run-id")
    evaluation.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    evaluation.add_argument("--concurrency", type=int, choices=range(1, 9), default=2)
    evaluation.add_argument("--output")
    rescore = commands["rescore"]
    rescore.add_argument("dataset")
    rescore.add_argument("run_ids", nargs="+")
    rescore.add_argument("--output", default=".runs/evaluations/rescored.json")
    commands["report"].add_argument("report")
    compare = commands["compare"]
    compare.add_argument("baseline", help="Baseline evaluation report JSON")
    compare.add_argument("candidate", help="Candidate evaluation report JSON")
    compare.add_argument(
        "--allow-dataset-mismatch",
        action="store_true",
        help="Compare reports over different or undeclared frozen dataset digests",
    )
    datasets = commands["dataset"].add_subparsers(
        dest="dataset_command", required=True, title="dataset commands"
    )
    validate_help = "Verify digests, requests, sources, target binding and oracle consistency"
    validate = datasets.add_parser("validate", help=validate_help, description=validate_help)
    _presentation_options(validate)
    validate.add_argument("datasets", nargs="+", metavar="DATASET", help="Dataset manifest JSON")
    validate.add_argument(
        "--fix-digests",
        action="store_true",
        help="Rewrite only stale manifest digests of otherwise valid entries",
    )
    agents = commands["agent"].add_subparsers(
        dest="agent_command", required=True, title="agent commands"
    )
    preview_help = (
        "Render the system instruction, tool declarations and packet a role would receive, "
        "with byte and approximate token counts; no model is called"
    )
    preview = agents.add_parser("preview", help=preview_help, description=preview_help)
    _presentation_options(preview)
    preview.add_argument("role", choices=("producer", "auditor"))
    preview.add_argument("request", help="Case request JSON; source paths relative to this file")
    preview.add_argument(
        "--submission",
        dest="review_submission",
        metavar="FILE",
        help="Submission JSON the auditor reviews (auditor only)",
    )
    preview.add_argument(
        "--round", type=positive_round, default=1, help="Producer round index (default 1)"
    )
    preview.add_argument(
        "--previous", metavar="FILE", help="Previous-round Submission JSON (producer, round > 1)"
    )
    preview.add_argument(
        "--feedback",
        type=gate_reason,
        metavar="GATE:REASON",
        help="Retry feedback the producer receives (round > 1), e.g. audit:REASON",
    )
    preview.add_argument(
        "--structured-tools",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Force the native response-schema route (or, with --no-, the set_model_response "
        "tool); default: what the configured model route reports",
    )
    preview.add_argument("--output", metavar="FILE", help="Also save the JSON preview here")
    preview.add_argument(
        "--diff", metavar="PREVIEW.json", help="Compare against a saved preview, part by part"
    )
    preview.add_argument(
        "--full", action="store_true", help="Human output: print every part (or diff) in full"
    )
    return root


def main() -> None:
    args = cast(CliArguments, parser().parse_args())
    from corsair.entrypoints.terminal import Terminal

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
        terminal.report_failure(error)
        code = 2
    # Exit after the handler: retaining exception tracebacks can retain native SDK clients.
    raise SystemExit(code)


if __name__ == "__main__":
    main()
