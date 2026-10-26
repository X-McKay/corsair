"""Canonical evaluation wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import ArtifactRef, Contract, DiagnosticText, Digest, Identifier
from .results import Disposition, ExecutionStatus, FixStatus, Verdict
from .sources import InvestigationRequest


class MatchKind(StrEnum):
    """Exact-output diagnostic for an isolated agent evaluation row."""

    EXACT_MATCH = "exact_match"
    CANDIDATE_EXACT_MISMATCH = "candidate_exact_mismatch"
    CONTROL_MISMATCH = "control_mismatch"
    # Auditor only: the decision matched but the oracle's decisive rubric rule did not.
    RULE_MISMATCH = "rule_mismatch"
    NO_VALID_OUTPUT = "no_valid_output"
    OPERATIONAL_FAILURE = "operational_failure"


class BatchRequest(Contract):
    batch_id: Identifier
    requests: list[InvestigationRequest] = Field(min_length=1, max_length=64)
    repeats: int = Field(default=1, ge=1, le=8)
    concurrency: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def bounded_history_payload(self):
        if len(self.model_dump_json().encode()) > 1_000_000:
            raise ValueError("batch payload exceeds 1 MB; split the dataset into finite batches")
        if len(self.batch_id) > 60:
            raise ValueError("batch identity must leave space for child identifiers")
        return self


class BatchItem(Contract):
    case_id: Identifier
    run_id: Identifier
    artifact: ArtifactRef | None = None
    error: DiagnosticText | None = None


# Evaluator-only expectations for one frozen composed case. The schema is canonical here, but
# oracle values are read only by corsair.evaluation and never reach agent, tool or workflow inputs.
# A comment, not a docstring, so the model's JSON schema stays unchanged.
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
