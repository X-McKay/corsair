"""Finite commands; production investigations always go through Temporal.

Module scope imports only the standard library and the sanitized logger, so ``--help``,
``--version`` and argument errors exit before Rich, Pydantic contracts, the scorer or any SDK
loads. Each handler imports what its command uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

from corsair.observability.logging import configure_logging, event, safe_text

if TYPE_CHECKING:
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import BatchItem, InvestigationResult, Oracle
    from corsair.entrypoints.gym import GymRun
    from corsair.entrypoints.terminal import Terminal
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
    families: bool
    family_dataset: str | None
    case: str | None
    limit: int | None
    evidence: bool
    explain: bool
    model: bool
    source_root: str
    recipe_template: str | None
    dataset_command: str
    datasets: list[str]
    agent_command: str
    role: Literal["producer", "auditor"]
    round: int
    previous: str | None
    feedback: tuple[str, str] | None
    review_submission: str | None
    diff: str | None
    full: bool
    structured_tools: bool | None
    gym_command: str
    ledger_command: str
    tier: str
    cases: list[str] | None
    languages: list[str] | None
    temporal_address: str | None
    budgets: str | None
    out: str | None
    run_dir: str
    references: list[str] | None
    runs: list[str]
    source: str
    scorecard: str
    row_id: str
    wave: int
    entry: Literal["baseline", "experiment"]
    track: str | None
    idea: str | None
    lesson: str
    ledger: str
    ledger_markdown: str
    ledger_baseline: str | None
    gym_dataset: str | None
    gym_root: str | None
    runs_tier: str | None
    reference: str | None
    skip_tier1: bool


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


def _existing_store(settings: Settings) -> ArtifactStore | None:
    """The local artifact store only when it already exists, so opening creates nothing."""
    from corsair.adapters.storage.filesystem import ArtifactStore

    root = Path(settings.artifact_root)
    if not ((root / "blobs").is_dir() and (root / "operations").is_dir()):
        return None
    return ArtifactStore(root)


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


def _family_report(args: CliArguments, path: str) -> dict[str, Any]:
    """Read one saved report, labelling its rows from ``--dataset`` when given."""
    from corsair.evaluation.comparison import read_report

    report = read_report(Path(path))
    if args.family_dataset is not None:
        from corsair.evaluation.families import label_report

        report = label_report(report, Path(args.family_dataset))
    return report


async def _handle_report(args: CliArguments, ui: Terminal) -> int:
    """Display a saved evaluation report and its per-case rows without runtime services."""
    report = _family_report(args, args.report)
    if args.families:
        from corsair.evaluation.families import family_view

        report = {**report, **family_view(report.get("rows", []))}
    ui.emit(report)
    return 0


async def _handle_compare(args: CliArguments, ui: Terminal) -> int:
    """Compare two saved reports by case; exit 1 when the candidate regressed and 2 when the
    reports cover different dataset digests, which is no comparison either way."""
    from corsair.evaluation.comparison import compare_reports

    baseline, candidate = _family_report(args, args.baseline), _family_report(args, args.candidate)
    diff = compare_reports(baseline, candidate, allow_dataset_mismatch=args.allow_dataset_mismatch)
    if not diff["dataset_match"]:
        digests = diff["dataset_digest"]
        event(
            "compare.dataset_mismatch",
            level=logging.WARNING,
            message=f"baseline={digests['baseline']} candidate={digests['candidate']}",
        )
    if args.families:
        from corsair.evaluation.families import family_deltas

        diff["families"] = family_deltas(baseline["rows"], candidate["rows"], diff["regressions"])
    ui.emit({"baseline_report": args.baseline, "candidate_report": args.candidate, **diff})
    if not diff["comparable"]:
        return 2
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
        asyncio.to_thread(sandbox.image_id_for, request.case.recipe.kind),
        "Resolving native Docker image",
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
    if args.explain and args.online:
        raise ValueError("--explain reads the artifact store; it cannot be used with --online")
    if args.explain and args.evidence:
        raise ValueError("--explain and --evidence are separate views; choose one")

    settings = _settings(args)
    if not args.online:
        from corsair.adapters.storage.filesystem import ArtifactStore

        store = ArtifactStore(settings.artifact_root)
        result = _result_from_store(store, identity)
        if args.evidence:
            from corsair.entrypoints.runs import inspect_evidence

            ui.emit(inspect_evidence(store, result))
        elif args.explain:
            from corsair.entrypoints.runs import explain_run

            ui.emit({"result": result, **explain_run(store, result)}, store=store)
        else:
            ui.emit(result, store=store)
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


async def _handle_explain(args: CliArguments, ui: Terminal) -> int:
    """Explain a committed result's verdict from the artifact store; no services."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.entrypoints.runs import explain_run

    identity = validate_run_id(args.run_id or "")
    store = ArtifactStore(_settings(args).artifact_root)
    ui.emit(explain_run(store, _result_from_store(store, identity)))
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
    # A worker sharing this host's artifact root lets the human view verify the ledger.
    ui.emit(result, store=_existing_store(settings) if ui.human else None)
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
    from corsair.contracts import BatchRequest, digest
    from corsair.evaluation.datasets import load_dataset
    from corsair.evaluation.families import label_rows
    from corsair.evaluation.scoring import save_report, score_batch
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
    rows = score_batch(items, store, oracles)
    output = Path(args.output or f".runs/evaluations/{identity}.json")
    report = save_report(output, label_rows(rows, dataset), dataset_digest=digest(dataset))
    ui.emit({"report": str(output), "summary": report["summary"]})
    event("evaluation.completed", run_id=identity, completed=len(items), total=len(items))
    return 0 if report["summary"]["failed"] == 0 else 1


