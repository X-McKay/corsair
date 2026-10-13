"""What an investigation returns besides its receipts: one record and one summary line. An eval case adds its
expected outcome and whether it matched; a cohort adds how many cases reached each stage. Nothing here branches on
a language.
"""
from collections import Counter
from pathlib import Path

from corsair.composition.direct import DirectRun

from .build import Investigation
from .docker import SETUP_NETWORK

# "admission": refused before any model request (request, acquisition, runtime selection or framework table).
STAGES = ("admission", "runtime", "environment", "identification", "planning", "authoring", "execution", "assessment",
          "complete")


# The headline label, one table (Al, 2026-10-13): what kind of outcome a run had, with the stage and reason under it.
# The eval match keeps comparing the three-part result, never this label.
FINDING_LABELS = {"reproduced": "LIKELY_EXPLOITABLE", "not_reproduced": "LIKELY_NOT_EXPLOITABLE",
                  "refuted_in_scope": "LIKELY_NOT_EXPLOITABLE", "inconclusive": "INCONCLUSIVE"}
EXECUTION_LABELS = {"failed": "ERROR", "unknown": "ERROR", "blocked": "UNABLE_TO_RUN", "unsupported": "UNABLE_TO_RUN"}
# Stops before the model stages for a case reason: the request, its runtime, route or environment cannot be run.
BEFORE_MODEL = ("admission", "runtime", "environment")
MODEL_STAGES = ("identification", "planning", "authoring", "assessment")
LABELS = ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE", "INCONCLUSIVE", "UNABLE_TO_RUN", "ERROR")


def headline(stopped_at: str | None, gate: dict | None, *, failed: bool = False, error: bool = False) -> str:
    """The run's label. `failed`: the stage that ended the run raised (provider, timeout, harness) instead of
    returning an outcome; `error`: the run itself crashed."""
    if error or failed:
        return "ERROR"
    if stopped_at in BEFORE_MODEL:
        return "UNABLE_TO_RUN"
    if stopped_at in MODEL_STAGES:
        return "INCONCLUSIVE"  # The chain ran; a stage's own outcome (blocked, unsupported, refused) settled nothing
    if stopped_at is not None or not gate:
        return "ERROR"  # Execution stopped, or a completed run without a gate
    return EXECUTION_LABELS.get(gate["execution"]) or FINDING_LABELS[gate["finding"]]


def _usage(run: DirectRun) -> dict:
    return {f"{index}-{a.stage}": {"requests": a.usage.requests if a.usage else None,
                                   "input_tokens": a.usage.input_tokens if a.usage else None,
                                   "output_tokens": a.usage.output_tokens if a.usage else None,
                                   "elapsed_seconds": round(a.elapsed_seconds, 1),
                                   "failure": None if a.failure is None else type(a.failure).__name__}
            for index, a in enumerate(run.attempts)}


def record(label: str, evidence: Path, *, investigation: Investigation | None = None, run: DirectRun | None = None,
           refused: str | None = None, error: str | None = None) -> dict:
    """`refused` is why the request could not start, `error` why the run crashed; otherwise `run` is the chain's
    result."""
    environment = run.environment if run is not None else None
    cleanup = {}
    if run is not None:
        cleanup = {"environment": next((a.cleanup for a in run.attempts if a.stage == "environment"), None),
                   **{e.revision: e.observed.cleanup if e.observed else "not_run" for e in run.executions}}
    outcomes = {e.revision: [[c.test_id, c.outcome] for c in e.observed.execution.cases]
                for e in (run.executions if run else ()) if e.observed and e.observed.execution}
    return {
        "issue": label,
        "revisions": None if investigation is None else investigation.commits,
        "selected": None if investigation is None else {
            "language": investigation.case.environment.language, "image_row": investigation.row,
            "image": investigation.image, "framework": investigation.framework.name,
            "runner": investigation.framework.runner, "route": "docker_image_only",
            # The framework row's own qualification; this route is plain Docker whatever the row says.
            "evidence": investigation.framework.qualification.evidence,
            "witness_recorders": [f.id for f in investigation.harness.witness_facilities]},
        # The route's own qualification: plain Docker never qualifies a result (PLAN-0081), whatever the row says.
        "sandbox": "docker", "qualification": "unqualified",
        "bases": None if investigation is None else investigation.bases,
        "setup_network": None if investigation is None else SETUP_NETWORK,
        "environment_framework": getattr(environment, "framework", None),
        # Which test proved the environment: the project's own test or the operator smoke test (SPEC-0071); None
        # when no environment was admitted.
        "baseline_basis": getattr(environment, "baseline_basis", None),
        "reached": "admission" if run is None else (run.stopped_at or "complete"),
        "stopped_at": "admission" if run is None else run.stopped_at,
        "reason": (error or refused) if run is None else run.reason,
        "gate": run.gate.permitted.model_dump() if run is not None and run.gate else None,
        "label": headline("admission" if run is None else run.stopped_at,
                          run.gate.permitted.model_dump() if run is not None and run.gate else None,
                          failed=run is not None and any(a.stage == run.stopped_at and a.failure is not None
                                                         for a in run.attempts),
                          error=error is not None),
        "outcomes": outcomes, "usage": {} if run is None else _usage(run), "cleanup": cleanup,
        "evidence": str(evidence)}


