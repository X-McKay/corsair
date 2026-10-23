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
from collections import Counter
from pathlib import Path

from . import matrix
from .artifacts import ArtifactStore, write_json
from .auditor import audit, build_auditor
from .case import Case, load_case, load_oracle
from .kernel import (Evaluation, Fix, Kernel, Label, Submission, Verdict, negative_verdict, reported_target_present,
                     terminal_verdict)
from .producer import NEGATIVE_THRESHOLD, ProducerRun, investigate
from .providers import agent_models, load_provider_config
from .sandbox import sandboxes

RUNS = Path(".runs/lite")
LABELS = ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE")  # the two decisive labels, reported with precision and recall
TELEMETRY = ("requests", "input_tokens", "output_tokens", "tool_calls", "bash_calls", "duration_s")

# v2 oracles whose expectation predates the lite contract. Lite's behaviour is the intended one here, so the case is
# scored against the lite label (None: not scored) and the divergence is reported, not counted as a miss. See
# docs/pilot.md. The oracle's forbidden labels do not apply to these cases.
LITE_CONTRACT: dict[str, tuple[frozenset[str] | None, str]] = {
    "ineffective-fix": (frozenset({"LIKELY_EXPLOITABLE"}),
                        "a non-working fix keeps LIKELY_EXPLOITABLE with fix=not_verified; v2 expected INCONCLUSIVE"),
    "bare-tree-no-manifest": (None, "Python trees with no manifest are accepted; v2 expected UNABLE_TO_RUN"),
}


def _record(run_dir: Path, case: Case, row: matrix.Row | None, verdict: Verdict, evaluations: tuple[Evaluation, ...],
            *, mode: str, extra: dict) -> dict:
    from .auditor import INSTRUCTIONS as AUDIT_INSTRUCTIONS
    from .producer import INSTRUCTIONS, SKILLS_DIR
    manifest = {"schema": "corsair-lite/manifest/1", "contract": case.contract,
                "runtime": row.model_dump(mode="json") if row else None,
                "instructions": hashlib.sha256((INSTRUCTIONS + AUDIT_INSTRUCTIONS).encode()).hexdigest(),
                "skills": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SKILLS_DIR.glob("*.md"))},
                "models": extra.get("models"),
                "limits": {key: extra.get(key) for key in ("max_submissions", "negative_threshold", "request_limit")},
                "audit_configured": extra.get("audit_configured", False)}
    manifest_sha256 = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    record = {"schema": "corsair-lite/run/1", "run_id": run_dir.name, "mode": mode, "case_id": case.case_id,
              "tree_sha256": case.revision.tree_sha256,
              "fixed_tree_sha256": case.fixed_revision.tree_sha256 if case.fixed_revision else None,
              "runtime_row": row.id if row else None, "image": row.image if row else None,
              "submissions": [e.model_dump(mode="json") for e in evaluations],
              "verdict": verdict.model_dump(mode="json"), "manifest_sha256": manifest_sha256, **extra}
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "run.json", record)
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
    submission = Submission.model_validate_json(Path(args.submission).read_text())
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
    verdict = (evaluation.verdict or negative_verdict([evaluation], args.negative_threshold)
               or terminal_verdict(evaluation.gate, 1))
    record = _record(run_dir, case, row, verdict, (evaluation,), mode="verify",
                     extra={"duration_s": time.monotonic() - started, "audit_configured": bool(args.provider),
                            "negative_threshold": args.negative_threshold})
    _print(record)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if verdict.label is Label.LIKELY_EXPLOITABLE else 1