async def _handle_rescore(args: CliArguments, ui: Terminal) -> int:
    """Rescore committed evidence locally, retaining unavailable results in the report."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import digest
    from corsair.evaluation.datasets import load_dataset
    from corsair.evaluation.families import label_rows
    from corsair.evaluation.scoring import save_report

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    dataset, _, oracles = load_dataset(Path(args.dataset))
    rows = [
        _score_saved_result(store, validate_run_id(identity), oracles) for identity in args.run_ids
    ]
    output = Path(args.output or ".runs/evaluations/rescored.json")
    report = save_report(output, label_rows(rows, dataset), dataset_digest=digest(dataset))
    ui.emit({"report": str(output), "summary": report["summary"]})
    return 0 if report["summary"]["failed"] == 0 else 1


async def _handle_intake(args: CliArguments, ui: Terminal) -> int:
    """Dry-run scanner intake: which findings would become admissible requests, and why not."""
    from corsair.evaluation.intake import intake_receipt

    template = Path(args.recipe_template) if args.recipe_template else None
    receipt, intakes = intake_receipt(
        Path(args.report), Path(args.source_root), _settings(args), template
    )
    ui.emit(receipt)
    return 0 if intakes and all(item.admissible for item in intakes) else 1


def _dataset_report(args: CliArguments, *, fix: bool) -> dict[str, Any]:
    from corsair.evaluation.datasets import validate_datasets

    settings = _settings(args) if args.settings else None
    return validate_datasets([Path(path) for path in args.datasets], settings, fix=fix)


async def _handle_dataset_validate(args: CliArguments, ui: Terminal) -> int:
    """Validate frozen dataset manifests offline, never writing; exit 1 on any failure."""
    report = _dataset_report(args, fix=False)
    ui.emit(report)
    return 0 if report["valid"] else 1


async def _handle_dataset_refreeze(args: CliArguments, ui: Terminal) -> int:
    """Rewrite stale manifest digests of otherwise valid entries; exit 1 whenever it wrote,
    because a new dataset digest is a new frozen cohort that a human must review."""
    report = _dataset_report(args, fix=True)
    ui.emit(report)
    if report["rewritten"]:
        changed = [
            f"{item['dataset_digest_change']['old']} -> {item['dataset_digest_change']['new']}"
            for item in report["datasets"]
            if item["dataset_digest_change"] is not None
        ]
        event(
            "dataset.refrozen",
            level=logging.WARNING,
            message="digests rewritten; review the diff and commit; dataset digest "
            + "; ".join(changed),
        )
        return 1
    return 0 if report["valid"] else 1


async def _handle_replay_candidates(args: CliArguments, ui: Terminal) -> int:
    """Replay mismatching isolated producer proposals natively; never edits an oracle."""
    from corsair.adapters.sandboxing.docker import DockerSandbox
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.evaluation.comparison import read_report
    from corsair.evaluation.replay import replay_candidates

    settings = _settings(args)
    store = ArtifactStore(settings.artifact_root)
    report = read_report(Path(args.report))
    identity = validate_run_id(args.run_id or f"replay-{uuid4().hex}")
    replayed = await ui.wait(
        replay_candidates(
            report,
            Path(args.dataset),
            settings,
            store,
            DockerSandbox(settings, store=store),
            replay_id=identity,
        ),
        "Replaying mismatching producer proposals natively · evidence only, no oracle change",
    )
    output = Path(args.output or f".runs/evaluations/{identity}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(replayed, indent=2) + "\n")
    counts = replayed["summary"]["replay"]
    event("replay.completed", run_id=identity, completed=sum(counts.values()))
    ui.emit({**replayed, "report": str(output)})
    return 1 if counts["unavailable"] else 0


async def _handle_dataset(args: CliArguments, ui: Terminal) -> int:
    """Dispatch one ``corsair dataset`` subcommand."""
    if args.dataset_command == "validate":
        return await _handle_dataset_validate(args, ui)
    if args.dataset_command == "refreeze":
        return await _handle_dataset_refreeze(args, ui)
    if args.dataset_command == "replay-candidates":
        return await _handle_replay_candidates(args, ui)
    raise ValueError("Unknown dataset command")


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


GYM_LEDGER = "evals/experiments/ledger.jsonl"
GYM_LEDGER_MARKDOWN = "evals/experiments/LEDGER.md"


def _gym_settings(args: CliArguments) -> Settings:
    """``--settings``, else the checkout's live ``.state/settings.json``, else the defaults."""
    from corsair.entrypoints.gym import checkout_root, default_settings_path
    from corsair.settings import load_settings

    return load_settings(args.settings or default_settings_path(checkout_root()))


