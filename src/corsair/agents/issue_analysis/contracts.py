"""Saved fixture stage contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from typing import Generic, Literal

from pydantic import Field, model_validator

# Shared saved-source contracts moved with their second consumer; names stay importable here.
from ..source.contracts import (
    Citation, Contract, Fact, SourceExcerpt, SourceFile, SourceLine, SourceRead, SourceReference,
    bounded_inventory, confined_path,
)


class IssueAnalysisInput(Contract):
    fixture_id: str = Field(min_length=1, max_length=128)
    issue: str = Field(min_length=1, max_length=8192)
    scope: Literal["component", "application_path"]
    source_files: tuple[SourceFile, ...] = Field(max_length=16)

    @model_validator(mode="after")
    def bounded_unique_source(self) -> "IssueAnalysisInput":
        bounded_inventory(self.source_files)
        return self

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class Hypothesis(Contract):
    entry_point: Fact
    attacker_input: Fact
    attacker_capabilities: Fact
    preconditions: tuple[Fact, ...] = Field(min_length=1, max_length=16)
    sensitive_operation: Fact
    observable_effect: Fact = Field(description="Conditional behavior predicted from the source, including rejection or prevention when supported; not an execution verdict.")


class _Analysis(Contract, Generic[Citation]):
    status: Literal["ready", "missing_information", "unsupported"] = Field(description="ready: cited, testable behavioral prediction, not confirmation of a vulnerability. Other statuses require a null hypothesis; missing_information also requires blocking missing facts.")
    scope: Literal["component", "application_path"]
    hypothesis: Hypothesis | None
    citations: tuple[Citation, ...] = Field(max_length=16)
    missing_facts: tuple[Fact, ...] = Field(max_length=16, description="Only unknowns that prevent a grounded prediction at the authorized scope. Must be empty for ready. Conditional assumptions belong in preconditions; wider-context unknowns in limitations.")
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def status_matches_evidence(self) -> "_Analysis[Citation]":
        if self.status == "ready":
            if self.hypothesis is None or not self.citations or self.missing_facts:
                raise ValueError("ready requires a cited hypothesis and no missing required facts")
        elif self.hypothesis is not None:
            raise ValueError("missing_information or unsupported analysis cannot carry a hypothesis")
        elif self.status == "missing_information" and not self.missing_facts:
            raise ValueError("missing_information requires the missing facts")
        # unsupported may have no missing fact: the requirement itself is out of
        # scope, and the mandatory limitations state why.
        return self


class IssueAnalysis(_Analysis[SourceExcerpt]):
    pass


class IssueAnalysisDraft(_Analysis[SourceReference]):
    pass
