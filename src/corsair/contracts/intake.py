"""Scanner-finding intake wire contracts.

These model the envelope an upstream security scanner feeds Corsair. Everything
here is UNTRUSTED producer input: a scanner's severity, confidence, category and
narrative are self-assessments carried only for reporting. The verdict kernel in
``policies/verdicts.py`` never reads any of these fields -- a finding's label is
decided by what Corsair can demonstrate against the supplied source, not by what
the scanner claims about it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from .common import Contract, safe_path

# A scanner report may enumerate many findings, but a single intake admits exactly
# one finding at a time; these bounds keep an envelope parseable, not unbounded.
MAX_SCANNER_FINDINGS = 256
MAX_PRECONDITIONS = 32
MAX_REPOSITORIES = 32

ShortText = Annotated[str, Field(min_length=1, max_length=500)]
Narrative = Annotated[str, Field(min_length=1, max_length=12000)]
Precondition = Annotated[str, Field(min_length=1, max_length=1000)]


class Repository(Contract):
    """One source repository the scanner says bounds the claimed finding.

    The supplied repositories are the *only* code Corsair can demonstrate against.
    If the claimed application path depends on code outside this set, the
    demonstration ceiling is the component seam, never the full application.
    """

    name: ShortText
    url: str = Field(min_length=1, max_length=2048)
    branch: str | None = Field(default=None, max_length=500)
    revision: str | None = Field(default=None, max_length=256)


class ScannerScope(Contract):
    """The scanner's claim about where the finding lives and what bounds it.

    ``application`` is the scanner's free-text claim about the application entry
    point. It is untrusted narrative: the demonstrated scope is decided by what
    Corsair can actually exercise against ``repositories``, not by this string.
    """

    application: ShortText
    repositories: list[Repository] = Field(min_length=1, max_length=MAX_REPOSITORIES)


class ScannerFinding(Contract):
    """One finding as emitted by the upstream scanner.

    Severity, confidence, category, impact, exploit_scenario, preconditions and
    recommendation are the scanner's own assessment. They are preserved verbatim
    for reporting and NEVER influence the verdict.
    """

    title: ShortText
    description: Narrative
    file: str
    line: int | None = Field(default=None, ge=1)
    category: str = Field(default="", max_length=200)
    severity: str = Field(default="", max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    impact: str = Field(default="", max_length=12000)
    exploit_scenario: str = Field(default="", max_length=12000)
    recommendation: str = Field(default="", max_length=12000)
    preconditions: list[Precondition] = Field(default_factory=list, max_length=MAX_PRECONDITIONS)
    scope: ScannerScope

    _safe_file = field_validator("file")(safe_path)


class ScanReport(Contract):
    """The top-level scanner envelope: a completed scan and its findings."""

    schema_version: Literal["corsair.scan_report/1"] = "corsair.scan_report/1"
    scan_completed: bool
    vulnerabilities_found: bool
    findings: list[ScannerFinding] = Field(default_factory=list, max_length=MAX_SCANNER_FINDINGS)


class ScannerClaim(Contract):
    """The scanner's untrusted self-assessment, carried on an internal Finding.

    This exists so a verdict and its report can cite what the scanner claimed
    without that claim ever reaching the verdict kernel. The kernel reads only a
    Finding's title, description, file, line and claim_scope; this object is never
    among them.
    """

    severity: str = Field(default="", max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    category: str = Field(default="", max_length=200)
    recommendation: str = Field(default="", max_length=12000)
    impact: str = Field(default="", max_length=12000)
    exploit_scenario: str = Field(default="", max_length=12000)
    preconditions: list[Precondition] = Field(default_factory=list, max_length=MAX_PRECONDITIONS)
    application: str = Field(default="", max_length=500)
    repositories: list[Repository] = Field(default_factory=list, max_length=MAX_REPOSITORIES)

    @classmethod
    def from_finding(cls, finding: ScannerFinding) -> ScannerClaim:
        """Carry a scanner finding's self-assessment verbatim, for reporting only."""
        return cls(
            severity=finding.severity,
            confidence=finding.confidence,
            category=finding.category,
            recommendation=finding.recommendation,
            impact=finding.impact,
            exploit_scenario=finding.exploit_scenario,
            preconditions=list(finding.preconditions),
            application=finding.scope.application,
            repositories=list(finding.scope.repositories),
        )
