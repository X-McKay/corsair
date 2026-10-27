"""Canonical evaluation wire contracts; no vendor SDK types."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

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


# A staged row's licence status: every drafted tree holds a licence or notice file, or not.
ReviewLicence = Literal["retained", "NOASSERTION"]


class ReviewDecision(StrEnum):
    """A reviewer's decision on one drafted intake row."""

    ACCEPT = "accept"
    AMEND = "amend"
    REJECT = "reject"


class DatasetReviewEntry(Contract):
    """One drafted row as the review decided it.

    ``reviewer`` and ``reason`` are the reviewer's own text, kept for machine output only.
    ``frozen_oracle_digest`` is the manifest's oracle digest for an accepted or amended row and
    absent for a rejected one. ``licence`` and ``import_target`` describe a staged row: the
    licence status of its drafted trees and, once imported, its directory below the corpus.
    A field a reconstructed record cannot recover stays None.
    """

    case_id: str = Field(min_length=1, max_length=120)
    family: str | None = None
    kind: str | None = None
    decision: ReviewDecision
    reviewer: str | None = Field(default=None, max_length=400)
    reviewed_oracle_digest: Digest | None = None
    frozen_oracle_digest: Digest | None = None
    reason: str | None = Field(default=None, max_length=400)
    licence: ReviewLicence | None = None
    import_target: str | None = None

    @model_validator(mode="after")
    def coherent_decision(self):
        frozen = self.decision is not ReviewDecision.REJECT
        if frozen != (self.frozen_oracle_digest is not None):
            raise ValueError(
                "an accepted or amended row records its frozen oracle digest; a rejected row none"
            )
        if not frozen and self.import_target is not None:
            raise ValueError("a rejected row has no import target")
        return self


class DatasetReview(Contract):
    """The tracked record of one ``dataset freeze``: which review decided which rows.

    Paths are relative to the repository holding the manifest when they lie below it. The
    manifest digests are ``corsair.dataset/1`` identities (None: no manifest before or after);
    ``draft_digest`` and ``review_sheet_digest`` are SHA-256 of ``draft.json`` and the reviewed
    sheet. A ``reconstructed`` record was rebuilt after the sheet was lost and names its source.
    """

    schema_version: Literal["corsair.dataset-review/1"] = "corsair.dataset-review/1"
    manifest: str = Field(min_length=1)
    old_manifest_digest: Digest | None = None
    new_manifest_digest: Digest | None = None
    draft_id: Identifier
    draft_digest: Digest | None = None
    review_sheet_digest: Digest | None = None
    source_root: str | None = None
    staged: bool = False
    split: str = Field(min_length=1)
    recorded_at: datetime | None = None
    reconstructed: bool = False
    reconstructed_from: str | None = Field(default=None, max_length=2000)
    entries: list[DatasetReviewEntry] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent_record(self):
        if self.reconstructed != (self.reconstructed_from is not None):
            raise ValueError("a reconstructed record, and only one, names what it was rebuilt from")
        case_ids = [entry.case_id for entry in self.entries]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("a review record lists each case once")
        return self
