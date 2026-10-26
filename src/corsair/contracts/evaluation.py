"""Canonical evaluation wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import ArtifactRef, Contract, DiagnosticText, Identifier
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
