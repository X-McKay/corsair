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

from corsair.adapters.artifacts.filesystem import ArtifactStore, write_json
from corsair.adapters.frameworks import framework
from corsair.adapters.inference.openai import OpenAIInference
from corsair.adapters.sandbox import sandboxes
from corsair.adapters.scm import source_control
from corsair.agents.auditor.agent import audit, build_auditor
from corsair.agents.producer.dependencies import NEGATIVE_THRESHOLD
from corsair.agents.producer.types import ProducerRun
from corsair.application.cases import load_case, load_oracle
from corsair.application.evaluation import _ledger, _load_set, per_case, score, summarise
from corsair.application.investigation import investigate
from corsair.application.kernel import Kernel, reported_target_present
from corsair.domain.case import Case
from corsair.domain.policy import negative_verdict, terminal_verdict
from corsair.domain.verification import Evaluation, Fix, Label, Submission, Verdict
from corsair.ports.inference import Inference
from corsair.ports.scm import SourceControl
from corsair.runtime import matrix
from corsair.runtime.inference import load_provider_config

RUNS = Path(".runs/lite")


def _record(
    run_dir: Path,
    case: Case,
    row: matrix.Row | None,
    verdict: Verdict,
    evaluations: tuple[Evaluation, ...],
    *,
    mode: str,
    extra: dict,
) -> dict:
    from corsair.agents.auditor.agent import instructions as audit_instructions
    from corsair.agents.producer.agent import instructions as producer_instructions
    from corsair.agents.producer.dependencies import SKILLS_DIR

    manifest = {
        "schema": "corsair-lite/manifest/1",
        "contract": case.contract,
        "runtime": row.model_dump(mode="json") if row else None,
        "instructions": hashlib.sha256((producer_instructions() + audit_instructions()).encode()).hexdigest(),
        "skills": {
            p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))
        },
        "agent_specs": {
            p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).with_name("agents").glob("*/agent.yaml"))
        },
        "models": extra.get("models"),
        "limits": {key: extra.get(key) for key in ("max_submissions", "negative_threshold", "request_limit")},
        "audit_configured": extra.get("audit_configured", False),
    }
    manifest_sha256 = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    record = {
        "schema": "corsair-lite/run/1",
        "run_id": run_dir.name,
        "mode": mode,
        "case_id": case.case_id,
        "tree_sha256": case.revision.tree_sha256,
        "fixed_tree_sha256": case.fixed_revision.tree_sha256 if case.fixed_revision else None,
        "runtime_row": row.id if row else None,
        "image": row.image if row else None,
        "submissions": [e.model_dump(mode="json") for e in evaluations],
        "verdict": verdict.model_dump(mode="json"),
        "manifest_sha256": manifest_sha256,
        **extra,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "run.json", record)
    for index, evaluation in enumerate(evaluations, 1):
        (run_dir / f"submission-{index}.json").write_text(
            evaluation.submission.model_dump_json(indent=2) + "\n"
        )
    return record


def _print(record: dict) -> None:
    verdict = record["verdict"]
    gates = [s["gate"]["stage"] for s in record["submissions"]]
    print(
        f"{record['case_id']}: {verdict['label']} ({verdict['rule']}) fix={verdict['fix']} "
        f"submissions={len(gates)} gates={gates} run={record['run_id']}",
        file=sys.stderr,
    )


async def _verify(args: argparse.Namespace, inference: Inference, scm: SourceControl) -> int:
    case = load_case(Path(args.case), scm=scm)
    row = matrix.select(case)
    run_id = args.run_id or uuid.uuid4().hex[:12]
    run_dir = Path(args.runs) / run_id
    if row is None:
        verdict = Verdict(
            label=Label.UNABLE_TO_RUN,
            rule="K2",
            reason="no runtime row matches the tree",
            fix=Fix.NOT_APPLICABLE,
        )
        _print(_record(run_dir, case, None, verdict, (), mode="verify", extra={}))
        return 2
    submission = Submission.model_validate_json(Path(args.submission).read_text())
    store = ArtifactStore(run_dir / "artifacts")
    backend = sandboxes()
    started = time.monotonic()
    if args.provider:
        config = load_provider_config(Path(args.provider))
        async with inference.models(config, ["auditor"]) as models:
            auditor = build_auditor(models["auditor"])
            kernel = Kernel(
                backend,
                row,
                case,
                artifacts=store,
                run_id=run_id,
                auditor=lambda s: audit(auditor, s),
                framework=framework(row.framework),
            )
            evaluation = await kernel.evaluate(submission)
    else:
        kernel = Kernel(
            backend, row, case, artifacts=store, run_id=run_id, framework=framework(row.framework)
        )
        evaluation = await kernel.evaluate(submission)
    verdict = (
        evaluation.verdict
        or negative_verdict([evaluation], args.negative_threshold)
        or terminal_verdict(evaluation.gate, 1)
    )
    record = _record(
        run_dir,
        case,
        row,
        verdict,
        (evaluation,),
        mode="verify",
        extra={
            "duration_s": time.monotonic() - started,
            "audit_configured": bool(args.provider),
            "negative_threshold": args.negative_threshold,
        },
    )
    _print(record)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if verdict.label is Label.LIKELY_EXPLOITABLE else 1


