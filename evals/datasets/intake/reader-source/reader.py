from pathlib import Path


def read_file(root, path):
    """Read one file under root."""
    return (Path(root) / path).read_text()
