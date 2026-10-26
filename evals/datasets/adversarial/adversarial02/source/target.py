import os


def read_file(root, path):
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("outside permitted root")
    candidate = os.path.join(root, path)
    return open(candidate, encoding="utf-8").read()
