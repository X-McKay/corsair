"""Command line: verify a human- or agent-supplied submission with the kernel alone, investigate a case with the
producer, evaluate a set of cases against their oracles, or sweep this tool's containers.

Every run writes ``.runs/lite/<run id>/run.json`` (the record) and keeps logs and reports in an artifact store
beside it. Nothing here calls a model unless a provider config is given.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

from . import matrix
from .artifacts import ArtifactStore
from .auditor import audit, build_auditor
from .benchmark import verify_references
from .case import Case, load_case, load_oracle
from .kernel import Evaluation, Fix, Kernel, Label, Submission, Verdict, reported_target_present, terminal_verdict
from .producer import ProducerRun, investigate
from .providers import agent_models, load_provider_config
from .sandbox import sandboxes

RUNS = Path(".runs/lite")


def _record(run_dir: Path, case: Case, row: matrix.Row | None, verdict: Verdict, evaluations: tuple[Evaluation, ...],
            *, mode: str, extra: dict) -> dict:
    package = Path(__file__).parent
    versions = {path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(package.rglob("*")) if path.is_file() and path.suffix in (".py", ".md", ".yaml")}
    record = {"schema": "corsair-lite/run/2", "run_id": run_dir.name, "mode": mode, "case_id": case.case_id,
              "tree_sha256": case.revision.tree_sha256,
              "fixed_tree_sha256": case.fixed_revision.tree_sha256 if case.fixed_revision else None,
              "runtime_row": row.id if row else None, "image": row.image if row else None,
              "runtime": row.model_dump(mode="json") if row else None, "implementation_sha256": versions,
              "submissions": [e.model_dump(mode="json") for e in evaluations],
              "verdict": verdict.model_dump(mode="json"), **extra}
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    for index, evaluation in enumerate(evaluations, 1):
        (run_dir / f"submission-{index}.json").write_text(evaluation.submission.model_dump_json(indent=2) + "\n")
    return record


def _print(record: dict) -> None:
    verdict = record["verdict"]
    gates = [s["gate"]["stage"] for s in record["submissions"]]
    print(f"{record['case_id']}: {verdict['label']} ({verdict['rule']}) fix={verdict['fix']} "
          f"submissions={len(gates)} gates={gates} run={record['run_id']}", file=sys.stderr)


async def _verify(args: argparse.Namespace) -> int:
    case = load_case(Path(args.case))
    row = matrix.select(case)
    run_id = args.run_id or uuid.uuid4().hex[:12]
    run_dir = Path(args.runs) / run_id
    if row is None:
        verdict = Verdict(label=Label.UNABLE_TO_RUN, rule="K2", reason="no runtime row matches the tree", fix=Fix.NOT_APPLICABLE)
        _print(_record(run_dir, case, None, verdict, (), mode="verify", extra={}))
        return 2
    try:
        submission = Submission.model_validate_json(Path(args.submission).read_text())
    except ValidationError as error:
        print(f"invalid submission: {error}", file=sys.stderr)
        return 2
    store = ArtifactStore(run_dir / "artifacts")
    backend = sandboxes()
    started = time.monotonic()
    if args.provider:
        config = load_provider_config(Path(args.provider))
        async with agent_models(config, ["auditor"]) as models:
            auditor = build_auditor(models["auditor"])
            kernel = Kernel(backend, row, case, artifacts=store, run_id=run_id,
                            auditor=lambda s: audit(auditor, s))
            evaluation = await kernel.evaluate(submission)
    else:
        kernel = Kernel(backend, row, case, artifacts=store, run_id=run_id)
        evaluation = await kernel.evaluate(submission)
    verdict = evaluation.verdict or terminal_verdict(evaluation.gate, 1)
    record = _record(run_dir, case, row, verdict, (evaluation,), mode="verify",
                     extra={"duration_s": time.monotonic() - started, "audit_configured": bool(args.provider),
                            "runtime_image_id": kernel.runtime_image_id})
    _print(record)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if verdict.label in (Label.LIKELY_EXPLOITABLE, Label.LIKELY_NOT_EXPLOITABLE) else 1


async def _investigate_one(case: Case, args: argparse.Namespace, models: dict) -> dict:
    row = matrix.select(case)
    run_id = uuid.uuid4().hex[:12]
    run_dir = Path(args.runs) / run_id
    if row is None:
        verdict = Verdict(label=Label.UNABLE_TO_RUN, rule="K2", reason="no runtime row matches the tree", fix=Fix.NOT_APPLICABLE)
        return _record(run_dir, case, None, verdict, (), mode="investigate", extra={})
    absent = reported_target_present(case)
    if absent is not None:  # decided by trusted code; no model call, no sandbox
        verdict = Verdict(label=Label.UNABLE_TO_RUN, rule="K2", reason=f"target_not_found: {absent}", fix=Fix.NOT_APPLICABLE)
        return _record(run_dir, case, row, verdict, (), mode="investigate", extra={"requests": 0})
    store = ArtifactStore(run_dir / "artifacts")
    backend = sandboxes()
    auditor_agent = None if args.no_audit else build_auditor(models["auditor"])
    kernel = Kernel(backend, row, case, artifacts=store, run_id=run_id,
                    auditor=None if auditor_agent is None else (lambda s: audit(auditor_agent, s)))
    run: ProducerRun = await investigate(case, row, model=models["producer"], kernel=kernel, backend=backend,
                                         max_submissions=args.max_submissions, request_limit=args.request_limit)
    extra = {"duration_s": run.duration_s, "requests": run.requests, "input_tokens": run.input_tokens,
             "output_tokens": run.output_tokens, "tool_calls": run.tool_calls, "bash_calls": run.bash_calls,
             "final_text": run.final_text, "error": run.error, "work_cleanup_confirmed": run.cleanup_confirmed,
             "audit_configured": auditor_agent is not None, "max_submissions": args.max_submissions,
             "runtime_image_id": kernel.runtime_image_id,
             "models": {name: model.model_name for name, model in models.items()}}
    record = _record(run_dir, case, row, run.verdict, run.evaluations, mode="investigate", extra=extra)
    _print(record)
    return record


async def _investigate(args: argparse.Namespace) -> int:
    case = load_case(Path(args.case))
    config = load_provider_config(Path(args.provider))
    async with agent_models(config) as models:
        record = await _investigate_one(case, args, models)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if record["verdict"]["label"] in (Label.LIKELY_EXPLOITABLE, Label.LIKELY_NOT_EXPLOITABLE) else 1


async def _eval(args: argparse.Namespace) -> int:
    config = load_provider_config(Path(args.provider))
    rows = []
    async with agent_models(config) as models:
        for path in args.cases:
            case_dir = Path(path)
            case = load_case(case_dir)
            oracle = load_oracle(case_dir) or {}
            record = await _investigate_one(case, args, models)
            expected = oracle.get("expected_label")
            label = record["verdict"]["label"]
            expected_fix = oracle.get("expected_fix")
            oracle_path = case_dir / "oracle.json"
            label_correct = label == expected if expected else None
            fix_correct = record["verdict"]["fix"] == expected_fix if expected_fix else None
            checks = [check for check in (label_correct, fix_correct) if check is not None]
            rows.append({"case": str(case_dir), "case_id": case.case_id, "label": label, "fix": record["verdict"]["fix"],
                         "runtime_row": record.get("runtime_row"),
                         "dataset_version": oracle.get("dataset_version"),
                         "oracle_sha256": hashlib.sha256(oracle_path.read_bytes()).hexdigest()
                         if oracle_path.is_file() else None,
                         "expected_label": expected, "expected_fix": oracle.get("expected_fix"),
                         "label_correct": label_correct, "fix_correct": fix_correct,
                         "correct": all(checks) if checks else None,
                         "forbidden_hit": label in (oracle.get("forbidden_labels") or []),
                         "submissions": len(record["submissions"]),
                         "gates": [s["gate"]["stage"] for s in record["submissions"]],
                         "requests": record.get("requests"), "input_tokens": record.get("input_tokens"),
                         "output_tokens": record.get("output_tokens"), "duration_s": record.get("duration_s"),
                         "run_id": record["run_id"]})
    scored = [r for r in rows if r["correct"] is not None]
    summary = {"schema": "corsair-lite/eval/2", "cases": rows, "n": len(rows),
               "correct": sum(1 for r in scored if r["correct"]), "scored": len(scored),
               "forbidden_hits": sum(1 for r in rows if r["forbidden_hit"]),
               "gate_ledger": _ledger(rows), "provider": str(args.provider), "max_submissions": args.max_submissions}
    summary["passed"] = bool(rows) and len(scored) == len(rows) and all(r["correct"] for r in scored) and summary["forbidden_hits"] == 0
    provider_path = Path(args.provider)
    summary["provider_sha256"] = hashlib.sha256(provider_path.read_bytes()).hexdigest() if provider_path.is_file() else None
    out = Path(args.runs) / f"eval-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))
    print(f"written {out}", file=sys.stderr)
    return 0 if summary["passed"] else 1


def _ledger(rows: list[dict]) -> dict[str, int]:
    ledger: dict[str, int] = {}
    for row in rows:
        for gate in row["gates"]:
            ledger[gate] = ledger.get(gate, 0) + 1
    return dict(sorted(ledger.items()))


def _cleanup(args: argparse.Namespace) -> int:
    backend = sandboxes()
    names = backend.labelled(args.run_id)
    unconfirmed = [name for name in names if not backend.remove(name)]
    print(f"removed {len(names) - len(unconfirmed)} container(s); unconfirmed: {unconfirmed}", file=sys.stderr)
    if args.images:
        from .sandbox.docker import docker
        from .kernel import ENV_REPOSITORY
        listed = docker("images", ENV_REPOSITORY, "--format", "{{.Repository}}:{{.Tag}}")
        tags = sorted(set(listed.stdout.decode().split())) if listed.returncode == 0 else []
        failed = [tag for tag in tags if docker("rmi", tag).returncode != 0]
        print(f"removed {len(tags) - len(failed)} sealed environment image(s); failed: {failed}", file=sys.stderr)
        unconfirmed += failed
    return 0 if not unconfirmed else 1


async def _benchmark_verify(args: argparse.Namespace) -> int:
    try:
        report = await verify_references(
            root=Path.cwd(), manifest_path=Path(args.manifest), eval_set=args.eval_set,
            attempts=args.attempts, runs_root=Path(args.runs), receipts_root=Path(args.receipts))
    except (OSError, ValidationError, ValueError) as error:
        print(f"benchmark-verify input invalid: {error}", file=sys.stderr)
        return 2
    for case in report.cases:
        for attempt in case.attempts:
            detail = f" failure={attempt.failure_code}" if attempt.failure_code else ""
            print(f"{case.case_id} attempt={attempt.attempt} outcome={attempt.outcome} "
                  f"receipt={attempt.path}{detail}", file=sys.stderr)
    complete = sum(attempt.outcome == "complete" for case in report.cases for attempt in case.attempts)
    total = sum(len(case.attempts) for case in report.cases)
    summary = {
        "schema": report.schema_version,
        "dataset_version": report.dataset_version,
        "eval_set": report.eval_set,
        "qualification_run_id": report.qualification_run_id,
        "cases": len(report.cases),
        "attempts": total,
        "complete": complete,
        "admission_ready": sum(case.admission_ready for case in report.cases),
        "ok": report.ok,
    }
    print(json.dumps(summary, indent=2))
    return 0 if report.ok else 1


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corsair", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="run the kernel on a supplied submission (no producer)")
    verify.add_argument("--case", required=True, help="case directory with input.json, or a request file")
    verify.add_argument("--submission", required=True,
                        help="v2 JSON file with contract_version, hypothesis, build_script and Boolean probe")
    verify.add_argument("--provider", help="provider config; enables the blind auditor")
    verify.add_argument("--runs", default=str(RUNS))
    verify.add_argument("--run-id")

    inv = sub.add_parser("investigate", help="run the producer against a case")
    inv.add_argument("--case", required=True)
    inv.add_argument("--provider", required=True)
    inv.add_argument("--max-submissions", type=int, default=4)
    inv.add_argument("--request-limit", type=int, default=60)
    inv.add_argument("--no-audit", action="store_true")
    inv.add_argument("--runs", default=str(RUNS))

    ev = sub.add_parser("eval", help="investigate several case directories and score them against oracle.json")
    ev.add_argument("--cases", nargs="+", required=True)
    ev.add_argument("--provider", required=True)
    ev.add_argument("--max-submissions", type=int, default=4)
    ev.add_argument("--request-limit", type=int, default=60)
    ev.add_argument("--no-audit", action="store_true")
    ev.add_argument("--runs", default=str(RUNS))

    benchmark = sub.add_parser("benchmark-verify", help="replay trusted corpus references and write receipts")
    benchmark.add_argument("--manifest", default="benchmarks/dataset/manifest.json")
    benchmark.add_argument("--eval-set", choices=("conformance", "development", "regression", "release"),
                           default="development")
    benchmark.add_argument("--attempts", type=_positive_int, default=3)
    benchmark.add_argument("--runs", default=str(RUNS))
    benchmark.add_argument("--receipts", default="benchmarks/dataset/receipts")

    clean = sub.add_parser("cleanup", help="remove every container this tool created (optionally one run)")
    clean.add_argument("--run-id")
    clean.add_argument("--images", action="store_true", help="also remove the sealed corsair-lite-env images")

    args = parser.parse_args(argv)
    if args.command == "verify":
        return asyncio.run(_verify(args))
    if args.command == "investigate":
        return asyncio.run(_investigate(args))
    if args.command == "eval":
        return asyncio.run(_eval(args))
    if args.command == "benchmark-verify":
        return asyncio.run(_benchmark_verify(args))
    return _cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