def _gym_store(args: CliArguments, run_dir: Path) -> ArtifactStore:
    """The store a gym run wrote to (its run.json), else the configured or shared store."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.entrypoints.gym import run_store

    return ArtifactStore(run_store(run_dir, None, _gym_settings(args)))


def _emit_view(ui: Terminal, text: str, value: object) -> None:
    """Human and Markdown output print the code-owned Markdown view; JSON gets the record."""
    if ui.human or ui.markdown:
        sys.stdout.write(text)
    else:
        ui.emit(value)


async def _handle_gym_run(args: CliArguments, ui: Terminal) -> int:
    """Run one tier on an in-process worker in the gym namespace; write and show its scorecard."""
    from corsair.entrypoints.gym import (
        GymOptions,
        checkout_root,
        resolve_tier,
        run_gym,
        safe_invocation,
    )

    root = checkout_root()
    options = GymOptions(
        dataset=resolve_tier(args.tier, root),
        settings=_gym_settings(args),
        repeats=args.repeats,
        concurrency=args.concurrency,
        temporal_address=args.temporal_address,
        cases=tuple(args.cases or ()),
        languages=tuple(
            language.strip()
            for value in args.languages or ()
            for language in value.split(",")
            if language.strip()
        ),
        budgets=Path(args.budgets) if args.budgets else None,
        out=Path(args.out) if args.out else None,
        run_id=validate_run_id(args.run_id) if args.run_id else None,
        invocation=safe_invocation(sys.argv),
    )
    run = await run_gym(options, root=root, observe=_gym_observer(ui))
    _emit_view(ui, "\n".join(_gym_run_lines(run)), _gym_run_record(run))
    unavailable = sum(item.status == "unavailable" for item in run.trajectories)
    return 1 if unavailable else 0


def _gym_observer(ui: Terminal) -> Callable[[Any], Awaitable[list[BatchItem]]]:
    """Wait for the batch with the terminal's progress view of the workflow status."""

    async def observe(handle: Any) -> list[BatchItem]:
        from corsair.adapters.temporal.client import wait_for_result
        from corsair.workflows.evaluation import EvaluationWorkflow

        return await ui.wait(
            wait_for_result(handle),
            f"Gym {handle.id}",
            query=lambda: handle.query(EvaluationWorkflow.status),
        )

    return observe


