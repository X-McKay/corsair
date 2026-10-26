import functools


@functools.cache
def read_file(root, path):
    with open(root + "/" + path, encoding="utf-8") as handle:
        return handle.read()
