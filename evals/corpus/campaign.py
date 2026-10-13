"""Finite development corpus batches through the existing product runner, without retries.

Prepare writes every planned slot before dispatch. Run processes only planned slots, serially, with an explicit
slot limit. Started slots with no final product record remain unknown; repeats require a fresh campaign directory.
All labels and expectations stay evaluator-owned. Docker remains unqualified.
"""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import traceback
import fcntl

from corsair.composition.direct import CompositionBudget
from corsair.composition.receipts import AGENT_STAGES, VERSION_FIELDS, VERSIONS
from corsair.inference.config import inference_config, load_inference
from corsair.investigate import images, investigate
from corsair.investigation.request import IssueRequest
from corsair.investigation.results import LABELS, cohort_summary, markdown
from evals.corpus.cases import HELD_OUT, case_digest, load
from evals.corpus.issues import capture
from evals.run import _git


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def identity(provider: Path, image_file: Path, profiles: Path | None, timeout: int) -> dict:
    """What a comparison holds fixed: committed source, per-stage provider settings (no secrets: keys are env names),
    images, stage profiles, timeout and the composition budget. Uncommitted source has no identity."""
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit the source before freezing or running a campaign")
    config = load_inference(provider)
    return {"git_commit": _git("rev-parse", "HEAD"),
            "stage_providers": {stage: inference_config(config).resolve(stage).model_dump(mode="json")
                                for stage in AGENT_STAGES},
            "images": images(image_file), "stage_profiles": json.loads(profiles.read_bytes()) if profiles else None,
            "timeout_seconds": timeout, "max_concurrency": 1,
            "budget": CompositionBudget().model_dump(),
            "versions": {stage: dict(zip(VERSION_FIELDS, VERSIONS[stage])) for stage in AGENT_STAGES}}


def prepare(directory: Path, case_ids: list[str], provider: Path, image_file: Path, *, repeat: int = 1,
            profiles: Path | None = None, timeout: int = 600) -> dict:
    """Freeze positive pairs and independent candidate-only negatives in an exclusive private directory."""
    if repeat < 1 or timeout < 1 or not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("select distinct cases and positive repeat/timeout values")
    cases = load(split="development", case_ids=set(case_ids))
    by_id = {case.case_id: case for case in cases}
    if set(by_id) != set(case_ids):
        raise ValueError("campaigns select development cases only")
    frozen_identity = identity(provider, image_file, profiles, timeout)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    sources = directory / "sources"
    slots = []
    for index, case_id in enumerate(case_ids, 1):
        case = by_id[case_id]
        variants = [("positive_pair" if case.candidate else "baseline_only", case)]
        if case.candidate:
            variants.append(("negative_baseline", replace(case, finding=case.candidate.finding,
                                                         baseline=case.candidate, candidate=None)))
        for direction, selected in variants:
            opaque = f"item-{index:03d}-{len(slots):03d}"
            request, _ = capture(selected, sources, materialized_id=opaque)
            for repetition in range(1, repeat + 1):
                slot_id = f"attempt-{len(slots) + 1:04d}"
                slot = {"id": slot_id, "case": case_id, "language": case.language, "topic": str(case.topic),
                        "cwe": case.finding.cwe, "direction": direction, "repeat": repetition,
                        "case_sha256": case_digest(case), "issue": str((sources / opaque / "issue.json").resolve()),
                        "issue_sha256": _digest(sources / opaque / "issue.json"), "revision": request["revision"],
                        "fixed_revision": request.get("fixed_revision"),
                        "expected": selected.oracle.gate.model_dump(), "oracle_confidence": "upstream_hypothesis"}
                slots.append(slot)
    manifest = {"schema": "corsair-corpus-campaign/v1", "split": "development", "qualification": "unqualified",
                "sandbox": "docker", "held_out_manifest_sha256": _digest(HELD_OUT),
                "dataset_sha256": sha256(json.dumps([{k: v for k, v in slot.items()
                                                      if k not in {"issue", "issue_sha256"}}
                                                     for slot in slots], sort_keys=True).encode()).hexdigest(),
                "identity": frozen_identity, "slots": slots}
    _write(directory / "manifest.json", manifest)
    for slot in slots:
        _write(directory / (slot["id"] + ".json"), {"id": slot["id"], "status": "planned"})
    report(directory)
    return manifest