async def _investigate_one(
    case: Case, args: argparse.Namespace, models: dict, model_config: dict | None = None
) -> dict:
    row = matrix.select(case)
    run_id = uuid.uuid4().hex[:12]
    run_dir = Path(args.runs) / run_id
    if row is None:
        verdict = Verdict(
            label=Label.UNABLE_TO_RUN,
            rule="K2",
            reason="no runtime row matches the tree",
            fix=Fix.NOT_APPLICABLE,
        )
        return _record(run_dir, case, None, verdict, (), mode="investigate", extra={})
    absent = reported_target_present(case)
    if absent is not None:  # decided by trusted code; no model call, no sandbox
        verdict = Verdict(
            label=Label.UNABLE_TO_RUN, rule="K2", reason=f"target_not_found: {absent}", fix=Fix.NOT_APPLICABLE
        )
        return _record(run_dir, case, row, verdict, (), mode="investigate", extra={"requests": 0})
    store = ArtifactStore(run_dir / "artifacts")
    backend = sandboxes()
    auditor_agent = None if args.no_audit else build_auditor(models["auditor"])
    kernel = Kernel(
        backend,
        row,
        case,
        artifacts=store,
        run_id=run_id,
        auditor=None if auditor_agent is None else (lambda s: audit(auditor_agent, s)),
        framework=framework(row.framework),
    )
    checkpoints: list[dict] = []

    def checkpoint(evaluation: Evaluation) -> None:
        checkpoints.append(evaluation.model_dump(mode="json"))
        write_json(
            run_dir / "checkpoint.json",
            {
                "schema": "corsair-lite/checkpoint/1",
                "run_id": run_id,
                "state": "running",
                "case_id": case.case_id,
                "tree_sha256": case.revision.tree_sha256,
                "submissions": checkpoints,
            },
        )

    run: ProducerRun = await investigate(
        case,
        row,
        model=models["producer"],
        kernel=kernel,
        backend=backend,
        max_submissions=args.max_submissions,
        request_limit=args.request_limit,
        negative_threshold=args.negative_threshold,
        checkpoint=checkpoint,
    )
    extra = {
        "duration_s": run.duration_s,
        "requests": run.requests,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "tool_calls": run.tool_calls,
        "bash_calls": run.bash_calls,
        "final_text": run.final_text,
        "error": run.error,
        "work_cleanup_confirmed": run.cleanup_confirmed,
        "audit_configured": auditor_agent is not None,
        "max_submissions": args.max_submissions,
        "negative_threshold": args.negative_threshold,
        "early_stop": run.early_stop,
        "observations": list(run.observations),
        "request_limit": args.request_limit,
        "models": model_config,
    }
    record = _record(run_dir, case, row, run.verdict, run.evaluations, mode="investigate", extra=extra)
    write_json(
        run_dir / "checkpoint.json",
        {"schema": "corsair-lite/checkpoint/1", "run_id": run_id, "state": "finished", "record": "run.json"},
    )
    _print(record)
    return record


async def _investigate(args: argparse.Namespace, inference: Inference, scm: SourceControl) -> int:
    case = load_case(Path(args.case), scm=scm)
    config = load_provider_config(Path(args.provider))
    async with inference.models(config) as models:
        record = await _investigate_one(case, args, models, _models(config))
    print(json.dumps(record["verdict"], indent=2))
    return 0 if record["verdict"]["label"] == Label.LIKELY_EXPLOITABLE else 1


def _models(config) -> dict:
    """The profile, model name and endpoint each agent ran on, so results are compared by model."""
    out = {}
    for agent, name in sorted(config.agents.items()):
        profile = config.profile(agent)
        out[agent] = {
            "profile": name,
            "model_name": profile.model_name,
            "base_url": profile.base_url,
            "max_tokens": profile.max_tokens,
            "temperature": profile.temperature,
            "thinking": profile.thinking,
            "thinking_token_budget": profile.thinking_token_budget,
        }
    return out


