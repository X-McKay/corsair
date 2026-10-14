"""The reconciler: remove every container labelled ``corsair.v2=1`` (optionally for one run) and report, never hide,
the ones whose removal could not be confirmed (``cleanup_unconfirmed``)."""
from __future__ import annotations

from dataclasses import dataclass

from .workspace.docker import LABEL, RUN_LABEL, docker, remove


@dataclass(frozen=True)
class Sweep:
    removed: tuple[str, ...]
    unconfirmed: tuple[str, ...]


def labelled(run_id: str | None = None) -> list[str]:
    filters = ["--filter", f"label={LABEL}=1"] + (["--filter", f"label={RUN_LABEL}={run_id}"] if run_id else [])
    listed = docker("ps", "--all", "--no-trunc", *filters, "--format", "{{.Names}}")
    if listed.returncode != 0:
        raise RuntimeError(f"cannot list containers: {listed.stderr.decode(errors='replace')[-2000:]}")
    return sorted(listed.stdout.decode().split())


def sweep(run_id: str | None = None) -> Sweep:
    removed, unconfirmed = [], []
    for name in labelled(run_id):
        (removed if remove(name) else unconfirmed).append(name)
    return Sweep(tuple(removed), tuple(unconfirmed))
