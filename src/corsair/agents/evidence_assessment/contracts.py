"""Frozen evidence-assessment contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from corsair.core.disposition import (Admission, AssessmentEvidence, Disposition, Execution, Finding,
                                      Fix, GateResult, Limitation, ObservationPlan, TestValidity)

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
    path: str | None = Field(default=None, max_length=256, exclude_if=lambda value: value is None)
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


class ValidityInput(Contract):
    """Frozen pre-execution review; execution observations cannot enter this contract."""
    scope: Literal["component", "application_path"]
    plan: ObservationPlan
    revision_sources: dict[Literal["baseline", "candidate"], str]
    items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def review_only(self) -> "ValidityInput":
        if self.plan.observation_mode != "unit_test":
            raise ValueError("pre-execution validity requires unit-test mode")
        if any(item.kind not in ("source", "patch", "plan") for item in self.items):
            raise ValueError("validity review cannot contain execution evidence")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate evidence item id")
        if sum(len(item.content) for item in self.items) > MAX_TOTAL_CHARS:
            raise ValueError("evidence items exceed the admitted character budget")
        if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
               for value in self.revision_sources.values()):
            raise ValueError("source identity must be a sha256 digest")
        return self


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


class ProductionBinding(Contract, Generic[Citation]):
    called_symbol: Fact = Field(description="Actual symbol invoked in the frozen probe, following imports, aliases and replacements")
    status: Literal["production", "copied", "replaced", "unknown"]
    call_site: Citation = Field(description="Exact frozen patch lines invoking the probe call")
    definition_site: Citation | None = Field(description="Exact lines holding the actual called definition, after resolving imports/aliases/replacements; null when unresolved. A test-local copy is in a patch item, not source.")
    evidence: Observation[Citation]


class InputExercise(Contract, Generic[Citation]):
    observed_input: Fact = Field(description="Actual argument/value reaching this probe's call, copied from the frozen test rather than inferred from the issue")
    status: Literal["benign", "reported_adversarial", "different", "unknown"]
    preconditions: Literal["established", "missing", "unknown"]
    evidence: Observation[Citation]


class AssertionProperty(Contract, Generic[Citation]):
    asserted_property: Fact = Field(description="Property the actual assertion enforces, including any caught exception and pass condition")
    status: Literal["benign_behavior", "security_property", "unrelated", "vacuous", "unknown"]
    evidence: Observation[Citation]


class DependencySubstitutions(Contract, Generic[Citation]):
    substitutions: tuple[Fact, ...] = Field(max_length=8, description="Actual dependencies or entry points replaced, including replacement behavior; empty only when none are replaced or unresolved")
    scope: Literal["none", "dependencies_only", "entry_point_replaced", "security_logic_replaced", "unknown"]
    evidence: Observation[Citation]


class ProbeValidity(Contract, Generic[Citation]):
    test_id: Fact = Field(description="Exact native test id for this probe from the frozen plan")
    production_binding: ProductionBinding[Citation]
    input_exercise: InputExercise[Citation]
    assertion: AssertionProperty[Citation]
    dependencies: DependencySubstitutions[Citation]

    @property
    def observations(self) -> tuple[Observation[Citation], ...]:
        return (self.production_binding.evidence, self.input_exercise.evidence,
                self.assertion.evidence, self.dependencies.evidence)


class ValidityReview(Contract, Generic[Citation]):
    """Evidence for each real probe; aggregate validity is derived by trusted code."""
    revision: Literal["baseline", "candidate"]
    control: ProbeValidity[Citation]
    exploit: ProbeValidity[Citation]

    @property
    def observations(self) -> tuple[Observation[Citation], ...]:
        return (*self.control.observations, *self.exploit.observations)

    @property
    def source_linked(self) -> bool:
        return all(probe.production_binding.status == "production" for probe in (self.control, self.exploit))

    @property
    def condition_exercised(self) -> bool:
        return (self.control.input_exercise.status == "benign"
                and self.exploit.input_exercise.status == "reported_adversarial"
                and all(probe.input_exercise.preconditions == "established" for probe in (self.control, self.exploit)))

    @property
    def assertions_relevant(self) -> bool:
        return (self.control.assertion.status == "benign_behavior"
                and self.exploit.assertion.status == "security_property")

    @property
    def dependency_scope_valid(self) -> bool:
        return all(probe.dependencies.scope in ("none", "dependencies_only")
                   for probe in (self.control, self.exploit))


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


class HistoricalValidityReview(Contract, Generic[Citation]):
    """Read-only compatibility for saved pre-structured-review artifacts; never accepted from the model."""
    revision: Literal["baseline", "candidate"]
    source_linked: bool
    condition_exercised: bool
    assertions_relevant: bool
    dependency_scope_valid: bool
    rationale: Observation[Citation]


class EvidenceAssessment(_Proposal[EvidenceExcerpt]):
    """Final stage output: the proposal, the gate's ruling and the disposition that stands."""
    validity_reviews: tuple[ValidityReview[EvidenceExcerpt] | HistoricalValidityReview[EvidenceExcerpt], ...] = Field(default=(), max_length=2)
    bound_validity: dict[Literal["baseline", "candidate"], TestValidity] = Field(default_factory=dict, exclude_if=lambda value: not value)
    admission: Admission
    gate_limitations: tuple[Limitation, ...]
    gate_result: GateResult | None = Field(default=None, exclude_if=lambda value: value is None)
    evidence: AssessmentEvidence | None = Field(default=None, exclude_if=lambda value: value is None)

    @property
    def disposition(self) -> Disposition:
        return self.admission.disposition
