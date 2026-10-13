from pathlib import Path

def read_document(root: Path, filename: str) -> str:
    allowed = root.resolve()
    candidate = (allowed / filename).resolve()
    if not candidate.is_relative_to(allowed):
        return ""
    return candidate.read_text()
