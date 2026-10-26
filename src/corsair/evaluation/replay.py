"""Trusted native replay of mismatching isolated producer proposals.

The isolated producer diagnostic scores a proposal by exact match against its frozen
oracle, so a semantically valid alternative payload is a retained mismatch. This module
replays each mismatching proposal through the real verification path (source admission,
``run_evidence`` and the configured sandbox) on the fixture's frozen request, and records
whether the pair demonstrates: a healthy control, a violating adversarial run and the
bound target line covered in both. The result is evidence for a human deciding whether
to admit a candidate into the oracle's allowed list. It never reads or writes an oracle,
never changes a row's pass/fail, and never reaches an agent, tool or workflow input.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from corsair.adapters.scm.local import prepare_case
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    EvidenceInput,
    FixStatus,
    InvestigationRequest,
    MatchKind,
    Observation,
    PreparedCase,
    ProducerOutput,
    digest,
)
from corsair.evaluation.datasets import dataset_root, read_frozen
from corsair.policies.verdicts import fix_status
from corsair.ports.sandboxing import SandboxPort
from corsair.settings import Settings
from corsair.steps.evidence import run_evidence
from corsair.steps.manifest import build_manifest

# Rows whose valid proposal differs from the frozen oracle; every other row is not replayed.
REPLAYED_KINDS = frozenset({MatchKind.CONTROL_MISMATCH, MatchKind.CANDIDATE_EXACT_MISMATCH})
REPLAY_NOTE = (
    "Native replay is evidence for a human oracle decision only: row pass/fail is unchanged, "
    "no oracle was read or modified, and a demonstrating candidate is not admitted until a "
    "reviewer adds it to the frozen oracle under a new digest."
)


def load_frozen_requests(path: Path) -> tuple[str, dict[str, tuple[Path, bytes]]]:
    """Read an isolated agent dataset and digest-verify each input; oracles stay unread."""
    dataset = json.loads(path.read_bytes())
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "corsair.agent-dataset/1":
        raise ValueError("replay requires an isolated agent dataset (corsair.agent-dataset/1)")
    entries = dataset.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("isolated dataset has no entries")
    root = dataset_root(path)
    inputs: dict[str, tuple[Path, bytes]] = {}
    for entry in entries:
        inputs[entry["case_id"]] = read_frozen(root, entry["input"], entry["input_digest"], "input")
    return digest(dataset), inputs


def replay_demonstrates(prepared: PreparedCase, observation: Observation) -> dict[str, Any]:
    """Classify one native observation with the kernel's own differential and coverage checks.

    ``fix_status`` classifies any validated pair: NOT_BLOCKED is a healthy control with a
    native violation, cleanup confirmed and the evidence artifact committed (the gate
    ledger reads it the same way). Coverage is the kernel's both-runs target-line gate, on
    the bound line (``PreparedCase.bound_line``) the kernel requires.
    """
    control, adversarial = observation.control, observation.adversarial
    line = prepared.bound_line
    covered = bool(
        line is not None
        and control is not None
        and adversarial is not None
        and line in control.covered_lines
        and line in adversarial.covered_lines
    )
    differential = fix_status(observation) is FixStatus.NOT_BLOCKED
    demonstrated = differential and covered and observation.source_digest == prepared.source.sha256
    return {
        "status": "demonstrated" if demonstrated else "not_demonstrated",
        "demonstrated": demonstrated,
        "control": None if control is None else control.outcome.value,
        "adversarial": None if adversarial is None else adversarial.outcome.value,
        "covered": covered,
        "cleanup_confirmed": observation.cleanup_confirmed,
        "gate": None if observation.feedback is None else observation.feedback.gate,
        "operation_id": observation.operation_id,
        "observation": None
        if observation.artifact is None
        else observation.artifact.model_dump(mode="json"),
    }


def _unavailable(reason: str, operation_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "demonstrated": None,
        "control": None,
        "adversarial": None,
        "covered": None,
        "cleanup_confirmed": None,
        "gate": None,
        "operation_id": operation_id,
        "observation": None,
        "reason": reason,
    }


def _replayable(row: dict[str, Any]) -> bool:
    try:
        return MatchKind(row.get("match_kind")) in REPLAYED_KINDS
    except ValueError:
        return False


def replay_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count replay outcomes; rows that were not replayed are counted, never dropped."""
    counts = {"demonstrated": 0, "not_demonstrated": 0, "unavailable": 0, "not_replayed": 0}
    for row in rows:
        replay = row.get("replay")
        counts[replay["status"] if isinstance(replay, dict) else "not_replayed"] += 1
    return counts


async def replay_candidates(
    report: dict[str, Any],
    dataset: Path,
    settings: Settings,
    store: ArtifactStore,
    sandbox: SandboxPort,
    *,
    replay_id: str,
) -> dict[str, Any]:
    """Return a copy of ``report`` whose rows gain a ``replay`` entry; pass/fail is untouched."""
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("report has no rows to replay")
    if any(row.get("agent") != "producer" for row in rows):
        raise ValueError("replay-candidates replays isolated producer reports only")
    dataset_digest, inputs = load_frozen_requests(dataset)
    if report.get("dataset_digest") != dataset_digest:
        raise ValueError("report dataset digest differs from DATASET; replay the matching dataset")
    image_id: str | None = None
    prepared_cases: dict[str, tuple[PreparedCase, InvestigationRequest]] = {}
    replayed = copy.deepcopy(report)
    for index, row in enumerate(replayed["rows"]):
        if not _replayable(row):
            row["replay"] = None
            continue
        operation_id = f"{replay_id}.c{index}"
        case_id = row.get("case_id")
        if case_id not in inputs:
            row["replay"] = _unavailable("case is not in the frozen dataset", operation_id)
            continue
        try:
            output = ProducerOutput.model_validate(
                store.get_json(ArtifactRef.model_validate(row.get("output_artifact")))
            )
        except (OSError, ValueError, KeyError, TypeError):
            row["replay"] = _unavailable("producer output artifact is unavailable", operation_id)
            continue
        submission = output.submission_for_verification()
        if submission is None:
            row["replay"] = _unavailable("producer output has no submission", operation_id)
            continue
        if case_id not in prepared_cases:
            path, content = inputs[case_id]
            request = normalize_request_sources(
                InvestigationRequest.model_validate_json(content), path
            )
            if image_id is None:
                # Resolved only once a proposal needs native replay.
                image_id = await asyncio.to_thread(lambda: sandbox.image_id)
            manifest = build_manifest(request, settings, image_id)
            prepared = await asyncio.to_thread(
                prepare_case, request.case, settings, store, manifest
            )
            prepared_cases[case_id] = (prepared, request)
        prepared, request = prepared_cases[case_id]
        observation = await run_evidence(
            EvidenceInput(
                run_id=replay_id,
                operation_id=operation_id,
                prepared=prepared,
                submission=submission,
                budget=request.budget,
            ),
            settings,
            store,
            sandbox=sandbox,
        )
        row["replay"] = replay_demonstrates(prepared, observation)
    replayed["summary"]["replay"] = replay_summary(replayed["rows"])
    replayed["replay_id"] = replay_id
    replayed["replay_note"] = REPLAY_NOTE
    return replayed
