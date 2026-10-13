"""Narrow source location handoff; trusted code preserves the reported issue."""

from typing import Generic, Literal

from pydantic import Field, field_validator, model_validator

from .contracts import Citation, Contract, Fact, SourceExcerpt, SourceReference


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
