import os


def fetch_record(records_root: str, record_name: str, *, encoding: str) -> str:
    path = os.path.join(records_root, record_name)
    with open(path, encoding=encoding) as stream:
        return stream.read()
