import os

def read_file(root, path):
    target = os.path.realpath(os.path.join(root, path))
    if os.path.commonpath([os.path.realpath(root), target]) != os.path.realpath(root):
        raise ValueError("outside permitted root")
    return open(target, encoding="utf-8").read()
