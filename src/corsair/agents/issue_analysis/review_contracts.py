"""Vendor-free, immutable contracts for issue-analysis evidence review."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Fact, SourceExcerpt, SourceReference


FieldPath = Literal[
    "status", "scope", "hypothesis.entry_point", "hypothesis.attacker_input",
    "hypothesis.attacker_capabilities", "hypothesis.preconditions",
    "hypothesis.sensitive_operation", "hypothesis.observable_effect",
    "citations", "missing_facts", "limitations",
]


class ConditionAudit(Contract):
    operation: Fact
    required_condition: Fact
    coverage: Literal["explicit", "entailed", "missing"]
    basis: Fact


class ReviewFindingDraft(Contract):
    field_path: FieldPath
    problem: Fact
    citations: tuple[SourceReference, ...] = Field(max_length=8)


class ReviewFinding(Contract):
    field_path: FieldPath
    problem: Fact
    citations: tuple[SourceExcerpt, ...] = Field(max_length=8)


class ReviewDraft(Contract):
    assessment: Literal["supported", "needs_revision", "insufficient_evidence"]
    scope: Literal["component", "application_path"]
    findings: tuple[ReviewFindingDraft, ...] = Field(max_length=8)
    citations: tuple[SourceReference, ...] = Field(max_length=16)
    condition_audit: tuple[ConditionAudit, ...] = Field(max_length=8)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def assessment_matches_findings(self) -> "ReviewDraft":
        if self.assessment == "supported" and self.findings:
            raise ValueError("supported review cannot contain findings")
        if self.assessment != "supported" and not self.findings:
            raise ValueError("an incomplete review requires targeted findings")
        if (any(item.coverage == "missing" for item in self.condition_audit)
                and self.assessment != "needs_revision"):
            raise ValueError("an unmet necessary condition requires needs_revision")
        if (any(item.coverage == "missing" for item in self.condition_audit)
                and not any(item.field_path in ("hypothesis.preconditions", "hypothesis.observable_effect")
                            for item in self.findings)):
            raise ValueError("missing necessary condition requires a targeted precondition or effect finding")
        return self


class ReviewReport(Contract):
    assessment: Literal["supported", "needs_revision", "insufficient_evidence"]
    scope: Literal["component", "application_path"]
    findings: tuple[ReviewFinding, ...] = Field(max_length=8)
    citations: tuple[SourceExcerpt, ...] = Field(max_length=16)
    condition_audit: tuple[ConditionAudit, ...] = Field(max_length=8)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def assessment_matches_findings(self) -> "ReviewReport":
        if self.assessment == "supported" and self.findings:
            raise ValueError("supported review cannot contain findings")
        if self.assessment != "supported" and not self.findings:
            raise ValueError("an incomplete review requires targeted findings")
        if (any(item.coverage == "missing" for item in self.condition_audit)
                and self.assessment != "needs_revision"):
            raise ValueError("an unmet necessary condition requires needs_revision")
        if (any(item.coverage == "missing" for item in self.condition_audit)
                and not any(item.field_path in ("hypothesis.preconditions", "hypothesis.observable_effect")
                            for item in self.findings)):
            raise ValueError("missing necessary condition requires a targeted precondition or effect finding")
        return self
