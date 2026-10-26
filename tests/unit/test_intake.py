"""Scanner-finding intake: parsing, conservative mapping, and the hard guarantee
that a scanner's self-assessment can never move a verdict."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.contracts import (
    FixStatus,
    Repository,
    ScannerFinding,
    ScannerScope,
    Scope,
    Verdict,
)
from corsair.entrypoints.requests import finding_from_scanner, load_scan_report
from corsair.policies.verdicts import session_verdict
from tests.unit.test_evidence import _audit, _prepared
from tests.unit.test_verdicts import _demonstrated

FIXTURES = Path(__file__).resolve().parents[2] / "evals/fixtures/scan_reports"


def _scanner_finding(**overrides) -> ScannerFinding:
    base = ScannerFinding(
        title="Caller path joins the configured root without containment",
        description="The reported callable joins a caller-controlled path onto the root.",
        file="reader.py",
        line=4,
        category="Path traversal",
        severity="LOW",
        confidence=0.1,
        preconditions=["The caller controls the path argument."],
        scope=ScannerScope(
            application="Reporting service file export",
            repositories=[Repository(name="svc", url="https://example.invalid/svc")],
        ),
    )
    return base.model_copy(update=overrides) if overrides else base


@pytest.mark.parametrize(
    "name", ["library-template-injection.json", "preview-server-path-traversal.json"]
)
def test_example_scan_reports_parse(name):
    report = load_scan_report(FIXTURES / name)
    assert report.scan_completed and report.vulnerabilities_found
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.scope.repositories  # the supplied-repos bound is present
    assert 0.0 <= finding.confidence <= 1.0


def test_mapping_carries_the_untrusted_claim_and_caps_the_scope():
    scanner_finding = _scanner_finding(severity="HIGH", confidence=0.95)
    finding = finding_from_scanner(scanner_finding)
    assert finding.title == scanner_finding.title
    assert finding.file == scanner_finding.file
    assert finding.line == scanner_finding.line
    # Conservative ceiling: a scanner claim maps to APPLICATION scope so a genuine
    # differential is capped at COMPONENT_EXPLOIT_DEMONSTRATED, never a silent full
    # application EXPLOIT_DEMONSTRATED we cannot run end to end.
    assert finding.claim_scope is Scope.APPLICATION
    # The self-assessment is carried verbatim for reporting only.
    assert finding.scanner is not None
    assert finding.scanner.severity == "HIGH"
    assert finding.scanner.confidence == 0.95
    assert finding.scanner.application == scanner_finding.scope.application
    assert finding.scanner.repositories == scanner_finding.scope.repositories


def _verdict_for(scanner_finding: ScannerFinding) -> Verdict:
    finding = finding_from_scanner(scanner_finding)
    prepared = _prepared().model_copy(update={"finding": finding})
    return session_verdict(prepared, _demonstrated(), _audit(), FixStatus.NOT_REQUESTED).verdict


def test_scanner_self_assessment_never_moves_the_verdict():
    """Severity and confidence are carried but the kernel never reads them: a
    maximal-severity, maximal-confidence finding and a minimal one with the same
    demonstrated evidence resolve to the exact same code-decided label, and that
    label is the component ceiling, never the full EXPLOIT_DEMONSTRATED."""
    loud = _verdict_for(_scanner_finding(severity="CRITICAL", confidence=1.0))
    quiet = _verdict_for(_scanner_finding(severity="INFO", confidence=0.0))
    assert loud is quiet is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED
    assert loud is not Verdict.EXPLOIT_DEMONSTRATED


def test_scope_requires_at_least_one_supplied_repository():
    """The supplied repositories bound the demonstrable code; a finding that names
    none cannot be admitted, so the scope contract rejects an empty repository set."""
    with pytest.raises(ValidationError):
        ScannerScope(application="svc", repositories=[])


def test_unusual_severity_strings_are_carried_not_rejected():
    """Severity is untrusted producer text, read only for reporting, so an
    unexpected value is preserved rather than rejected (it cannot affect a verdict)."""
    finding = finding_from_scanner(_scanner_finding(severity="SEV-0 (vendor custom)"))
    assert finding.scanner is not None
    assert finding.scanner.severity == "SEV-0 (vendor custom)"
