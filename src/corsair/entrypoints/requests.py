"""Client-edge request loading; preserve path spelling for secure source admission."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from corsair.contracts.intake import IssueReference

from corsair.adapters.scm.requests import normalize_request_sources
from corsair.contracts import InvestigationRequest


def load_investigation_request(path: Path) -> InvestigationRequest:
    """Read and validate one request, resolving sources relative to its file."""

    request = InvestigationRequest.model_validate_json(path.read_bytes())
    return normalize_request_sources(request, path)


def parse_issue_reference(value: str, repositories: list[str]) -> "IssueReference":
    """Resolve a number only when operator context names exactly one repository."""
    from corsair.contracts.intake import IssueReference

    if value.isdecimal():
        if len(repositories) != 1:
            raise ValueError("numeric issue ID requires exactly one configured GitHub repository")
        value = f"{repositories[0]}#{value}"
    repository, number = value.rsplit("#", 1)
    owner, name = repository.split("/", 1)
    return IssueReference(owner=owner, repository=name, number=int(number))


def load_execution_request(path: Path):
    """New investigation input: v3 only; historical recipe loading stays explicit."""
    from corsair.contracts.execution import ExecutionRequest

    request = ExecutionRequest.model_validate_json(path.read_bytes())

    def absolute(source):
        return source.model_copy(update={"path": str(path.absolute().parent / source.path)})

    return request.model_copy(
        update={
            "source": absolute(request.source),
            "fixed_source": None
            if request.fixed_source is None
            else absolute(request.fixed_source),
        }
    )


def load_issue_investigation_request(path: Path):
    """Load a bounded intake-first request without erasing unsafe source spelling."""
    from corsair.contracts.pipeline import IssueInvestigationRequest

    with path.open("rb") as stream:
        payload = stream.read(131073)
    if len(payload) > 131072:
        raise ValueError("issue investigation request exceeds byte limit")
    request = IssueInvestigationRequest.model_validate_json(payload)

    def absolute(source):
        return source.model_copy(update={"path": str(path.absolute().parent / source.path)})

    return request.model_copy(
        update={
            "intake": request.intake.model_copy(update={"source": absolute(request.intake.source)}),
            "fixed_source": None
            if request.fixed_source is None
            else absolute(request.fixed_source),
        }
    )