def _gym_run_lines(run: GymRun) -> list[str]:
    from corsair.entrypoints.gym import read_run_record
    from corsair.evaluation.gym.render import render_scorecard

    card = run.scorecard
    return [
        render_scorecard(card),
        f"- Run directory: `{run.run_dir}`",
        f"- Store: `{read_run_record(run.run_dir).get('store', 'unknown')}`",
        f"- Temporal: {'ephemeral' if run.ephemeral else 'existing'} `{run.temporal_address}`, "
        f"namespace `{card.run.temporal_namespace}`, task queue `{card.run.task_queue}`",
        f"- Commit: `{card.run.git_branch}` `{card.run.git_commit}`",
        *(f"- Image `{ref}`: `{image_id}`" for ref, image_id in card.run.image_ids.items()),
        f"- Wall seconds: {run.wall_seconds:.1f}",
        "",
    ]


def _gym_run_record(run: GymRun) -> dict[str, object]:
    return {
        "run_dir": str(run.run_dir),
        "temporal_address": run.temporal_address,
        "ephemeral": run.ephemeral,
        "wall_seconds": run.wall_seconds,
        "scorecard": run.scorecard,
    }


async def _handle_gym_score(args: CliArguments, ui: Terminal) -> int:
    """Score a saved report into trajectories and a scorecard; no services."""
    from corsair.contracts import RunContext
    from corsair.evaluation.comparison import read_report
    from corsair.evaluation.gym.budgets import load_budgets
    from corsair.evaluation.gym.render import render_scorecard
    from corsair.evaluation.gym.scoring import (
        SCORECARD_FILE,
        TRAJECTORIES_FILE,
        load_results,
        read_scorecard,
        score_report,
        write_scorecard,
        write_trajectories,
    )

    report_path = Path(args.report)
    report = read_report(report_path)
    out = Path(args.out) if args.out else report_path.parent
    previous = out / SCORECARD_FILE
    run = (
        read_scorecard(previous).run
        if previous.exists()
        else RunContext(run_id=validate_run_id(report_path.stem))
    )
    store = _gym_store(args, report_path.parent)
    run_ids = [str(row.get("run_id")) for row in report.get("rows", [])]
    trajectories, card = score_report(
        report,
        Path(args.dataset),
        load_results(store, run_ids),
        run=run,
        budgets=load_budgets(Path(args.budgets)) if args.budgets else None,
    )
    write_trajectories(out / TRAJECTORIES_FILE, trajectories)
    write_scorecard(out / SCORECARD_FILE, card)
    _emit_view(ui, render_scorecard(card) + f"\n- Written to `{out}`\n", card)
    return 0


async def _handle_gym_gate(args: CliArguments, ui: Terminal) -> int:
    """Gate a candidate scorecard: exit 0 accepted, 1 rejected, 2 incomparable."""
    from corsair.evaluation.gym.gate import gate
    from corsair.evaluation.gym.render import render_gate
    from corsair.evaluation.gym.scoring import read_scorecard

    baseline, candidate = read_scorecard(Path(args.baseline)), read_scorecard(Path(args.candidate))
    verdict = gate(baseline, candidate)
    _emit_view(ui, render_gate(verdict, baseline, candidate), verdict)
    return verdict.exit_code


async def _handle_gym_replay(args: CliArguments, ui: Terminal) -> int:
    """Show one case's rounds, per-call usage and failure stop from a gym run; no services."""
    from corsair.entrypoints.gym import render_replay, replay_case

    run_dir = Path(args.run_dir)
    view = replay_case(run_dir, args.case or "", _gym_store(args, run_dir))
    _emit_view(ui, render_replay(view), view)
    return 0


async def _handle_gym_capture(args: CliArguments, ui: Terminal) -> int:
    """Freeze a case's failed repeats as agent fixtures and kernel replay cases."""
    from corsair.entrypoints.gym import checkout_root, dataset_for_report
    from corsair.evaluation.gym.capture import capture
    from corsair.evaluation.gym.scoring import REPORT_FILE

    root = checkout_root()
    run_dir = Path(args.run_dir)
    dataset = (
        Path(args.gym_dataset)
        if args.gym_dataset
        else dataset_for_report(run_dir / REPORT_FILE, root)
    )
    captured = capture(
        run_dir,
        args.case or "",
        dataset_path=dataset,
        store=_gym_store(args, run_dir),
        out_root=root / "evals",
        kernel_dir=root / "tests/replay/kernel",
        references=[Path(path) for path in args.references or ()],
    )
    ui.emit(captured)
    return 0


