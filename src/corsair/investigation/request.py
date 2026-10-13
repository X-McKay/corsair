"""`corsair-issue-request/v1`: what a user supplies to start an investigation, and nothing an operator owns.

The issue is a captured ticket (`TicketSnapshot`, as `corsair.tickets.capture` writes it) or a hand-written
`manual` issue with a title and body. Runtime, framework, runner, baseline test, witness target, budgets, policy
and images are never part of a request: they are selected or inferred and recorded with their basis. Labels and
oracles are never part of a request either; an eval case keeps them in a separate file the entry never reads.
"""
from hashlib import sha256
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from corsair.agents.source.contracts import confined_path
from corsair.ports.tickets import TicketSnapshot

COMMIT = re.compile(r"[0-9a-f]{40}")
HTTPS = re.compile(r"https://[a-z0-9.-]+(?:/[A-Za-z0-9._~%-]+)+")
# An operator-allowlisted local repository root (eval cases); the entry refuses any path outside the allowed roots.
LOCAL = re.compile(r"file:///[^\0\n]+")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ManualIssue(_Frozen):
    provider: Literal["manual"] = "manual"
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(max_length=65536)
    format: Literal["markdown", "html"] = "markdown"

    def issue_text(self, *, max_chars: int = 8192) -> str:
        return f"{self.title}\n\n{self.body}"[:max_chars]

    @property
    def digest(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()


class PovFile(_Frozen):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=16384)

    _path = field_validator("path")(confined_path)


class Pov(_Frozen):
    """Untrusted proof-of-concept material: read as issue content, never executed directly."""
    description: str = Field(default="", max_length=8192)
    files: tuple[PovFile, ...] = Field(default=(), max_length=8)


class IssueRequest(_Frozen):
    schema_: Literal["corsair-issue-request/v1"] = Field(alias="schema")
    issue: TicketSnapshot | ManualIssue = Field(discriminator="provider")
    repository: str | None = Field(default=None, description="https URL, or file:// under an operator-allowed root")
    revision: str | None = Field(default=None, description="The vulnerable revision's commit")
    fixed_revision: str | None = Field(default=None, description="The fix's commit; without it no fix is verified")
    scope: Literal["component", "application_path"] | None = None
    pov: Pov | None = None

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("repository")
    @classmethod
    def repository_url(cls, value: str | None) -> str | None:
        if value is not None and not (HTTPS.fullmatch(value) or LOCAL.fullmatch(value)):
            raise ValueError("repository must be a plain https URL or a file:// path")
        return value

    @field_validator("revision", "fixed_revision")
    @classmethod
    def commit(cls, value: str | None) -> str | None:
        # A branch or tag would be resolved to a commit at acquisition; not built yet, so only commits are accepted.
        if value is not None and not COMMIT.fullmatch(value):
            raise ValueError("revisions must be exact 40-hex commits (ref resolution is not built yet)")
        return value

    def issue_text(self) -> str:
        """Untrusted issue content for identification: the ticket's text and any PoV description."""
        text = self.issue.issue_text()
        if self.pov and self.pov.description:
            text = f"{text}\n\nProof of concept (untrusted, not executed):\n{self.pov.description}"
        return text[:8192]

    @property
    def label(self) -> str:
        issue = self.issue
        return f"{issue.provider}:{issue.source}#{issue.id}" if isinstance(issue, TicketSnapshot) else \
            f"manual:{issue.digest[:12]}"
