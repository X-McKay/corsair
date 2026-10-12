from pathlib import Path

def read_document(root: Path, filename: str) -> str:
    allowed = root.resolve()
    candidate = (allowed / filename).resolve()
    candidate.relative_to(allowed)
    return candidate.read_text()
