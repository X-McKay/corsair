from pathlib import Path


def resolve_asset(root: str, name: str) -> str:
    """Return an asset's text."""
    return (Path(root) / name).read_text(encoding="utf-8")
