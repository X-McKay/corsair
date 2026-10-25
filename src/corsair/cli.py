"""Finite commands; production investigations always go through Temporal."""

import argparse
import asyncio
import json
import sys
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
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import load_settings


def emit(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, ensure_ascii=False))


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


async def execute(args) -> int:
    settings = load_settings(args.settings)
    store = ArtifactStore(settings.artifact_root)
    if args.command == "worker":
        from corsair.runtime.worker import run_worker

        await run_worker(settings)
        return 0
    if args.command == "verify":
        from corsair.runtime.manifest import build_manifest
        from corsair.tools.security.evidence import EvidenceVerifier
        from corsair.tools.security.sandbox import DockerSandbox
        from corsair.tools.security.sources import prepare_case

        request = request_from_file(Path(args.request))
        submission = Submission.model_validate_json(Path(args.submission).read_bytes())
        identity = run_id(args.run_id or f"reference-{uuid4().hex}")
        image_id = await asyncio.to_thread(lambda: DockerSandbox(settings).image_id)
        prepared = await asyncio.to_thread(
            prepare_case,
            request.case,
            settings,
            store,
            build_manifest(request, settings, image_id),
        )
        observation = await asyncio.to_thread(
            EvidenceVerifier(settings, store).evaluate,
            EvidenceInput(
                run_id=identity,
                operation_id=f"{identity}.reference",
                prepared=prepared,
                submission=submission,
                budget=request.budget,
                fixed=args.fixed,
            ),
        )
        # Local reference replay returns observations, never a release-facing disposition.
        emit(observation)
        healthy = (
            observation.feedback is None
            and observation.cleanup_confirmed
            and observation.control is not None
            and observation.adversarial is not None
            and observation.control.outcome.value == "PROPERTY_HELD"
            and observation.adversarial.outcome.value in {"PROPERTY_HELD", "VIOLATION"}
        )
        return 0 if healthy else 1
    if args.command == "inspect" and not args.online:
        ref = store.reconcile(f"result.{args.run_id}")
        if ref is None:
            raise ValueError("No committed result; use --online to query the Temporal workflow")
        emit(InvestigationResult.model_validate(store.get_json(ref)))
        return 0
    if args.command == "rescore":
        _, _, oracles = load_dataset(Path(args.dataset))
        rows = []
        for identity in args.run_ids:
            ref = store.reconcile(f"result.{identity}")
            if ref is None:
                rows.append({"run_id": identity, "status": "unavailable", "reason": "No result"})
                continue
            result = InvestigationResult.model_validate(store.get_json(ref))
            rows.append(score(result, oracles[result.case_id], store))
        report = save_report(Path(args.output), rows)
        emit(report["summary"])
        return 0 if report["summary"]["failed"] == 0 else 1
    if args.command == "report":
        report = json.loads(Path(args.report).read_text())
        emit(report["summary"])
        return 0

    from datetime import timedelta

    from corsair.runtime.worker import connect
    from corsair.workflows.evaluation import EvaluationWorkflow
    from corsair.workflows.investigation import InvestigationWorkflow

    client = await connect(settings)
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
        if args.wait:
            result = await handle.result()
            emit(result)
            return 0 if result.execution_status.value == "COMPLETED" else 1
        emit({"run_id": handle.id, "state": "submitted", "security_disposition": None})
        return 0
    if args.command == "inspect":
        emit(await client.get_workflow_handle(args.run_id).query(InvestigationWorkflow.status))
        return 0
    if args.command == "cancel":
        await client.get_workflow_handle(args.run_id).cancel()
        emit({"run_id": args.run_id, "state": "cancellation_requested"})
        return 0
    if args.command == "eval":
        dataset, requests, oracles = load_dataset(Path(args.dataset))
        identity = run_id(args.run_id or f"eval-{uuid4().hex}")
        batch = BatchRequest(
            batch_id=identity,
            requests=requests,
            repeats=args.repeats,
            concurrency=args.concurrency,
        )
        handle = await client.start_workflow(
            EvaluationWorkflow.run,
            batch,
            id=identity,
            task_queue=settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        items: list[BatchItem] = await handle.result()
        rows = []
        for item in items:
            if item.artifact is None:
                rows.append(
                    {
                        "case_id": item.case_id,
                        "run_id": item.run_id,
                        "status": "unavailable",
                        "reason": item.error or "Result artifact unavailable",
                    }
                )
                continue
            try:
                result = InvestigationResult.model_validate(store.get_json(item.artifact))
                rows.append(score(result, oracles[item.case_id], store))
            except (FileNotFoundError, ValueError) as exc:
                rows.append(
                    {
                        "case_id": item.case_id,
                        "run_id": item.run_id,
                        "status": "unavailable",
                        "reason": str(exc),
                    }
                )
        output = Path(args.output or f".runs/evaluations/{identity}.json")
        report = save_report(output, rows)
        report["dataset_digest"] = digest(dataset)
        output.write_text(json.dumps(report, indent=2) + "\n")
        emit({"report": str(output), "summary": report["summary"]})
        return 0 if report["summary"]["failed"] == 0 else 1
    raise ValueError("Unknown command")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Evidence-first security verification on ADK + Temporal"
    )
    sub = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--settings", help="Worker/client settings JSON; credentials stay in environment"
    )
    sub.add_parser("worker", parents=[common], help="Run the standard Temporal worker")
    investigate = sub.add_parser("investigate", parents=[common])
    investigate.add_argument("request")
    investigate.add_argument("--run-id")
    investigate.add_argument("--wait", action="store_true")
    inspect = sub.add_parser("inspect", parents=[common])
    inspect.add_argument("run_id")
    inspect.add_argument("--online", action="store_true")
    cancel = sub.add_parser("cancel", parents=[common])
    cancel.add_argument("run_id")
    verify = sub.add_parser(
        "verify", parents=[common], help="Replay a reference submission; no verdict"
    )
    verify.add_argument("request")
    verify.add_argument("submission")
    verify.add_argument("--run-id")
    verify.add_argument("--fixed", action="store_true")
    evaluation = sub.add_parser("eval", parents=[common])
    evaluation.add_argument("dataset")
    evaluation.add_argument("--run-id")
    evaluation.add_argument("--repeats", type=int, default=1)
    evaluation.add_argument("--concurrency", type=int, default=2)
    evaluation.add_argument("--output")
    rescore = sub.add_parser("rescore", parents=[common])
    rescore.add_argument("dataset")
    rescore.add_argument("run_ids", nargs="+")
    rescore.add_argument("--output", default=".runs/evaluations/rescored.json")
    report = sub.add_parser("report", parents=[common])
    report.add_argument("report")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        code = asyncio.run(execute(args))
    except (ValueError, ValidationError, FileNotFoundError, PermissionError) as exc:
        print(f"corsair: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    raise SystemExit(code)
