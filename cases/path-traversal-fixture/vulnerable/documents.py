from pathlib import Path


def read_document(root: Path, filename: str) -> str:
    return (root / filename).read_text()
