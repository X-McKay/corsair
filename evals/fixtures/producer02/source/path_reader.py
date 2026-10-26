from pathlib import Path


def read_document(document_root: str, relative_path: str) -> str:
    return (Path(document_root) / relative_path).read_text(encoding="utf-8")
