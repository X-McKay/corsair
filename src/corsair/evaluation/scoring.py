"""External evaluator: oracle files are never passed to agents, tools or workflows."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Contract,
    Digest,
    Disposition,
    ExecutionStatus,
    FixStatus,
    InvestigationRequest,
    InvestigationResult,
    Verdict,
    digest,
)
from corsair.evaluation.ledger import gate_ledger, ledger_counts, row_ledger, verified_rounds
from corsair.policies.verdicts import decide, fix_status, session_verdict
from corsair.settings import Settings

if TYPE_CHECKING:
    from corsair.steps.verification import EvidenceVerifier

# A case is "correctly resolved" only when the canonical label decided by code is a
# decisive demonstration or non-demonstration -- never the internal disposition, and
# never INCONCLUSIVE / UNABLE_TO_RUN / ERROR.
_DECISIVE_VERDICTS = frozenset(
    {
        Verdict.EXPLOIT_DEMONSTRATED,
        Verdict.COMPONENT_EXPLOIT_DEMONSTRATED,
        Verdict.EXPLOIT_NOT_DEMONSTRATED,
    }
)


class Oracle(Contract):
    acceptable: list[Disposition] = Field(min_length=1)
    forbidden: list[Disposition] = Field(default_factory=list)
    expected_execution: ExecutionStatus = ExecutionStatus.COMPLETED
    expected_fix: FixStatus | None = None
    # Canonical case-label expectations. Omitted means the oracle does not score
    # the verdict (older Disposition-only oracles keep passing unchanged).
    expected_verdict: Verdict | None = None
    acceptable_verdicts: list[Verdict] | None = None
    forbidden_verdicts: list[Verdict] = Field(default_factory=list)

    def verdict_allowed(self, verdict: Verdict | None) -> bool:
        """Whether a result's canonical verdict satisfies this oracle."""
        if self.acceptable_verdicts is None and self.expected_verdict is None:
            return verdict not in self.forbidden_verdicts
        if verdict is None:
            return False
        if self.acceptable_verdicts is not None and verdict not in self.acceptable_verdicts:
            return False
        if self.expected_verdict is not None and verdict != self.expected_verdict:
            return False
        return verdict not in self.forbidden_verdicts


class DatasetEntry(Contract):
    case_id: str
    family: str
    request: str
    oracle: str
    request_digest: Digest
    oracle_digest: Digest
    split: str


class Dataset(Contract):
    schema_version: str = "corsair.dataset/1"
    entries: list[DatasetEntry] = Field(min_length=1, max_length=64)


def dataset_root(path: Path) -> Path:
    # Reference-layout manifests in evals/datasets address the enclosing evals tree.
    parent = path.parent.resolve()
    return parent.parent if parent.name == "datasets" else parent


