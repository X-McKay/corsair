"""Client-edge request loading; preserve path spelling for secure source admission."""

from pathlib import Path

from corsair.adapters.scm.requests import normalize_request_sources
from corsair.contracts import (
    Finding,
    InvestigationRequest,
    ScannerClaim,
    ScannerFinding,
    ScanReport,
    Scope,
)


def load_investigation_request(path: Path) -> InvestigationRequest:
    """Read and validate one request, resolving sources relative to its file."""

    request = InvestigationRequest.model_validate_json(path.read_bytes())
    return normalize_request_sources(request, path)


def load_scan_report(path: Path) -> ScanReport:
    """Read and validate one upstream scanner envelope.

    The report is untrusted producer data. Validation only bounds and shapes it;
    it never grants a finding's claim any standing in the verdict.
    """

    return ScanReport.model_validate_json(path.read_bytes())


def finding_from_scanner(scanner_finding: ScannerFinding) -> Finding:
    """Map one scanner finding onto an internal Finding, conservatively.

    The scanner's severity, confidence, category and narrative are carried on the
    Finding as an untrusted ``ScannerClaim`` purely for reporting; the verdict
    kernel never reads them. The claimed scope is set to APPLICATION so that a
    genuine demonstration against the supplied repositories is capped at
    COMPONENT_EXPLOIT_DEMONSTRATED: driving the real application entry point needs
    an application-entry recipe mechanism that is a known follow-up, so until then
    we never award a silent full-application EXPLOIT_DEMONSTRATED for an
    application claim we cannot run end to end. The supplied repositories are the
    only code the demonstration may run against: a finding whose file is absent
    from the admitted source cannot bind its target line and resolves
    UNABLE_TO_RUN rather than any demonstration or clean negative.
    """

    return Finding(
        title=scanner_finding.title,
        description=scanner_finding.description,
        file=scanner_finding.file,
        line=scanner_finding.line,
        claim_scope=Scope.APPLICATION,
        scanner=ScannerClaim.from_finding(scanner_finding),
    )
