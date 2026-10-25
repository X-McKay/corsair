import os


def resolve(root, path):
    """Storage seam that the public API depends on; it rejects paths outside root."""
    target = os.path.realpath(os.path.join(root, path))
    if os.path.commonpath([os.path.realpath(root), target]) != os.path.realpath(root):
        raise ValueError("outside permitted root")
    return target


def read_file(root, path):
    return open(resolve(root, path), encoding="utf-8").read()
