"""Sandbox backends: the ``Sandboxes`` port for trusted code and the PydanticAI workspace backend for agents,
implemented over Docker. ``sandboxes()`` selects the backend explicitly from ``CORSAIR_SANDBOX`` (``docker`` when
unset); any other value is an error. An OpenShell backend implementing the same port is the intended production
adapter and is not part of the pilot.
"""
from __future__ import annotations

import os

from .docker import DockerConfig, DockerSandboxes, DockerWorkspace
from .port import Exec, SandboxExists, Sandboxes, SandboxSpec, labels, sandbox_name

BACKEND_ENV = "CORSAIR_SANDBOX"
BACKENDS = ("docker",)


def sandboxes(name: str | None = None) -> Sandboxes:
    chosen = name or os.environ.get(BACKEND_ENV) or "docker"
    if chosen == "docker":
        return DockerSandboxes()
    raise ValueError(f"unknown {BACKEND_ENV} {chosen!r}; expected one of {', '.join(BACKENDS)}")


__all__ = ("BACKENDS", "DockerConfig", "DockerSandboxes", "DockerWorkspace", "Exec", "SandboxExists", "SandboxSpec",
           "Sandboxes", "labels", "sandbox_name", "sandboxes")