async def _handle_gym_export(args: CliArguments, ui: Terminal) -> int:
    """Write grouped rewards and advantages from run directories for later training."""
    from corsair.evaluation.gym.export import export_groups

    count = export_groups([Path(path) for path in args.runs], Path(args.out or ""))
    ui.emit({"export": args.out, "records": count})
    return 0


async def _handle_gym_budgets(args: CliArguments, ui: Terminal) -> int:
    """Derive per-kind budgets from a scorecard's p95 values and write them with their digest."""
    from corsair.evaluation.gym.budgets import derive_budgets, write_budgets
    from corsair.evaluation.gym.scoring import read_scorecard

    budgets = derive_budgets(read_scorecard(Path(args.source)))
    ui.emit({"budgets": args.out, "digest": write_budgets(Path(args.out or ""), budgets)})
    return 0


async def _handle_gym_ledger(args: CliArguments, ui: Terminal) -> int:
    """Append one ledger row from a scorecard, or render LEDGER.md from the JSONL ledger."""
    from corsair.evaluation.gym.ledger import append_ledger, build_ledger_row, render_ledger_file
    from corsair.evaluation.gym.scoring import read_scorecard

    if args.ledger_command == "render":
        render_ledger_file(Path(args.ledger), Path(args.ledger_markdown))
        ui.emit({"ledger": args.ledger, "markdown": args.ledger_markdown})
        return 0
    from datetime import date

    from corsair.evaluation.gym.gate import gate

    candidate = read_scorecard(Path(args.scorecard))
    verdict = (
        None
        if args.ledger_baseline is None
        else gate(read_scorecard(Path(args.ledger_baseline)), candidate)
    )
    row = build_ledger_row(
        candidate,
        row_id=args.row_id,
        recorded_on=date.today(),
        wave=args.wave,
        entry=args.entry,
        tier=args.tier,
        track=args.track,
        idea=args.idea,
        gate=verdict,
        lesson=args.lesson,
        scorecard_path=args.scorecard,
    )
    append_ledger(Path(args.ledger), row)
    ui.emit(row)
    return 0


async def _handle_gym_runs(args: CliArguments, ui: Terminal) -> int:
    """List stored runs, newest first, from the shared gym root (or ``--root``)."""
    from corsair.entrypoints.gym import gym_paths, list_runs
    from corsair.evaluation.gym.render import render_runs

    root = Path(args.gym_root) if args.gym_root else gym_paths(None, _gym_settings(args)).root
    rows = list_runs(root, tier=args.runs_tier, limit=args.limit)
    _emit_view(ui, f"## Gym runs under `{root}`\n\n" + render_runs(rows), rows)
    return 0


_SKIPPED_TEXT = {
    "skipped_by_request": "was skipped on request (--skip-tier1); this is not an acceptance.",
    "rejected_at_tier0": "was not run because tier0 was REJECTED.",
}


