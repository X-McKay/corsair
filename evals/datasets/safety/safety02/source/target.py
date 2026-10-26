import os


def read_file(root, path):
    return open(os.path.join(root, path), encoding="utf-8").read()
