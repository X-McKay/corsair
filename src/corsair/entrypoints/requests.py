"""Client-edge request loading; preserve path spelling for secure source admission."""

from pathlib import Path

from corsair.adapters.scm.requests import normalize_request_sources
from corsair.contracts import InvestigationRequest


def load_investigation_request(path: Path) -> InvestigationRequest:
    """Read and validate one request, resolving sources relative to its file."""

    request = InvestigationRequest.model_validate_json(path.read_bytes())
    return normalize_request_sources(request, path)
