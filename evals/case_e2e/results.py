"""One result line per case and the cohort roll-up: what was selected, how far the chain got and why, the outcome
against the evaluator's expectation, model usage, cleanup and where the receipts are.

A line is evaluator output: it may name the case id and expected outcome, which never reach an agent.
"""
from collections import Counter
from pathlib import Path

from corsair.composition.direct import DirectRun

from .case import CaseRun

# "case": refused before any model request (no manifest fields, commits, selected runtime or harness).
STAGES = ("case", "runtime", "environment", "identification", "planning", "authoring", "execution", "assessment",
          "complete")


def _usage(run: DirectRun) -> dict:
    return {f"{index}-{a.stage}": {"requests": a.usage.requests if a.usage else None,
                                   "input_tokens": a.usage.input_tokens if a.usage else None,
                                   "output_tokens": a.usage.output_tokens if a.usage else None,
                                   "elapsed_seconds": round(a.elapsed_seconds, 1),
                                   "failure": None if a.failure is None else type(a.failure).__name__}
            for index, a in enumerate(run.attempts)}


def result_line(case_id: str, language: str, expected, evidence: Path, *, prepared: CaseRun | None = None,
                run: DirectRun | None = None, refused: str | None = None) -> dict:
    """`expected` is the manifest's chain oracle or None (unknown); `refused` is why the case could not start."""
    reached = "case" if run is None else (run.stopped_at or "complete")
    gate = run.gate.permitted.model_dump() if run is not None and run.gate else None
    matches = None
    if expected is not None and run is not None:
        matches = run.stopped_at == expected.stopped_at and gate == (expected.gate.model_dump() if expected.gate else None)
    environment = run.environment if run is not None else None
    cleanup = {}
    if run is not None:
        cleanup = {"environment": next((a.cleanup for a in run.attempts if a.stage == "environment"), None),
                   **{e.revision: e.observed.cleanup if e.observed else "not_run" for e in run.executions}}
    return {
        "case": case_id, "language": language,
        "selected": None if prepared is None else {
            "image_row": prepared.row, "image": prepared.image, "framework": prepared.framework.name,
            "runner": prepared.framework.runner, "evidence": prepared.framework.qualification.evidence,
            "witness_recorders": [f.id for f in prepared.harness.witness_facilities]},
        "environment_framework": getattr(environment, "framework", None),
        # Which test proved the environment: "project" (the environment stage's existing test) or "operator_smoke"
        # (the corpus thread's smoke test, not yet wired); None when no environment was admitted.
        "baseline_basis": "project" if getattr(environment, "status", None) == "ready" else None,
        "reached": reached, "stopped_at": None if run is None else run.stopped_at,
        "reason": refused if run is None else run.reason, "gate": gate,
        "expected": None if expected is None else expected.model_dump(mode="json"), "matches_expected": matches,
        "usage": {} if run is None else _usage(run), "cleanup": cleanup, "evidence": str(evidence)}


def cohort_summary(lines: list[dict]) -> dict:
    """Cases reaching each stage, per language and in total; a case counts for every stage up to where it stopped."""
    def reached(group):
        counts = Counter()
        for line in group:
            counts.update(STAGES[:STAGES.index(line["reached"]) + 1])
        return {stage: counts[stage] for stage in STAGES}
    languages = sorted({line["language"] for line in lines})
    return {"cases": len(lines), "total": reached(lines),
            "by_language": {language: reached([l for l in lines if l["language"] == language]) for language in languages},
            "matches_expected": Counter(str(line["matches_expected"]) for line in lines)}


def markdown(summary: dict) -> str:
    rows = ["| Language | " + " | ".join(STAGES) + " |", "| --- |" + " --- |" * len(STAGES)]
    for language, counts in [*summary["by_language"].items(), ("total", summary["total"])]:
        rows.append(f"| {language} | " + " | ".join(str(counts[stage]) for stage in STAGES) + " |")
    return "\n".join([f"Cases reaching each stage ({summary['cases']} cases)", "", *rows, ""])
