"""Lexical request-source normalization before local source admission."""

from pathlib import Path

from corsair.contracts import InvestigationRequest


def normalize_request_sources(
    request: InvestigationRequest, request_file: Path
) -> InvestigationRequest:
    """Anchor relative sources at a request file without resolving source symlinks."""

    base = request_file.parent.absolute()

    def anchored(path: str) -> str:
        return path if Path(path).is_absolute() else str((base / path).absolute())

    source = request.case.source.model_copy(update={"path": anchored(request.case.source.path)})
    fixed = request.case.fixed_source
    if fixed is not None:
        fixed = fixed.model_copy(update={"path": anchored(fixed.path)})
    return request.model_copy(
        update={"case": request.case.model_copy(update={"source": source, "fixed_source": fixed})}
    )
