"""Workspace backends for v2: the native PydanticAI workspace interface for agents and the ``Sandboxes`` port for
trusted code, implemented over Docker (the default) and OpenShell.

``sandboxes()`` selects the backend explicitly from ``CORSAIR_WORKSPACE`` (``docker`` when unset, or
``openshell``, which reads its operator config from ``CORSAIR_OPENSHELL_CONFIG``). Any other value is an error;
there is no fallback from one backend to another.
"""
from __future__ import annotations

import os
from pathlib import Path

from .docker import DockerConfig, DockerSandboxes, DockerWorkspace
from .port import Exec, SandboxExists, Sandboxes, SandboxSpec, labels, sandbox_name

BACKEND_ENV = "CORSAIR_WORKSPACE"
OPENSHELL_CONFIG_ENV = "CORSAIR_OPENSHELL_CONFIG"
BACKENDS = ("docker", "openshell")


def sandboxes(name: str | None = None) -> Sandboxes:
    """The configured backend. ``name`` overrides the environment variable."""
    chosen = name or os.environ.get(BACKEND_ENV) or "docker"
    if chosen == "docker":
        return DockerSandboxes()
    if chosen == "openshell":
        config = os.environ.get(OPENSHELL_CONFIG_ENV)
        if not config:
            raise ValueError(f"{BACKEND_ENV}=openshell needs {OPENSHELL_CONFIG_ENV} (the operator's OpenShell config)")
        from .openshell import OpenShellSandboxes

        return OpenShellSandboxes.from_config(Path(config))
    raise ValueError(f"unknown {BACKEND_ENV} {chosen!r}; expected one of {', '.join(BACKENDS)}")


__all__ = ("BACKENDS", "DockerConfig", "DockerSandboxes", "DockerWorkspace", "Exec", "SandboxExists", "SandboxSpec",
           "Sandboxes", "labels", "sandbox_name", "sandboxes")
