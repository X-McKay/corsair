"""Small shared report boundaries; native SDKs still own coverage computation."""

from __future__ import annotations

import json
import posixpath
from typing import Any

MAX_REPORT_BYTES = 32 * 1024 * 1024


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def load_json(data: bytes | None) -> Any:
    """Standard JSON decoding with bounded size, unique keys and no NaN/Infinity."""
    if not data or len(data) > MAX_REPORT_BYTES:
        raise ValueError("missing or oversized report")
    return json.loads(data, object_pairs_hook=_unique_keys, parse_constant=_invalid_constant)


def work_path(path: object) -> str | None:
    """Anchor relative SDK paths at /work without traversal, foreign roots or basename matching."""
    if not isinstance(path, str) or not path or any(c in path for c in ("\x00", "\\", "\r", "\n")):
        return None
    if ".." in path.split("/"):
        return None
    normalized = posixpath.normpath(path)
    if normalized in ("", "."):
        return None
    absolute = normalized if normalized.startswith("/") else f"/work/{normalized}"
    return absolute if absolute.startswith("/work/") else None
