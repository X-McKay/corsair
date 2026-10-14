"""Print the v2 runtime matrix rows as the JSON list CI fans out over: id, image tag, and the toolchain image
directory (deploy/qualification/toolchains/<toolchain>) that `make toolchain-images` builds it from.

A row whose image source is not a toolchain directory still gets a job, so the missing source fails in CI instead of
dropping out of it. Usage: uv run --locked python tools/ci_rows.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corsair import matrix  # noqa: E402

PREFIX = "deploy/qualification/toolchains/"


def rows() -> list[dict[str, str]]:
    found = []
    for row in matrix.load():
        source = (row.image_source or "").split()[0] if row.image_source else ""
        toolchain = source.removeprefix(PREFIX) if source.startswith(PREFIX) else ""
        found.append({"id": row.id, "image": row.image, "toolchain": toolchain or "missing-image-source"})
    return found


if __name__ == "__main__":
    print(json.dumps(rows(), separators=(",", ":")))