async def _investigate_one(case: Case, args: argparse.Namespace, models: dict, model_config: dict | None = None) -> dict:
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
    checkpoints: list[dict] = []

    def checkpoint(evaluation: Evaluation) -> None:
        checkpoints.append(evaluation.model_dump(mode="json"))
        write_json(run_dir / "checkpoint.json", {"schema": "corsair-lite/checkpoint/1", "run_id": run_id,
                                                "state": "running", "case_id": case.case_id,
                                                "tree_sha256": case.revision.tree_sha256,
                                                "submissions": checkpoints})

    run: ProducerRun = await investigate(case, row, model=models["producer"], kernel=kernel, backend=backend,
                                         max_submissions=args.max_submissions, request_limit=args.request_limit,
                                         negative_threshold=args.negative_threshold, checkpoint=checkpoint)
    extra = {"duration_s": run.duration_s, "requests": run.requests, "input_tokens": run.input_tokens,
             "output_tokens": run.output_tokens, "tool_calls": run.tool_calls, "bash_calls": run.bash_calls,
             "final_text": run.final_text, "error": run.error, "work_cleanup_confirmed": run.cleanup_confirmed,
             "audit_configured": auditor_agent is not None, "max_submissions": args.max_submissions,
             "negative_threshold": args.negative_threshold, "early_stop": run.early_stop,
             "observations": list(run.observations), "request_limit": args.request_limit, "models": model_config}
    record = _record(run_dir, case, row, run.verdict, run.evaluations, mode="investigate", extra=extra)
    write_json(run_dir / "checkpoint.json", {"schema": "corsair-lite/checkpoint/1", "run_id": run_id,
                                            "state": "finished", "record": "run.json"})
    _print(record)
    return record


async def _investigate(args: argparse.Namespace) -> int:
    case = load_case(Path(args.case))
    config = load_provider_config(Path(args.provider))
    async with agent_models(config) as models:
        record = await _investigate_one(case, args, models, _models(config))
    print(json.dumps(record["verdict"], indent=2))
    return 0 if record["verdict"]["label"] == Label.LIKELY_EXPLOITABLE else 1


def _load_set(path: Path) -> tuple[list[Path], bool]:
    """Case directories of a frozen set file, and its held-out flag. Keys are relative to ``evals/e2e``; a case whose
    oracle no longer matches the digest recorded at freeze time is refused, so a relabelled case cannot slip in."""
    data = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent.parent
    dirs = []
    for key, digest in data["cases"].items():
        oracle = root / key / "oracle.json"
        if hashlib.sha256(oracle.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"{path}: the oracle for {key} changed since the set was frozen")
        dirs.append(root / key)
    return dirs, bool(data.get("held_out"))


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _telemetry(rows: list[dict], key: str) -> dict:
    """Totals over the runs that reported the field. A field no run reported is unknown (total None), never zero."""
    values = [row[key] for row in rows if row.get(key) is not None]
    total = sum(values) if values else None
    return {"reported_runs": len(values), "runs": len(rows), "total": total,
            "mean": _rate(total, len(values)) if values else None}


def summarise(rows: list[dict]) -> dict:
    """Accuracy, per-label precision and recall, the INCONCLUSIVE rate and usage over per-run rows. Accuracy uses the
    oracle's accepted labels (``correct``); precision and recall use its ``expected_label`` as the truth, and rows
    without one are left out of them."""
    scored = [row for row in rows if row["correct"] is not None]
    truthed = [row for row in rows if row["expected_label"]]
    per_label = {}
    for label in LABELS:
        tp = sum(1 for r in truthed if r["expected_label"] == label and r["label"] == label)
        fp = sum(1 for r in truthed if r["expected_label"] != label and r["label"] == label)
        fn = sum(1 for r in truthed if r["expected_label"] == label and r["label"] != label)
        per_label[label] = {"tp": tp, "fp": fp, "fn": fn, "precision": _rate(tp, tp + fp), "recall": _rate(tp, tp + fn)}
    counts = Counter(row["label"] for row in rows)
    correct = sum(1 for r in scored if r["correct"])
    return {"runs": len(rows), "scored_runs": len(scored), "correct_runs": correct,
            "accuracy": _rate(correct, len(scored)), "forbidden_hits": sum(1 for r in rows if r["forbidden_hit"]),
            "per_label": per_label, "label_counts": dict(sorted(counts.items())),
            "inconclusive_rate": _rate(counts.get("INCONCLUSIVE", 0), len(rows)),
            "telemetry": {key: _telemetry(rows, key) for key in TELEMETRY}}