def _read_frozen_file(root: Path, relative: str, expected: Digest, kind: str) -> tuple[Path, bytes]:
    """Read once and verify the exact bytes that the evaluator will parse."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("dataset path escapes its root or is missing")
    content = path.read_bytes()
    if digest(content) != expected:
        raise ValueError(f"frozen {kind} digest changed")
    return path, content


def load_dataset(path: Path) -> tuple[Dataset, list[InvestigationRequest], dict[str, Oracle]]:
    """Verify the frozen files first. Return oracle data only to the evaluator caller."""
    dataset = Dataset.model_validate_json(path.read_bytes())
    root = dataset_root(path)
    requests, oracles = [], {}
    family_splits: dict[str, str] = {}
    for entry in dataset.entries:
        if entry.case_id in oracles:
            raise ValueError("duplicate case identity")
        if entry.family in family_splits and family_splits[entry.family] != entry.split:
            raise ValueError("related family variants may not cross dataset splits")
        family_splits[entry.family] = entry.split
        request_path, request_bytes = _read_frozen_file(
            root, entry.request, entry.request_digest, "request"
        )
        _, oracle_bytes = _read_frozen_file(root, entry.oracle, entry.oracle_digest, "oracle")
        request = InvestigationRequest.model_validate_json(request_bytes)
        if request.case.case_id != entry.case_id:
            raise ValueError("dataset and request case identities disagree")
        requests.append(normalize_request_sources(request, request_path))
        oracles[entry.case_id] = Oracle.model_validate_json(oracle_bytes)
    return dataset, requests, oracles


def _saved_evidence_verifier(store: ArtifactStore) -> "EvidenceVerifier":
    """Revalidate saved receipts; imported on use because verification loads the Docker SDK."""
    from corsair.steps.verification import EvidenceVerifier

    return EvidenceVerifier(Settings(), store)


def valid_positive_evidence(result: InvestigationResult, store: ArtifactStore | None) -> bool:
    if result.manifest is None or store is None:
        return False
    verifier = _saved_evidence_verifier(store)
    for item in result.rounds:
        observation, audit = item.observation, item.audit
        submission = item.producer.submission_for_verification()
        if observation is None or submission is None or audit is None:
            continue
        prepared = verifier.validate_saved(observation, submission, result.manifest)
        if (
            prepared is not None
            and prepared.case_id == result.case_id
            and decide(prepared, observation, audit)[0] == result.disposition
        ):
            return True
    return False


def valid_negative_evidence(result: InvestigationResult, store: ArtifactStore | None) -> bool:
    """A negative label is only valid when it rests on at least the admitted
    ``negative_threshold`` of independent, validated clean sessions.

    Each qualifying session must revalidate: its committed receipts verify, the
    finding's exact line was covered in both runs, the audit accepted, the control
    held, and the exploit did NOT violate. Receipts are grouped by independent
    session; a missing manifest, store, or receipt is a validation failure, never a
    free pass. This is the costliest error to get wrong, so empty or partial
    evidence can never clear it."""
    if result.manifest is None or store is None:
        return False
    verifier = _saved_evidence_verifier(store)
    clean_sessions: set[int] = set()
    for item in result.rounds:
        observation, audit = item.observation, item.audit
        submission = item.producer.submission_for_verification()
        if observation is None or submission is None or audit is None:
            continue
        prepared = verifier.validate_saved(observation, submission, result.manifest)
        if prepared is None or prepared.case_id != result.case_id:
            continue
        # The fixed revision is irrelevant to a clean negative; NOT_REQUESTED keeps
        # the clean-negative gate independent of any fix differential.
        if session_verdict(prepared, observation, audit, FixStatus.NOT_REQUESTED).clean_negative:
            clean_sessions.add(item.session)
    return len(clean_sessions) >= result.manifest.negative_threshold


def valid_evidence(result: InvestigationResult, store: ArtifactStore | None) -> bool:
    """Validate a result's evidence against its code-decided canonical verdict.

    Evidence validation is dispatched by the verdict, not the internal disposition,
    and disposition/verdict combinations the kernel can never produce are rejected:
    a positive disposition never aggregates to a negative label, and a positive
    disposition that did not yield a positive label is inconsistent. Non-decisive
    labels assert nothing about demonstration, so there is nothing to validate."""
    verdict = result.verdict
    positive_disposition = result.disposition in {Disposition.SUPPORTED, Disposition.CONDITIONAL}
    if verdict in {Verdict.EXPLOIT_DEMONSTRATED, Verdict.COMPONENT_EXPLOIT_DEMONSTRATED}:
        return positive_disposition and valid_positive_evidence(result, store)
    if verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED:
        return not positive_disposition and valid_negative_evidence(result, store)
    # No decisive label. A positive disposition still asserts a demonstration and must
    # carry validated positive evidence (the legacy disposition-only path); any other
    # non-decisive outcome asserts nothing to validate.
    if positive_disposition:
        return valid_positive_evidence(result, store)
    return True


def score(result: InvestigationResult, oracle: Oracle, store: ArtifactStore | None = None) -> dict:
    """One final-policy result, including invalid evidence and operational failures."""
    evidence_valid = valid_evidence(result, store)
    allowed = result.disposition in oracle.acceptable and result.disposition not in oracle.forbidden
    fix_correct = oracle.expected_fix is None or result.fix_status == oracle.expected_fix
    if result.fix_status in {FixStatus.DEMONSTRATION_BLOCKED, FixStatus.NOT_BLOCKED}:
        fixed = result.fix_observation
        fixed_valid = False
        if fixed is not None and store is not None and result.manifest is not None:
            verifier = _saved_evidence_verifier(store)
            fixed_valid = any(
                (submission := item.producer.submission_for_verification()) is not None
                and (
                    prepared := verifier.validate_saved(
                        fixed, submission, result.manifest, expected_fixed=True
                    )
                )
                is not None
                and prepared.case_id == result.case_id
                for item in result.rounds
            )
        fix_correct = fix_correct and fixed_valid and fix_status(fixed) == result.fix_status
    verdict_allowed = oracle.verdict_allowed(result.verdict)
    passed = (
        allowed
        and evidence_valid
        and fix_correct
        and verdict_allowed
        and result.execution_status == oracle.expected_execution
    )
    return {
        "run_id": result.run_id,
        "case_id": result.case_id,
        "status": "pass" if passed else "fail",
        "disposition": result.disposition.value,
        "verdict": result.verdict.value if result.verdict is not None else None,
        "execution_status": result.execution_status.value,
        "evidence_valid": evidence_valid,
        "fix_correct": fix_correct,
        "verdict_allowed": verdict_allowed,
        "forbidden_label": result.disposition in oracle.forbidden,
        "correctly_resolved": passed and result.verdict in _DECISIVE_VERDICTS,
        **usage_metrics(result),
        "config_digest": result.manifest.config_digest if result.manifest else None,
        "reason": result.reason,
        "gate_ledger": gate_ledger(result, verified_rounds(result, store)),
    }


def usage_metrics(result: InvestigationResult) -> dict:
    """One usage calculation shared by scoring and human CLI presentation."""
    usage = [item.producer.usage for item in result.rounds]
    usage += [item.audit.usage for item in result.rounds if item.audit is not None]
    return {
        "llm_calls": sum(item.llm_calls for item in usage) if result.usage_complete else None,
        "tool_calls": sum(item.tool_calls for item in usage) if result.usage_complete else None,
        "input_tokens": _sum_known_counts(item.input_tokens for item in usage)
        if result.usage_complete
        else None,
        "output_tokens": _sum_known_counts(item.output_tokens for item in usage)
        if result.usage_complete
        else None,
        "agent_seconds": sum(item.seconds for item in usage) if result.usage_complete else None,
    }


def _sum_known_counts(values: Iterable[int | None]) -> int | None:
    """Aggregate in one pass; missing values and an empty population stay unknown."""
    iterator = iter(values)
    total = next(iterator, None)
    if total is None:
        return None
    for value in iterator:
        if value is None:
            return None
        total += value
    return total


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    passed = sum(row.get("status") == "pass" for row in rows)
    return {
        "attempts": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else None,
        "correctly_resolved": sum(row.get("correctly_resolved", False) for row in rows),
        "invalid_positive_evidence": sum(row.get("evidence_valid") is False for row in rows),
        "forbidden_labels": sum(row.get("forbidden_label", False) for row in rows),
        "inconclusive": sum(row.get("disposition") == "INCONCLUSIVE" for row in rows),
        "operational_failures": sum(
            row.get("execution_status") in {"BLOCKED", "ERROR", "CANCELLED"} for row in rows
        ),
        "unavailable_results": sum(row.get("status") == "unavailable" for row in rows),
        "llm_calls": _sum_known_counts(row.get("llm_calls") for row in rows),
        "tool_calls": _sum_known_counts(row.get("tool_calls") for row in rows),
        "input_tokens": _sum_known_counts(row.get("input_tokens") for row in rows),
        "output_tokens": _sum_known_counts(row.get("output_tokens") for row in rows),
        "cost_usd": None,
        # Every recorded stop, then the final stop of each failed row: where accuracy
        # was lost. Isolated agent rows saved without a ledger derive their one entry;
        # rows without either (unavailable results) contribute nothing.
        "gate_ledger": ledger_counts(row_ledger(row) for row in rows),
        "failure_stops": ledger_counts(
            row_ledger(row)[-1:] for row in rows if row.get("status") == "fail"
        ),
    }


def save_report(path: Path, rows: list[dict], dataset_digest: Digest | None = None) -> dict:
    """Write and return one complete external evaluation report."""
    report = {"rows": rows, "summary": summarize(rows)}
    if dataset_digest is not None:
        report["dataset_digest"] = dataset_digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report
