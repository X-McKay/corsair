"""Pinned Git acquisition with a content-addressed checkout cache."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from corsair.domain.case import GitSource

SOURCES_ENV = "CORSAIR_SOURCES"


def sources_root() -> Path:
    """The operator-owned cache location, evaluated only when acquisition is requested."""
    return Path(os.environ.get(SOURCES_ENV) or Path.cwd() / ".runs" / "sources")


class GitSCM:
    """Acquire exactly one immutable commit without repository hooks or file transport."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else None

    def acquire(self, source: GitSource, root: Path | None = None) -> Path:
        key = hashlib.sha256(f"{source.url}\n{source.commit}".encode()).hexdigest()[:24]
        target = (Path(root) if root is not None else self.root or sources_root()) / key
        marker = target / ".corsair-complete"
        if not marker.is_file():
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)
            git = [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "protocol.file.allow=never",
                "-C",
                str(target),
            ]
            subprocess.run([*git, "init", "-q"], check=True, stdin=subprocess.DEVNULL)
            subprocess.run(
                [*git, "fetch", "-q", "--depth", "1", source.url, source.commit],
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=900,
            )
            subprocess.run(
                [*git, "-c", "advice.detachedHead=false", "checkout", "-q", source.commit],
                check=True,
                stdin=subprocess.DEVNULL,
            )
            marker.write_text(f"{source.url}\n{source.commit}\n")
        tree = target / source.subdir if source.subdir else target
        if not tree.is_dir() or not tree.resolve().is_relative_to(target.resolve()):
            raise ValueError(f"subdir {source.subdir!r} is not a directory inside the checkout")
        return tree