def summary_line(item: dict) -> str:
    """One line: the disposition and how it was reached, or where and why the run stopped."""
    selected = item["selected"]
    chosen = (f"{selected['image_row']} over plain Docker, {item['qualification']} (row evidence {selected['evidence']}), "
              f"{selected['framework']}"
              if selected else "nothing selected")
    requests = sum(u["requests"] or 0 for u in item["usage"].values())
    head = item["issue"]
    if item["revisions"]:
        head += f" @{item['revisions']['baseline'][:8]} (fix {item['revisions']['candidate'][:8]})"
    if item["stopped_at"] is None:
        gate = item["gate"] or {}
        outcome = "; ".join(f"{revision} " + ", ".join(f"{test.rsplit(':', 1)[-1]} {result}" for test, result in cases)
                            for revision, cases in item["outcomes"].items())
        state = f"{gate.get('execution')} · {gate.get('finding')} · {gate.get('fix')}; {outcome}"
    else:
        state = f"stopped at {item['stopped_at']}: {item['reason']}".replace("\n", " ")[:400]
    cleanup = "confirmed" if item["cleanup"] and all(v in ("confirmed", None, "not_run") for v in item["cleanup"].values()) \
        else ("unconfirmed" if item["cleanup"] else "none needed")
    return f"{head}: {item['label']}; {state} — {chosen}; {requests} model requests; cleanup {cleanup}; {item['evidence']}"


def with_expected(item: dict, case: str, expected) -> dict:
    """An eval case's record: the investigation's own record plus the expected outcome (`ChainOracle` or None, never
    read by the investigation) and whether it matched."""
    matches = None
    if expected is not None and item["reached"] != "admission":
        matches = item["stopped_at"] == expected.stopped_at and item["gate"] == (
            expected.gate.model_dump() if expected.gate else None)
    return item | {"case": case, "expected": None if expected is None else expected.model_dump(mode="json"),
                   "matches_expected": matches}


def cohort_summary(items: list[dict]) -> dict:
    """Cases reaching each stage, per language and in total; a case counts for every stage up to where it stopped."""
    def reached(group):
        counts = Counter()
        for item in group:
            counts.update(STAGES[:STAGES.index(item["reached"]) + 1])
        return {stage: counts[stage] for stage in STAGES}
    language = lambda item: (item["selected"] or {}).get("language") or "not selected"
    languages = sorted({language(item) for item in items})
    return {"cases": len(items), "total": reached(items),
            "by_language": {name: reached([i for i in items if language(i) == name]) for name in languages},
            "labels": {name: sum(item["label"] == name for item in items) for name in LABELS},
            "matches_expected": dict(Counter(str(item.get("matches_expected")) for item in items))}


def markdown(summary: dict) -> str:
    rows = ["| Language | " + " | ".join(STAGES) + " |", "| --- |" + " --- |" * len(STAGES)]
    for language, counts in [*summary["by_language"].items(), ("total", summary["total"])]:
        rows.append(f"| {language} | " + " | ".join(str(counts[stage]) for stage in STAGES) + " |")
    return "\n".join([f"Cases reaching each stage ({summary['cases']} cases)", "", *rows, ""])
