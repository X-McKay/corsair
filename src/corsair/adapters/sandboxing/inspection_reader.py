"""Fixed container reader. This module never imports or executes target source."""

import json
import os
import stat
import sys
from pathlib import Path


def _path(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if (
        not relative
        or any(part in {"", ".", ".."} for part in parts)
        or "\\" in relative
        or "\x00" in relative
    ):
        raise ValueError("unsafe inspection path")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("inspection symlinks are forbidden")
    return current


def inspect_source(root: Path, operation: str, relative: str, limit: int) -> dict:
    if not 1024 <= limit <= 131072:
        raise ValueError("invalid inspection output limit")
    if operation == "read":
        path = _path(root, relative)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("inspection requires a regular file")
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError("inspection read exceeds output limit")
        return {"content": content.decode("utf-8")}
    if operation != "list":
        raise ValueError("unknown inspection operation")
    names: list[str] = []
    size = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(files):
            relative = (Path(directory) / name).relative_to(root).as_posix()
            path = _path(root, relative)
            if not path.is_file():
                raise ValueError("inspection requires regular files")
            size += len(relative.encode()) + 4
            if size > limit // 6:
                return {"files": names, "truncated": True}
            names.append(relative)
    return {"files": names, "truncated": False}


def main() -> None:
    try:
        result = inspect_source(Path("/source"), sys.argv[1], sys.argv[2], int(sys.argv[3]))
    except (ValueError, OSError, UnicodeError):
        result = {"error": "inspection read denied or exceeds limit"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