async def _eval(args: argparse.Namespace, inference: Inference, scm: SourceControl) -> int:
    config = load_provider_config(Path(args.provider))
    if args.set:
        case_dirs, held_out = _load_set(Path(args.set))
    else:
        case_dirs, held_out = [Path(p) for p in args.cases], None
    rows = []
    async with inference.models(config) as models:
        for case_dir in case_dirs:
            case = load_case(case_dir, scm=scm)
            oracle = load_oracle(case_dir) or {}
            expected = oracle.get("expected_label")
            for repeat in range(1, args.repeats + 1):
                record = await _investigate_one(case, args, models, _models(config))
                label = record["verdict"]["label"]
                correct, forbidden_hit, note = score(case_dir.name, oracle, label)
                rows.append(
                    {
                        "case": str(case_dir),
                        "case_id": case.case_id,
                        "repeat": repeat,
                        "label": label,
                        "fix": record["verdict"]["fix"],
                        "expected_label": expected,
                        "expected_fix": oracle.get("expected_fix"),
                        "correct": correct,
                        "forbidden_hit": forbidden_hit,
                        "policy_note": note,
                        "submissions": len(record["submissions"]),
                        "early_stop": record.get("early_stop"),
                        "gates": [s["gate"]["stage"] for s in record["submissions"]],
                        "requests": record.get("requests"),
                        "input_tokens": record.get("input_tokens"),
                        "output_tokens": record.get("output_tokens"),
                        "tool_calls": record.get("tool_calls"),
                        "bash_calls": record.get("bash_calls"),
                        "duration_s": record.get("duration_s"),
                        "run_id": record["run_id"],
                    }
                )
    summary = {
        "schema": "corsair-lite/eval/2",
        "provider": str(args.provider),
        "models": _models(config),
        "set": str(args.set) if args.set else None,
        "held_out": held_out,
        "cases": len(case_dirs),
        "repeats": args.repeats,
        "max_submissions": args.max_submissions,
        "negative_threshold": args.negative_threshold,
        "metrics": summarise(rows),
        "per_case": per_case(rows),
        "policy_divergences": [
            {"case_id": r["case_id"], "label": r["label"], "note": r["policy_note"]}
            for r in rows
            if r["policy_note"]
        ],
        "gate_ledger": _ledger(rows),
        "runs": rows,
    }
    out = Path(args.runs) / f"eval-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    write_json(out, summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("runs", "per_case")}, indent=2))
    print(f"written {out}", file=sys.stderr)
    return 0 if summary["metrics"]["forbidden_hits"] == 0 else 1


def _cleanup(args: argparse.Namespace) -> int:
    backend = sandboxes()
    names = backend.labelled(args.run_id)
    unconfirmed = [name for name in names if not backend.remove(name)]
    print(
        f"removed {len(names) - len(unconfirmed)} container(s); unconfirmed: {unconfirmed}", file=sys.stderr
    )
    if args.images:
        from corsair.adapters.sandbox.docker import docker
        from corsair.application.kernel import ENV_REPOSITORY

        listed = docker("images", ENV_REPOSITORY, "--format", "{{.Repository}}:{{.Tag}}")
        tags = sorted(set(listed.stdout.decode().split())) if listed.returncode == 0 else []
        failed = [tag for tag in tags if docker("rmi", tag).returncode != 0]
        print(
            f"removed {len(tags) - len(failed)} sealed environment image(s); failed: {failed}",
            file=sys.stderr,
        )
        unconfirmed += failed
    return 0 if not unconfirmed else 1


async def _proposal(args: argparse.Namespace, inference: Inference, scm: SourceControl) -> int:
    from corsair.agents.bug_seeder.agent import propose_seed
    from corsair.agents.producer.dependencies import SKILLS_DIR
    from corsair.agents.skill_crystallizer.agent import optimize_skills_from_trace
    from corsair.domain.verification import GateVerdict

    config = load_provider_config(Path(args.provider))
    async with inference.models(config, ["producer"]) as models:
        if args.command == "seed":
            from pydantic import TypeAdapter

            from corsair.domain.case import SafePath

            target = TypeAdapter(SafePath).validate_python(args.target)
            case = load_case(Path(args.case), scm=scm)
            root = Path(case.revision.source).resolve()
            path = root / target
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("seed target must be a regular file inside the case revision")
            if path.stat().st_size > 64_000:
                raise ValueError("seed target exceeds 64 KB")
            proposal = await propose_seed(
                models["producer"], target, path.read_text(), args.vulnerability_class
            )
        else:
            record = json.loads(Path(args.trace).read_text())
            rejections = [
                GateVerdict.model_validate(s["gate"])
                for s in record["submissions"]
                if not s["gate"]["passed"]
            ]
            proposal = await optimize_skills_from_trace(
                models["producer"], record["verdict"]["label"], rejections, SKILLS_DIR
            )
    result = {
        "schema": "corsair-lite/proposal/1",
        "applied": False,
        "proposal": proposal.model_dump(mode="json") if proposal is not None else None,
    }
    write_json(Path(args.output), result)
    print(json.dumps(result, indent=2))
    return 0


