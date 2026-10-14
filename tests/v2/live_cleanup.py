"""Cleanup evidence for live sandbox tests: one JSON line per removed sandbox in ``$CORSAIR_EVIDENCE_DIR``."""
from __future__ import annotations

import json
import os
from pathlib import Path

EVIDENCE_ENV = "CORSAIR_EVIDENCE_DIR"


def record_cleanup(backend: str, name: str, confirmed: bool) -> None:
    """Append ``{backend, name, confirmed}`` to ``cleanup.jsonl`` when an evidence directory is set."""
    directory = os.environ.get(EVIDENCE_ENV)
    if directory:
        with (Path(directory) / "cleanup.jsonl").open("a") as stream:
            stream.write(json.dumps({"backend": backend, "name": name, "confirmed": confirmed}) + "\n")


def remove_confirmed(sandboxes, names) -> list[str]:
    """Remove each sandbox, record the result and return the names whose absence was not confirmed."""
    unconfirmed = []
    for name in names:
        confirmed = bool(sandboxes.remove(name))
        record_cleanup(sandboxes.provider, name, confirmed)
        if not confirmed:
            unconfirmed.append(name)
    return unconfirmed
