"""Client-edge request loading; preserve path spelling for secure source admission."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from corsair.contracts.intake_agent import IssueReference

# Scanner-finding conversion is pure request shaping shared with the intake evaluator,
# so it lives with source normalization; this typed API re-exports it.
from corsair.adapters.scm.requests import finding_from_scanner as finding_from_scanner
from corsair.adapters.scm.requests import load_recipe_template as load_recipe_template
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.scm.requests import request_from_scanner as request_from_scanner
from corsair.contracts import InvestigationRequest, ScanReport


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


def parse_issue_reference(value: str, repositories: list[str]) -> "IssueReference":
    """Resolve a number only when operator context names exactly one repository."""
    from corsair.contracts.intake_agent import IssueReference

    if value.isdecimal():
        if len(repositories) != 1:
            raise ValueError("numeric issue ID requires exactly one configured GitHub repository")
        value = f"{repositories[0]}#{value}"
    repository, number = value.rsplit("#", 1)
    owner, name = repository.split("/", 1)
    return IssueReference(owner=owner, repository=name, number=int(number))