def per_case(rows: list[dict]) -> list[dict]:
    """Per case over its repeats: label counts, the modal label and agreement (share of runs on the modal label)."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["case"], []).append(row)
    out = []
    for case, group in groups.items():
        counts = Counter(row["label"] for row in group)
        modal, modal_count = counts.most_common(1)[0]
        scored = [row for row in group if row["correct"] is not None]
        out.append({"case": case, "case_id": group[0]["case_id"], "expected_label": group[0]["expected_label"],
                    "runs": len(group), "label_counts": dict(sorted(counts.items())), "modal_label": modal,
                    "agreement": modal_count / len(group), "scored_runs": len(scored),
                    "accuracy": _rate(sum(1 for r in scored if r["correct"]), len(scored))})
    return out


def _models(config) -> dict:
    """The profile, model name and endpoint each agent ran on, so results are compared by model."""
    out = {}
    for agent, name in sorted(config.agents.items()):
        profile = config.profile(agent)
        out[agent] = {"profile": name, "model_name": profile.model_name, "base_url": profile.base_url,
                      "max_tokens": profile.max_tokens, "temperature": profile.temperature,
                      "thinking": profile.thinking, "thinking_token_budget": profile.thinking_token_budget}
    return out


async def _eval(args: argparse.Namespace) -> int:
    config = load_provider_config(Path(args.provider))
    if args.set:
        case_dirs, held_out = _load_set(Path(args.set))
    else:
        case_dirs, held_out = [Path(p) for p in args.cases], None
    rows = []
    async with agent_models(config) as models:
        for case_dir in case_dirs:
            case = load_case(case_dir)
            oracle = load_oracle(case_dir) or {}
            expected = oracle.get("expected_label")
            for repeat in range(1, args.repeats + 1):
                record = await _investigate_one(case, args, models, _models(config))
                label = record["verdict"]["label"]
                correct, forbidden_hit, note = score(case_dir.name, oracle, label)
                rows.append({"case": str(case_dir), "case_id": case.case_id, "repeat": repeat, "label": label,
                             "fix": record["verdict"]["fix"], "expected_label": expected,
                             "expected_fix": oracle.get("expected_fix"), "correct": correct,
                             "forbidden_hit": forbidden_hit, "policy_note": note,
                             "submissions": len(record["submissions"]), "early_stop": record.get("early_stop"),
                             "gates": [s["gate"]["stage"] for s in record["submissions"]],
                             "requests": record.get("requests"), "input_tokens": record.get("input_tokens"),
                             "output_tokens": record.get("output_tokens"), "tool_calls": record.get("tool_calls"),
                             "bash_calls": record.get("bash_calls"), "duration_s": record.get("duration_s"),
                             "run_id": record["run_id"]})
    summary = {"schema": "corsair-lite/eval/2", "provider": str(args.provider), "models": _models(config),
               "set": str(args.set) if args.set else None, "held_out": held_out, "cases": len(case_dirs),
               "repeats": args.repeats, "max_submissions": args.max_submissions,
               "negative_threshold": args.negative_threshold, "metrics": summarise(rows),
               "per_case": per_case(rows),
               "policy_divergences": [{"case_id": r["case_id"], "label": r["label"], "note": r["policy_note"]}
                                      for r in rows if r["policy_note"]],
               "gate_ledger": _ledger(rows), "runs": rows}
    out = Path(args.runs) / f"eval-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    write_json(out, summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("runs", "per_case")}, indent=2))
    print(f"written {out}", file=sys.stderr)
    return 0 if summary["metrics"]["forbidden_hits"] == 0 else 1


def score(name: str, oracle: dict, label: str) -> tuple[bool | None, bool, str | None]:
    """(correct, forbidden hit, policy note) for one case. ``correct`` is None when the oracle accepts no label or the
    case is not scored. An oracle's ``acceptable_labels`` (default: ``expected_label``) decide correctness, so a safe
    case is correct with LIKELY_NOT_EXPLOITABLE; ``forbidden_labels`` are the labels that would be a false positive."""
    expected = oracle.get("expected_label")
    accepted = set(oracle.get("acceptable_labels") or ([expected] if expected else []))
    forbidden = set(oracle.get("forbidden_labels") or [])
    note = None
    if name in LITE_CONTRACT:
        lite_accepted, note = LITE_CONTRACT[name]
        accepted, forbidden = set(lite_accepted or ()), set()
    return (label in accepted) if accepted else None, label in forbidden, note


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


async def _proposal(args: argparse.Namespace) -> int:
    from .kernel import GateVerdict
    from .producer import SKILLS_DIR
    from .seed import optimize_skills_from_trace, propose_seed

    config = load_provider_config(Path(args.provider))
    async with agent_models(config, ["producer"]) as models:
        if args.command == "seed":
            from .case import SafePath
            from pydantic import TypeAdapter
            target = TypeAdapter(SafePath).validate_python(args.target)
            case = load_case(Path(args.case))
            root = Path(case.revision.source).resolve()
            path = root / target
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("seed target must be a regular file inside the case revision")
            if path.stat().st_size > 64_000:
                raise ValueError("seed target exceeds 64 KB")
            proposal = await propose_seed(models["producer"], target, path.read_text(), args.vulnerability_class)
        else:
            record = json.loads(Path(args.trace).read_text())
            rejections = [GateVerdict.model_validate(s["gate"]) for s in record["submissions"] if not s["gate"]["passed"]]
            proposal = await optimize_skills_from_trace(models["producer"], record["verdict"]["label"], rejections, SKILLS_DIR)
    result = {"schema": "corsair-lite/proposal/1", "applied": False,
              "proposal": proposal.model_dump(mode="json") if proposal is not None else None}
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corsair", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="run the kernel on a supplied submission (no producer)")
    verify.add_argument("--case", required=True, help="case directory with input.json, or a request file")
    verify.add_argument("--submission", required=True, help="JSON file with hypothesis, build_script and probe")
    verify.add_argument("--provider", help="provider config; enables the blind auditor")
    verify.add_argument("--runs", default=str(RUNS))
    verify.add_argument("--run-id")
    verify.add_argument("--negative-threshold", type=_threshold, default=NEGATIVE_THRESHOLD,
                        help="distinct clean negatives that make LIKELY_NOT_EXPLOITABLE (operator-owned)")

    inv = sub.add_parser("investigate", help="run the producer against a case")
    inv.add_argument("--case", required=True)
    inv.add_argument("--provider", required=True)
    inv.add_argument("--max-submissions", type=_threshold, default=4)
    inv.add_argument("--request-limit", type=_threshold, default=60)
    inv.add_argument("--no-audit", action="store_true")
    inv.add_argument("--negative-threshold", type=_threshold, default=NEGATIVE_THRESHOLD,
                     help="distinct clean negatives that end the run as LIKELY_NOT_EXPLOITABLE (operator-owned)")
    inv.add_argument("--runs", default=str(RUNS))

    ev = sub.add_parser("eval", help="investigate several case directories and score them against oracle.json")
    source = ev.add_mutually_exclusive_group(required=True)
    source.add_argument("--cases", nargs="+", help="case directories")
    source.add_argument("--set", help="a frozen case set under evals/e2e/sets (dev or held-out)")
    ev.add_argument("--repeats", type=_repeats, default=1,
                    help="full investigations per case; repeats measure run-to-run agreement (default 1)")
    ev.add_argument("--provider", required=True)
    ev.add_argument("--max-submissions", type=_threshold, default=4)
    ev.add_argument("--request-limit", type=_threshold, default=60)
    ev.add_argument("--no-audit", action="store_true")
    ev.add_argument("--negative-threshold", type=_threshold, default=NEGATIVE_THRESHOLD,
                    help="distinct clean negatives that end a run as LIKELY_NOT_EXPLOITABLE (operator-owned)")
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
    if args.command in ("seed", "optimize-skills"):
        return asyncio.run(_proposal(args))
    if args.command == "verify":
        return asyncio.run(_verify(args))
    if args.command == "investigate":
        return asyncio.run(_investigate(args))
    if args.command == "eval":
        return asyncio.run(_eval(args))
    return _cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