def _completed(slot: dict, attempt: dict, item: dict) -> dict:
    # The exact comparison uses the admitted final disposition, never the gate ceiling.
    admitted = item.get("label_basis") == "assessment_admitted"
    return attempt | {"status": "completed", "delivery": "returned", "record": item,
                      "matches_expected_final": item.get("final") == slot["expected"] if admitted else None}


def report(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    attempts = [json.loads((directory / (s["id"] + ".json")).read_text()) for s in manifest["slots"]]
    items = [a["record"] for a in attempts if a.get("record")]
    states = Counter(a["status"] for a in attempts)
    result = {"planned": len(attempts), "topics": len({s["case"] for s in manifest["slots"]}),
              "status": dict(states), "product": cohort_summary(items),
              "continuation_blocked_by": next((a["id"] for a in attempts if not _safe_to_continue(a)), None),
              "exact_final": dict(Counter(str(a.get("matches_expected_final")) for a in attempts)),
              "oracle_confidence": "upstream_hypothesis", "qualification": "unqualified"}
    table = {direction: dict(Counter(a.get("record", {}).get("label", a["status"])
                                    for s, a in zip(manifest["slots"], attempts) if s["direction"] == direction))
             for direction in sorted({s["direction"] for s in manifest["slots"]})}
    result["outcomes_by_direction"] = table
    efficiency = {}
    for metric in ("requests", "input_tokens", "output_tokens"):
        observed = [u[metric] for item in items for u in item.get("usage", {}).values()
                    if u.get(metric) is not None]
        if metric.endswith("tokens"):
            # Product RunUsage currently has no provider coverage flag. Zero defaults cannot prove zero billing;
            # positive values remain useful partial observations without claiming a complete measured total.
            positive = [value for value in observed if value > 0]
            efficiency[metric] = {"provider_coverage": "unknown", "total": None,
                                  "positive_stage_values": len(positive),
                                  "partial_nonzero_total": sum(positive) if positive else None}
        else:
            efficiency[metric] = {"observed_stage_values": len(observed), "total": sum(observed) if observed else None}
    elapsed = [a["elapsed_seconds"] for a in attempts if a.get("elapsed_seconds") is not None]
    efficiency["elapsed_seconds"] = {"observed_attempts": len(elapsed), "planned_attempts": len(attempts),
                                     "total": sum(elapsed) if elapsed else None}
    result["observed_efficiency"] = efficiency
    _write(directory / "summary.json", result)
    lines = [f"Planned attempts: {len(attempts)}; topics: {result['topics']}; Docker unqualified.",
             f"Attempt states: {dict(states)}", "", "Oracle expectations are upstream hypotheses; matches are not semantic qualification.", "",
             "| Direction | " + " | ".join(LABELS) + " | Other |", "| --- |" + " --- |" * (len(LABELS) + 1)]
    for direction, counts in table.items():
        lines.append(f"| {direction} | " + " | ".join(str(counts.get(label, 0)) for label in LABELS)
                     + f" | {sum(v for k, v in counts.items() if k not in LABELS)} |")
    (directory / "summary.md").write_text("\n".join(lines) + "\n\n" + markdown(result["product"]))
    return result


def _safe_to_continue(attempt: dict) -> bool:
    if attempt["status"] in {"unknown", "started", "failed"}:
        return False
    item = attempt.get("record")
    if item is None:
        return True
    if item.get("reached") == "admission" and item.get("selected") is None and not item.get("crashed"):
        return True  # Known pre-dispatch refusal, including the current fix-free admission blocker.
    cleanup = item.get("cleanup")
    return bool(cleanup) and all(value in ("confirmed", "not_run") for value in cleanup.values())


def _run(directory: Path, provider: Path, image_file: Path, *, slots: int, profiles: Path | None = None,
         timeout: int = 600, dispatcher=investigate) -> dict:
    """Dispatch at most `slots` demonstrably unstarted slots. A started attempt is never automatically rerun."""
    if slots < 1:
        raise ValueError("an explicit positive slot limit is required")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["identity"] != identity(provider, image_file, profiles, timeout):
        raise ValueError("source/provider/images/settings differ from the frozen campaign; prepare a fresh campaign")
    if manifest["held_out_manifest_sha256"] != _digest(HELD_OUT):
        raise ValueError("held-out manifest changed")
    config, prepared = load_inference(provider), images(image_file)
    stage_profiles = json.loads(profiles.read_bytes()) if profiles else None
    dispatched = 0
    for slot in manifest["slots"]:
        receipt = directory / (slot["id"] + ".json")
        attempt = json.loads(receipt.read_text())
        evidence = directory / slot["id"] / "investigation"
        if attempt["status"] in {"started", "unknown"}:
            final = evidence / "record.json"
            # Reconcile a final native record only when its request is byte-identical to the frozen input.
            try:
                if _digest(Path(slot["issue"])) != slot["issue_sha256"]:
                    raise ValueError("frozen input changed")
                item = json.loads(final.read_text())
                saved_request = IssueRequest.model_validate_json((evidence / "request.json").read_bytes())
                request = IssueRequest.model_validate_json(Path(slot["issue"]).read_bytes())
                if saved_request != request or not isinstance(item, dict) or "label" not in item:
                    raise ValueError("record/request mismatch")
                attempt = _completed(slot, attempt, item)
            except (OSError, ValueError):
                attempt |= {"status": "unknown", "delivery": "unknown", "reason": "started without a reconciled final record"}
            _write(receipt, attempt)
        if not _safe_to_continue(attempt):
            break  # Preserve ownership uncertainty; no more side effects until explicit receipt reconciliation.
        if attempt["status"] != "planned" or dispatched >= slots:
            continue
        if _digest(Path(slot["issue"])) != slot["issue_sha256"] or evidence.parent.exists():
            raise ValueError("planned slot input changed or evidence already exists; reconcile manually")
        started = perf_counter()
        attempt |= {"status": "started", "started_at": datetime.now(timezone.utc).isoformat(), "delivery": "unknown"}
        _write(receipt, attempt)
        dispatched += 1
        try:
            request = IssueRequest.model_validate_json(Path(slot["issue"]).read_bytes())
            item = dispatcher(request, evidence, prepared, roots=((directory / "sources").resolve(),),
                              config=config, profiles=stage_profiles, timeout=timeout)
            attempt = _completed(slot, attempt, item)
        except Exception as error:
            attempt |= {"status": "failed", "failure_layer": "campaign_dispatch", "failure_type": type(error).__name__,
                        "delivery": "unknown", "reason": str(error)[:2048]}
            (directory / (slot["id"] + "-error.txt")).write_text(traceback.format_exc())
        finally:
            attempt["elapsed_seconds"] = round(perf_counter() - started, 3)
            _write(receipt, attempt)
            report(directory)
        if not _safe_to_continue(attempt):
            break
    return report(directory)


def run(directory: Path, provider: Path, image_file: Path, *, slots: int, profiles: Path | None = None,
        timeout: int = 600, dispatcher=investigate) -> dict:
    """A native exclusive lock prevents two invocations dispatching the same planned slot."""
    directory = directory.resolve()  # Native artifact storage requires an absolute operator-owned evidence root.
    with (directory / ".dispatch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("campaign already has an active dispatcher") from error
        return _run(directory, provider, image_file, slots=slots, profiles=profiles, timeout=timeout,
                    dispatcher=dispatcher)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--slots", type=int)
    parser.add_argument("--provider-config", type=Path)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--stage-profiles", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    if args.action == "report":
        result = report(args.directory)
    else:
        if not args.provider_config or not args.images:
            parser.error("prepare/run require --provider-config and --images")
        if args.action == "prepare":
            result = prepare(args.directory, args.case, args.provider_config, args.images, repeat=args.repeat,
                             profiles=args.stage_profiles, timeout=args.timeout)
            result = report(args.directory)
        else:
            if args.slots is None:
                parser.error("run requires --slots")
            result = run(args.directory, args.provider_config, args.images, slots=args.slots,
                         profiles=args.stage_profiles, timeout=args.timeout)
    print(json.dumps({k: result[k] for k in ("planned", "topics", "status") if k in result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
