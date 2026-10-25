"""Client-edge request loading; preserve path spelling for secure source admission."""

from pathlib import Path

from corsair.contracts import InvestigationRequest


def resolve_request_sources(request: InvestigationRequest, base: Path) -> InvestigationRequest:
    """Make source paths absolute without resolving a potentially untrusted symlink."""
    source = request.case.source.model_copy(
        update={"path": str((base / request.case.source.path).absolute())}
    )
    fixed = request.case.fixed_source
    if fixed is not None:
        fixed = fixed.model_copy(update={"path": str((base / fixed.path).absolute())})
    return request.model_copy(
        update={"case": request.case.model_copy(update={"source": source, "fixed_source": fixed})}
    )


def load_investigation_request(path: Path) -> InvestigationRequest:
    """Read and validate one request, resolving sources relative to its file."""
    request = InvestigationRequest.model_validate_json(path.read_bytes())
    return resolve_request_sources(request, path.parent.resolve())