async def _handle_gym_verify(args: CliArguments, ui: Terminal) -> int:
    """tier0 run and gate, then tier1 run and gate unless rejected; exit 0, 1 or 2."""
    from corsair.entrypoints.gym import (
        VERIFY_TIERS,
        GymOptions,
        TierGate,
        checkout_root,
        gym_paths,
        resolve_tier,
        safe_invocation,
        verify_candidate,
    )
    from corsair.evaluation.gym.render import render_gate

    root = checkout_root()
    settings = _gym_settings(args)
    reference = Path(args.reference) if args.reference else gym_paths(root, settings).reference
    if not reference.is_dir():
        raise ValueError(f"no reference directory {reference}; pass --reference DIR")
    tiers = {name: resolve_tier(name, root) for name in VERIFY_TIERS}
    options = GymOptions(
        dataset=tiers["tier0"],
        settings=settings,
        repeats=args.repeats,
        concurrency=args.concurrency,
        temporal_address=args.temporal_address,
        budgets=Path(args.budgets) if args.budgets else None,
        invocation=safe_invocation(sys.argv),
    )
    human = ui.human or ui.markdown

    def show(item: TierGate) -> None:
        if human:
            sys.stdout.write(
                f"### {item.tier}\n\n- Run directory: `{item.run.run_dir}`\n"
                f"- Reference: `{item.reference}`\n\n"
                + render_gate(item.verdict, item.baseline, item.run.scorecard)
                + "\n"
            )
            sys.stdout.flush()

    result = await verify_candidate(
        options,
        reference,
        root=root,
        tiers=tiers,
        skip=("tier1",) if args.skip_tier1 else (),
        observe=_gym_observer(ui),
        on_gate=show,
    )
    if human:
        lines = [f"- {tier} {_SKIPPED_TEXT[reason]}" for tier, reason in result.skipped.items()]
        lines += [
            f"- Verdict record: `{result.verdict_path}`",
            "",
            f"VERDICT: {result.decision.value}",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
    else:
        ui.emit({"verdict": str(result.verdict_path), **_read_json(result.verdict_path)})
    return {"ACCEPTED": 0, "REJECTED": 1}.get(result.decision.value, 2)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


async def _handle_gym_images(args: CliArguments, ui: Terminal) -> int:
    """Build the content-addressed trusted images of this checkout; print tags and ids."""
    from corsair.entrypoints.gym import build_gym_images, checkout_root

    ids = await asyncio.to_thread(build_gym_images, checkout_root(), _gym_settings(args))
    ui.emit({"images": ids})
    return 0


_GYM_HANDLERS: dict[str, Callable[[CliArguments, Terminal], Awaitable[int]]] = {
    "run": _handle_gym_run,
    "score": _handle_gym_score,
    "gate": _handle_gym_gate,
    "replay": _handle_gym_replay,
    "capture": _handle_gym_capture,
    "export-grpo": _handle_gym_export,
    "budgets": _handle_gym_budgets,
    "ledger": _handle_gym_ledger,
    "images": _handle_gym_images,
    "runs": _handle_gym_runs,
    "verify": _handle_gym_verify,
}


async def _handle_gym(args: CliArguments, ui: Terminal) -> int:
    """Dispatch one ``corsair gym`` subcommand."""
    handler = _GYM_HANDLERS.get(args.gym_command)
    if handler is None:
        raise ValueError("Unknown gym command")
    return await handler(args, ui)


type CommandHandler = Callable[[CliArguments, Terminal], Awaitable[int]]
_COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "report": _handle_report,
    "compare": _handle_compare,
    "doctor": _handle_doctor,
    "worker": _handle_worker,
    "verify": _handle_verify,
    "inspect": _handle_inspect,
    "runs": _handle_runs,
    "explain": _handle_explain,
    "cancel": _handle_cancel,
    "investigate": _handle_investigate,
    "eval": _handle_eval,
    "rescore": _handle_rescore,
    "intake": _handle_intake,
    "dataset": _handle_dataset,
    "agent": _handle_agent,
    "gym": _handle_gym,
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
        "explain": "Explain a committed verdict in plain language and what would change it; "
        "no services",
        "cancel": "Request cancellation; this does not assert completed cleanup",
        "verify": "Execute a frozen reference submission natively; no security verdict",
        "eval": "Run frozen cases with bounded child workflows and external oracles",
        "rescore": "Revalidate saved native evidence and apply current verdict policy",
        "report": "Display an existing evaluation report and its per-case rows",
        "compare": (
            "Compare two evaluation reports by case; exit 1 on a regression, 2 when incomparable"
        ),
        "intake": "Dry-run a scanner report: which findings become admissible requests; "
        "no model or container",
        "dataset": (
            "Frozen dataset tools: validate offline; refreeze stale digests; "
            "replay-candidates natively in Docker"
        ),
        "agent": "Inspect agent roles offline; no model provider, target or services",
        "gym": "Evaluation gym: run a frozen tier in the corsair-gym namespace, score, gate, "
        "replay, capture, export and record",
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
    inspect.add_argument(
        "--explain",
        action="store_true",
        help="Add the plain-language verdict explanation; never model text",
    )
    runs = commands["runs"]
    runs.add_argument("--case", help="Only results for this case id")
    runs.add_argument("--limit", type=positive_limit, help="At most N rows")
    commands["explain"].add_argument("run_id")
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
    intake = commands["intake"]
    intake.add_argument("report", help="Scanner report JSON (corsair.scan_report/1)")
    intake.add_argument(
        "--source-root",
        required=True,
        help="The findings' source tree (a request's source.path), admitted under source_root",
    )
    intake.add_argument(
        "--recipe-template",
        help="Operator recipe JSON without module_file; intake binds it to each finding's file",
    )
    datasets = commands["dataset"].add_subparsers(
        dest="dataset_command", required=True, title="dataset commands"
    )
    validate_help = "Verify digests, requests, sources, target binding and oracle consistency"
    validate = datasets.add_parser("validate", help=validate_help, description=validate_help)
    _presentation_options(validate)
    validate.add_argument("datasets", nargs="+", metavar="DATASET", help="Dataset manifest JSON")
    refreeze_help = (
        "Rewrite only stale manifest digests of otherwise valid entries; exit 1 when it "
        "wrote, since the new dataset digest needs review"
    )
    refreeze = datasets.add_parser("refreeze", help=refreeze_help, description=refreeze_help)
    _presentation_options(refreeze)
    refreeze.add_argument("datasets", nargs="+", metavar="DATASET", help="Dataset manifest JSON")
    replay_help = (
        "Replay a producer report's mismatching proposals in the real sandbox; "
        "evidence for a human oracle decision, pass/fail unchanged"
    )
    replay = datasets.add_parser("replay-candidates", help=replay_help, description=replay_help)
    _presentation_options(replay)
    replay.add_argument("report", help="Isolated producer evaluation report JSON")
    replay.add_argument("dataset", help="The frozen agent dataset the report was run on")
    replay.add_argument("--run-id", help="Replay identity; operation ids are RUN_ID.c<row>")
    replay.add_argument("--output", help="Replay report path (default .runs/evaluations/)")
    for name in ("report", "compare"):
        commands[name].add_argument(
            "--families",
            action="store_true",
            help="Add per-family and per-split pass, decisive and forbidden-label summaries",
        )
        commands[name].add_argument(
            "--dataset",
            dest="family_dataset",
            help="Label rows of an older report from the manifest it was scored against",
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
    _gym_parsers(commands["gym"])
    return root


def _gym_parsers(gym: argparse.ArgumentParser) -> None:
    """``corsair gym`` subcommands; each prints code-owned text or a JSON record."""
    commands = gym.add_subparsers(dest="gym_command", required=True, title="gym commands")

    def command(name: str, description: str) -> argparse.ArgumentParser:
        parsed = commands.add_parser(name, help=description, description=description)
        _presentation_options(parsed)
        return parsed

    run = command(
        "run",
        "Run a tier through an in-process production worker on a per-branch queue in the "
        "corsair-gym namespace (ephemeral server unless --temporal-address); writes report, "
        "trajectories and scorecard",
    )
    run.add_argument("tier", help="Tier name (tier0 -> evals/datasets/gym-tier0.json) or a path")
    run.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    run.add_argument("--concurrency", type=int, choices=range(1, 9), default=2)
    run.add_argument(
        "--temporal-address", help="Existing server; it must already have namespace corsair-gym"
    )
    run.add_argument(
        "--case", dest="cases", action="append", help="Only this case (repeatable); sliced run"
    )
    run.add_argument(
        "--lang", dest="languages", action="append", help="Only these languages, e.g. python,c"
    )
    run.add_argument(
        "--budgets", help="Budgets file (default evals/experiments/budgets.json when present)"
    )
    run.add_argument("--out", help="Run directory (default <shared gym root>/runs/<run-id>)")
    run.add_argument("--run-id", help="Batch identity (default gym-<tier>-<time>-<hex>)")
    score_cmd = command("score", "Score a saved report into trajectories and a scorecard")
    score_cmd.add_argument("report", help="Composed evaluation report JSON")
    score_cmd.add_argument("--dataset", required=True, help="The manifest it was scored against")
    score_cmd.add_argument("--out", help="Directory for the files (default: the report's)")
    score_cmd.add_argument("--budgets", help="Budgets file for the efficiency bonus")
    gate_cmd = command(
        "gate", "Gate a candidate scorecard: exit 0 accepted, 1 rejected, 2 incomparable"
    )
    gate_cmd.add_argument("--baseline", required=True, metavar="SCORECARD")
    gate_cmd.add_argument("--candidate", required=True, metavar="SCORECARD")
    replay_cmd = command(
        "replay", "One case's round timeline, per-call usage and failure stop; no services"
    )
    replay_cmd.add_argument("run_dir", metavar="RUN-DIR")
    replay_cmd.add_argument("--case", required=True)
    capture_cmd = command(
        "capture", "Freeze a case's failed repeats as evals/ fixtures and tests/replay/kernel cases"
    )
    capture_cmd.add_argument("run_dir", metavar="RUN-DIR")
    capture_cmd.add_argument("--case", required=True)
    capture_cmd.add_argument(
        "--reference",
        dest="references",
        action="append",
        metavar="RUN-DIR",
        help="Another run over the same dataset that may supply demonstrated payloads",
    )
    capture_cmd.add_argument(
        "--dataset", dest="gym_dataset", help="Manifest (default: found by the report's digest)"
    )
    export = command("export-grpo", "Grouped rewards and advantages across runs, as JSONL")
    export.add_argument("--runs", nargs="+", required=True, metavar="RUN-DIR")
    export.add_argument("--out", required=True, metavar="FILE")
    budgets = command("budgets", "Write per-kind budgets from a scorecard's p95 values")
    budgets.add_argument("--from", dest="source", required=True, metavar="SCORECARD")
    budgets.add_argument("--out", required=True, metavar="FILE")
    command("images", "Build this checkout's content-addressed images; print tags and ids")
    runs_cmd = command("runs", "List stored gym runs, newest first, with their headline figures")
    runs_cmd.add_argument(
        "--root",
        dest="gym_root",
        help="Gym root holding runs/ (default <main checkout>/.runs/gym, shared by worktrees)",
    )
    runs_cmd.add_argument("--tier", dest="runs_tier", help="Only runs of this tier")
    runs_cmd.add_argument("--limit", type=positive_limit, help="At most this many runs")
    verify = command(
        "verify",
        "The candidate protocol: tier0 run and gate, then tier1 run and gate unless tier0 was "
        "rejected; exit 0 accepted, 1 rejected, 2 incomparable",
    )
    verify.add_argument(
        "--reference",
        help="Directory with tier0.json and tier1.json (default <shared gym root>/reference)",
    )
    verify.add_argument("--repeats", type=int, choices=range(1, 9), default=3)
    verify.add_argument("--concurrency", type=int, choices=range(1, 9), default=2)
    verify.add_argument(
        "--skip-tier1", action="store_true", help="Stop after tier0 (a smoke result only)"
    )
    verify.add_argument(
        "--temporal-address", help="Existing server; it must already have namespace corsair-gym"
    )
    verify.add_argument(
        "--budgets", help="Budgets file (default evals/experiments/budgets.json when present)"
    )
    ledger = command("ledger", "Append to or render the experiment ledger")
    ledger_commands = ledger.add_subparsers(
        dest="ledger_command", required=True, title="ledger commands"
    )
    append_help = "Append one row from a scorecard (gated when --baseline is given)"
    append = ledger_commands.add_parser("append", help=append_help, description=append_help)
    _presentation_options(append)
    append.add_argument("--scorecard", required=True)
    append.add_argument("--id", dest="row_id", required=True)
    append.add_argument("--entry", choices=("baseline", "experiment"), required=True)
    append.add_argument("--tier", required=True)
    append.add_argument("--wave", type=int, default=0)
    append.add_argument("--track")
    append.add_argument("--idea")
    append.add_argument("--baseline", dest="ledger_baseline", metavar="SCORECARD")
    append.add_argument("--lesson", default="")
    append.add_argument("--ledger", default=GYM_LEDGER)
    render_help = "Regenerate LEDGER.md's tables from the JSONL ledger"
    render = ledger_commands.add_parser("render", help=render_help, description=render_help)
    _presentation_options(render)
    render.add_argument("--ledger", default=GYM_LEDGER)
    render.add_argument("--markdown", dest="ledger_markdown", default=GYM_LEDGER_MARKDOWN)


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
