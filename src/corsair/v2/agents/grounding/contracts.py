"""Grounding contracts (placeholder spec, "ADO Intake, Security Graph and Grounding Agent", Oct 14 2026).

Grounding is advisory. It reports what human reviewers already concluded about similar issues, reads only a
context retrieved from the security graph, and nothing downstream reads its output: a person reads the brief
beside the verdict. These types therefore live in the grounding package, not in ``corsair.v2.contracts``.
All graph and work-item text is untrusted data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TERMINAL_STATES = frozenset({"closed", "resolved", "done", "approved", "completed", "removed"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- ADO intake -------------------------------------------------------------------------------------------------


class FindingInput(_Model):
    """A finding as ADO intake produces it. ``ado_work_item_id`` is set only by ADO intake, never from a graph id."""

    external_id: str = Field(min_length=1, max_length=256)
    title: str = Field(max_length=512)
    description: str = Field(default="", max_length=20_000)
    repo_url: str = Field(min_length=1, max_length=1024)
    revision: str = Field(default="HEAD", max_length=256)
    file_path: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    symbol: str | None = None
    cwe: str | None = Field(default=None, pattern=r"^CWE-\d{1,5}$")
    severity: str | None = None
    source_tool: str | None = None
    source_kind: Literal["ado", "security_graph"] = "ado"
    ado_work_item_id: int | None = None
    source_mode: str | None = None


class Skip(_Model):
    """A work item intake will not run, with the reason it is listed under."""

    external_id: str
    reason: str


class ScanRef(_Model):
    organization: str | None = None
    project: str | None = None
    repository: str | None = None
    branch: str | None = None
    commit: str | None = None


# --- Security graph ---------------------------------------------------------------------------------------------


class GraphIssue(_Model):
    id: str = Field(min_length=1, max_length=256)
    title: str = Field(default="", max_length=500)
    state: str = Field(default="", max_length=100, description="The tracker's own string, not normalised")
    cwe: str | None = None
    severity: str | None = None
    description: str = Field(default="", max_length=20_000)
    repo_url: str | None = None
    web_url: str | None = None
    source_file: str | None = None

    @property
    def decided(self) -> bool:
        return self.state.lower() in TERMINAL_STATES


class GraphComment(_Model):
    author: str = Field(default="", max_length=200)
    created_at: str = Field(default="", max_length=64)
    text: str = Field(default="", max_length=4_000)


class RelatedIssue(_Model):
    issue: GraphIssue
    relation: Literal["self", "similarity", "cwe", "nearby"]
    similarity: float | None = None
    comments: tuple[GraphComment, ...] = ()


class GraphRepoRef(_Model):
    clone_url: str
    web_url: str | None = None
    default_branch: str | None = None
    pinned_sha: str | None = None
    source: Literal["scan_header", "graph_edge", "coordinates"]


class GroundingContext(_Model):
    """Everything retrieval returned, assembled before the agent runs. It is the only citable material."""

    issue: GraphIssue | None = None
    comments: tuple[GraphComment, ...] = ()
    related: tuple[RelatedIssue, ...] = ()
    degraded: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return self.issue is None and not self.comments and not self.related

    def retrieved_ids(self) -> frozenset[str]:
        return frozenset(([self.issue.id] if self.issue else []) + [r.issue.id for r in self.related])


# --- Grounding agent output -------------------------------------------------------------------------------------

PriorDisposition = Literal["fixed", "not_exploitable", "accepted_risk", "duplicate", "unexplained"]


class Precedent(_Model):
    issue_id: str
    title: str = ""
    state: str = ""
    disposition: PriorDisposition
    relation: Literal["self", "similarity", "cwe", "nearby"]
    rationale: str = Field(default="", max_length=1_000)
    quote: str = Field(max_length=2_000, description="Verbatim from the retrieved text; checked by code")
    similarity: float | None = None
    web_url: str | None = None


class GroundingBrief(_Model):
    summary: str = Field(max_length=2_000)
    precedents: tuple[Precedent, ...] = ()
    prior_disposition: PriorDisposition | None = None
    caveats: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _disposition_needs_a_precedent(self) -> GroundingBrief:
        if self.prior_disposition is not None and not self.precedents:
            raise ValueError("prior_disposition needs a precedent that states it")
        return self
