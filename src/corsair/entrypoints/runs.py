"""Read-only navigation of committed results and their evidence receipts.

Nothing here writes to the artifact store or decides a label. Listing and evidence views
report what was committed; payloads, source excerpts, findings (beyond their declared and
bound line numbers) and driver jobs never leave the store through them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    TERMINAL_RESULT_MAX_BYTES,
    ArtifactRef,
    InvestigationResult,
    Observation,
    RoleObservation,
    Submission,
    digest,
)
from corsair.evaluation.ledger import gate_ledger, verified_rounds
from corsair.policies.explanation import explain_result
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier

_RESULT_SCHEMA = "corsair.result/1"
_ROLES = ("control", "adversarial")


def _recorded_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="seconds")


def _committed_result(
    store: ArtifactStore, key: str, ref: ArtifactRef
) -> InvestigationResult | None:
    """Return a result only if it was committed under its own ``result.<run_id>`` name.

    Raises ``ValueError`` for a result-shaped record that fails validation or binding.
    """
    if ref.media_type != "application/json" or ref.size > TERMINAL_RESULT_MAX_BYTES:
        return None
    value = store.get_json(ref)
    if not isinstance(value, dict) or value.get("schema_version") != _RESULT_SCHEMA:
        return None
    result = InvestigationResult.model_validate(value)
    if store.operation_key(f"result.{result.run_id}") != key:
        raise ValueError("result is not committed under its own run identity")
    return result


def list_runs(
    store: ArtifactStore, *, case_id: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """List committed results newest first, counting records that cannot be admitted."""
    rows: list[dict[str, Any]] = []
    invalid = 0
    for key, recorded, ref in store.operation_records():
        if ref is None:
            invalid += 1
            continue
        try:
            result = _committed_result(store, key, ref)
        except (OSError, ValueError):
            invalid += 1
            continue
        if result is None or (case_id is not None and result.case_id != case_id):
            continue
        rows.append(
            {
                "run_id": result.run_id,
                "case_id": result.case_id,
                "verdict": result.verdict,
                "execution_status": result.execution_status,
                "fix_status": result.fix_status,
                "rounds": len(result.rounds),
                "recorded_at": _recorded_at(recorded),
                "result_sha256": ref.sha256,
            }
        )
    # Every record is scanned so the invalid count describes the whole store.
    return {"runs": rows[:limit], "invalid_records": invalid}


def _role_receipt(
    store: ArtifactStore,
    raw_ref: object,
    observed: RoleObservation | None,
    *,
    operation_id: str,
    role: str,
) -> dict[str, Any]:
    """Summarize one role: the admitted observation plus its raw container receipt."""
    entry: dict[str, Any] = {
        "outcome": observed.outcome if observed else None,
        "target_executed": observed.target_executed if observed else None,
        "covered_lines": observed.covered_lines if observed else [],
        "native_exit_code": observed.native_exit_code if observed else None,
        "receipt": "absent",
    }
    if raw_ref is None:
        return entry
    try:
        ref = ArtifactRef.model_validate(raw_ref)
        raw = store.get_json(ref)
    except (OSError, ValueError):
        entry["receipt"] = "unreadable"
        return entry
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != "corsair.raw-evidence/1"
        or raw.get("operation_id") != operation_id
        or raw.get("role") != role
    ):
        entry["receipt"] = "identity_mismatch"
        return entry
    # Allowlisted receipt fields only: the driver record and job never leave the store.
    entry.update(
        receipt="present",
        raw_sha256=ref.sha256,
        cleanup_confirmed=raw.get("cleanup_confirmed") is True,
        container_id=raw.get("container_id") or None,
        image_id=raw.get("image_id"),
        docker_exit_code=raw.get("docker_exit_code"),
    )
    return entry


def _observation_view(
    store: ArtifactStore,
    verifier: EvidenceVerifier,
    result: InvestigationResult,
    observation: Observation,
    submission: Submission | None,
    *,
    fixed: bool,
) -> dict[str, Any]:
    """Walk one observation to its committed record, evidence bundle and raw receipts."""
    committed = store.reconcile(observation.operation_id)
    try:
        matches = committed is not None and (
            Observation.model_validate(store.get_json(committed)) == observation
        )
    except (OSError, ValueError):
        matches = False
    view: dict[str, Any] = {
        "operation_id": observation.operation_id,
        "fixed": fixed,
        "committed": matches,
        "cleanup_confirmed": observation.cleanup_confirmed,
        "gate": observation.feedback.gate if observation.feedback else None,
        "evidence_sha256": observation.artifact.sha256 if observation.artifact else None,
        "evidence": "absent",
        "receipts_admissible": None,
        "target_line": None,
        "declared_line": None,
        "line_provenance": None,
    }
    roles: Any = {}
    if observation.artifact is not None:
        try:
            bundle = store.get_json(observation.artifact)
        except (OSError, ValueError):
            bundle = None
        if (
            isinstance(bundle, dict)
            and bundle.get("schema_version") == "corsair.evidence/1"
            and bundle.get("operation_id") == observation.operation_id
            and isinstance(bundle.get("roles"), dict)
        ):
            view["evidence"], roles = "present", bundle["roles"]
        else:
            view["evidence"] = "unreadable"
    if submission is not None and result.manifest is not None:
        prepared = verifier.validate_saved(
            observation, submission, result.manifest, expected_fixed=fixed
        )
        view["receipts_admissible"] = prepared is not None
        if prepared is not None:
            # The line the kernel's coverage gate checked, the finding line it was bound
            # from, and whether trusted prepare code derived that line from the recipe
            # function; never the finding's text.
            view["target_line"] = prepared.bound_line
            view["declared_line"] = prepared.finding.line
            view["line_provenance"] = prepared.line_provenance
    view["roles"] = {
        role: _role_receipt(
            store,
            roles.get(role),
            getattr(observation, role),
            operation_id=observation.operation_id,
            role=role,
        )
        for role in _ROLES
    }
    return view


def inspect_evidence(store: ArtifactStore, result: InvestigationResult) -> dict[str, Any]:
    """Per-observation evidence view of a committed result, never its payloads."""
    verifier = EvidenceVerifier(Settings(), store)
    observations: list[dict[str, Any]] = []
    submissions: dict[str, Submission] = {}
    for item in result.rounds:
        submission = item.producer.submission_for_verification()
        if submission is not None:
            submissions.setdefault(digest(submission), submission)
        if item.observation is None:
            continue
        view = _observation_view(store, verifier, result, item.observation, submission, fixed=False)
        observations.append({"session": item.session, "round": item.index, **view})
    if result.fix_observation is not None:
        fixed = result.fix_observation
        view = _observation_view(
            store, verifier, result, fixed, submissions.get(fixed.submission_digest), fixed=True
        )
        observations.append({"session": None, "round": None, **view})
    return {
        "run_id": result.run_id,
        "case_id": result.case_id,
        "verdict": result.verdict,
        "execution_status": result.execution_status,
        "fix_status": result.fix_status,
        "observations": observations,
    }


def explain_run(store: ArtifactStore, result: InvestigationResult) -> dict[str, Any]:
    """Plain-language statements for a committed result, from its re-validated gate ledger."""
    ledger = gate_ledger(result, verified_rounds(result, store))
    return {
        "run_id": result.run_id,
        "case_id": result.case_id,
        "verdict": result.verdict,
        "statements": explain_result(result, ledger),
    }
