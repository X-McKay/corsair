from pathlib import Path

def read_file(root, path):
    return (Path(root) / path).read_text()
