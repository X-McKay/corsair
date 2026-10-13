"""Narrow source location handoff; trusted code preserves the reported issue.

Inline mode reads `IssueAnalysisInput`; repository mode reads `RepositoryIssueInput` (SPEC-0038).
"""

from hashlib import sha256
from typing import Generic, Literal

from pydantic import Field, field_validator, model_validator

from ..source.contracts import Citation, Contract, Fact, SourceExcerpt, SourceReference


class Target(Contract, Generic[Citation]):
    symbol: str = Field(min_length=1, max_length=256, description="Exact local source symbol naming the relevant implementation")
    source: Citation

    @field_validator("symbol")
    @classmethod
    def exact_symbol_spelling(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("target symbol must use exact spelling without whitespace")
        return value


class _Location(Contract, Generic[Citation]):
    status: Literal["ready", "missing_information", "unsupported"]
    scope: Literal["component", "application_path"]
    target: Target[Citation] | None
    reason: Fact | None = Field(description="Concrete blocker for abstention; null when ready")

    @model_validator(mode="after")
    def status_matches_selection(self) -> "_Location[Citation]":
        if self.status == "ready":
            if self.target is None or self.reason is not None:
                raise ValueError("ready requires a target and no blocker")
        elif self.target is not None or self.reason is None or not self.reason.strip():
            raise ValueError("abstention requires a concrete reason and no target")
        return self


class IssueIdentificationDraft(_Location[SourceReference]):
    pass


class IssueIdentification(_Location[SourceExcerpt]):
    reported_issue: str = Field(min_length=1, max_length=8192, description="Original issue preserved verbatim by trusted code; not a model-authored conclusion")


class RepositoryIdentity(Contract):
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree: str = Field(pattern=r"^[0-9a-f]{40}$")


class RepositoryIssueInput(Contract):
    case_id: str = Field(min_length=1, max_length=128)
    issue: str = Field(min_length=1, max_length=8192)
    scope: Literal["component", "application_path"]
    repository: RepositoryIdentity

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()
