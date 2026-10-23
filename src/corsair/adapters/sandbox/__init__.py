"""Explicit Docker sandbox selection at the composition boundary.

Unsupported backends are errors, never fallback choices. Future adapters are not pre-registered.
"""

from __future__ import annotations

import os

from corsair.adapters.sandbox.docker import DockerConfig, DockerSandboxes
from corsair.ports.sandbox import Exec, Sandboxes, SandboxExists, SandboxSpec, labels, sandbox_name

BACKEND_ENV = "CORSAIR_SANDBOX"
BACKENDS = ("docker",)


def sandboxes(name: str | None = None) -> Sandboxes:
    chosen = name or os.environ.get(BACKEND_ENV) or "docker"
    if chosen == "docker":
        return DockerSandboxes()
    raise ValueError(f"unknown {BACKEND_ENV} {chosen!r}; expected one of {', '.join(BACKENDS)}")


__all__ = (
    "BACKENDS",
    "DockerConfig",
    "DockerSandboxes",
    "Exec",
    "SandboxExists",
    "SandboxSpec",
    "Sandboxes",
    "labels",
    "sandbox_name",
    "sandboxes",
)
