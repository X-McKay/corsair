"""The reconciler: remove every sandbox labelled ``corsair.v2=1`` (optionally for one run) and report, never hide,
the ones whose removal could not be confirmed (``cleanup_unconfirmed``). It sweeps the configured backend only."""
from __future__ import annotations

from dataclasses import dataclass

from .workspace import sandboxes as configured
from .workspace.port import Sandboxes


@dataclass(frozen=True)
class Sweep:
    removed: tuple[str, ...]
    unconfirmed: tuple[str, ...]


def labelled(run_id: str | None = None, *, backend: Sandboxes | None = None) -> list[str]:
    return (backend or configured()).labelled(run_id)


def sweep(run_id: str | None = None, *, backend: Sandboxes | None = None) -> Sweep:
    backend = backend or configured()
    removed, unconfirmed = [], []
    for name in backend.labelled(run_id):
        (removed if backend.remove(name) else unconfirmed).append(name)
    return Sweep(tuple(removed), tuple(unconfirmed))