def _threshold(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("the negative threshold is at least 1")
    return number


def _repeats(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("repeats is at least 1")
    return number


def main(
    argv: list[str] | None = None, *, inference: Inference | None = None, scm: SourceControl | None = None
) -> int:
    parser = argparse.ArgumentParser(prog="corsair", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="run the kernel on a supplied submission (no producer)")
    verify.add_argument("--case", required=True, help="case directory with input.json, or a request file")
    verify.add_argument(
        "--submission", required=True, help="JSON file with hypothesis, build_script and probe"
    )
    verify.add_argument("--provider", help="provider config; enables the blind auditor")
    verify.add_argument("--runs", default=str(RUNS))
    verify.add_argument("--run-id")
    verify.add_argument(
        "--negative-threshold",
        type=_threshold,
        default=NEGATIVE_THRESHOLD,
        help="distinct clean negatives that make LIKELY_NOT_EXPLOITABLE (operator-owned)",
    )

    inv = sub.add_parser("investigate", help="run the producer against a case")
    inv.add_argument("--case", required=True)
    inv.add_argument("--provider", required=True)
    inv.add_argument("--max-submissions", type=_threshold, default=4)
    inv.add_argument("--request-limit", type=_threshold, default=60)
    inv.add_argument("--no-audit", action="store_true")
    inv.add_argument(
        "--negative-threshold",
        type=_threshold,
        default=NEGATIVE_THRESHOLD,
        help="distinct clean negatives that end the run as LIKELY_NOT_EXPLOITABLE (operator-owned)",
    )
    inv.add_argument("--runs", default=str(RUNS))

    ev = sub.add_parser(
        "eval", help="investigate several case directories and score them against oracle.json"
    )
    source = ev.add_mutually_exclusive_group(required=True)
    source.add_argument("--cases", nargs="+", help="case directories")
    source.add_argument("--set", help="a frozen case set under evals/e2e/sets (dev or held-out)")
    ev.add_argument(
        "--repeats",
        type=_repeats,
        default=1,
        help="full investigations per case; repeats measure run-to-run agreement (default 1)",
    )
    ev.add_argument("--provider", required=True)
    ev.add_argument("--max-submissions", type=_threshold, default=4)
    ev.add_argument("--request-limit", type=_threshold, default=60)
    ev.add_argument("--no-audit", action="store_true")
    ev.add_argument(
        "--negative-threshold",
        type=_threshold,
        default=NEGATIVE_THRESHOLD,
        help="distinct clean negatives that end a run as LIKELY_NOT_EXPLOITABLE (operator-owned)",
    )
    ev.add_argument("--runs", default=str(RUNS))

    clean = sub.add_parser("cleanup", help="remove every container this tool created (optionally one run)")
    clean.add_argument("--run-id")
    clean.add_argument("--images", action="store_true", help="also remove the sealed corsair-lite-env images")

    seed = sub.add_parser("seed", help="propose a synthetic bug diff; never modify the source tree")
    seed.add_argument("--case", required=True)
    seed.add_argument("--target", required=True)
    seed.add_argument("--vulnerability-class", required=True)
    seed.add_argument("--provider", required=True)
    seed.add_argument("--output", required=True)
    optimize = sub.add_parser("optimize-skills", help="propose a Markdown rule from successful run friction")
    optimize.add_argument("--trace", required=True, help="run.json from a successful investigation")
    optimize.add_argument("--provider", required=True)
    optimize.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    inference = inference or OpenAIInference()
    scm = scm or source_control()
    if args.command in ("seed", "optimize-skills"):
        return asyncio.run(_proposal(args, inference, scm))
    if args.command == "verify":
        return asyncio.run(_verify(args, inference, scm))
    if args.command == "investigate":
        return asyncio.run(_investigate(args, inference, scm))
    if args.command == "eval":
        return asyncio.run(_eval(args, inference, scm))
    return _cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
