"""Frozen evidence-assessment contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from corsair.core.disposition import (Admission, AssessmentEvidence, Disposition, Execution, Finding,
                                      Fix, GateResult, Limitation, ObservationPlan)

MAX_ITEM_CHARS = 16384
MAX_ITEMS = 32
MAX_TOTAL_CHARS = 131072
WINDOW_LINES = 80

ItemId = Annotated[str, Field(min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9_.-]*$')]
Fact = Annotated[str, Field(min_length=1, max_length=2048)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceItem(Contract):
    """One frozen artifact admitted for this run; content is untrusted workload text."""
    item_id: ItemId
    kind: Literal["plan", "patch", "junit", "witness", "receipt", "stdout", "stderr",
                  "sandbox_log", "environment", "source", "test_validity"]
    revision: Literal["baseline", "candidate"] | None
    run: int | None = Field(default=None, ge=0)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$',
                                     exclude_if=lambda value: value is None)
    content: str = Field(min_length=1, max_length=MAX_ITEM_CHARS)
    complete: bool = Field(default=True, exclude_if=lambda value: value is True)

    @model_validator(mode="after")
    def run_belongs_to_revision(self) -> "EvidenceItem":
        if (self.revision is None) != (self.run is None):
            raise ValueError("a run index requires a revision and vice versa")
        if sha256(self.content.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("evidence content does not match its recorded digest")
        return self


class AssessmentInput(Contract):
    """Gate evidence stays with trusted code; the model sees only the plan and item inventory."""
    scope: Literal["component", "application_path"]
    evidence: AssessmentEvidence
    items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def bounded_unique_items(self) -> "AssessmentInput":
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate evidence item id")
        if sum(len(item.content) for item in self.items) > MAX_TOTAL_CHARS:
            raise ValueError("evidence items exceed the admitted character budget")
        runs = {"baseline": len(self.evidence.baseline), "candidate": len(self.evidence.candidate)}
        if any(item.revision is not None and item.run >= runs[item.revision] for item in self.items):
            raise ValueError("evidence item names a run absent from the gate evidence")
        return self

    @property
    def plan(self) -> ObservationPlan:
        return self.evidence.plan


class EvidenceReference(Contract):
    item_id: ItemId
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered_range(self) -> "EvidenceReference":
        if self.end_line < self.start_line:
            raise ValueError("inverted evidence line range")
        return self


class EvidenceExcerpt(EvidenceReference):
    quote: str = Field(min_length=1, max_length=MAX_ITEM_CHARS)


class EvidenceLine(Contract):
    number: int = Field(ge=1)
    text: str = Field(max_length=MAX_ITEM_CHARS)


class EvidenceRead(EvidenceReference):
    lines: tuple[EvidenceLine, ...] = Field(min_length=1, max_length=WINDOW_LINES)

    @model_validator(mode="after")
    def complete_numbered_range(self) -> "EvidenceRead":
        if (len(self.lines) != self.end_line - self.start_line + 1
                or any(line.number != self.start_line + offset for offset, line in enumerate(self.lines))):
            raise ValueError("evidence lines must cover the declared range in order")
        return self


Citation = TypeVar("Citation", bound=EvidenceReference)


class Observation(Contract, Generic[Citation]):
    statement: Fact
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=8)


class ValidityReview(Contract, Generic[Citation]):
    """Independent assessment of the frozen test property against one revision."""
    revision: Literal["baseline", "candidate"]
    source_linked: bool = Field(description="Both control and exploit probes call the intended real source implementation")
    condition_exercised: bool = Field(description="The control exercises benign input and the exploit exercises the reported adversarial input and preconditions")
    assertions_relevant: bool = Field(description="Both probes make relevant non-vacuous assertions; the exploit asserts the required safe behavior")
    dependency_scope_valid: bool
    rationale: Observation[Citation]


class _Proposal(Contract, Generic[Citation]):
    execution: Execution
    finding: Finding
    fix: Fix
    application_observations: tuple[Observation[Citation], ...] = Field(max_length=8)
    sandbox_observations: tuple[Observation[Citation], ...] = Field(max_length=8)
    interpretation: Observation[Citation]
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=16)
    validity_reviews: tuple[ValidityReview[Citation], ...] = Field(default=(), max_length=2)


class ProposedDispositionDraft(_Proposal[EvidenceReference]):
    """Model-facing proposal citing evidence line ranges; quotations are attached by trusted code."""


class EvidenceAssessment(_Proposal[EvidenceExcerpt]):
    """Final stage output: the proposal, the gate's ruling and the disposition that stands."""
    admission: Admission
    gate_limitations: tuple[Limitation, ...]
    gate_result: GateResult | None = Field(default=None, exclude_if=lambda value: value is None)
    evidence: AssessmentEvidence | None = Field(default=None, exclude_if=lambda value: value is None)

    @property
    def disposition(self) -> Disposition:
        return self.admission.disposition
