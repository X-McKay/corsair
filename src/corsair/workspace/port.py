"""The sandbox port trusted code runs through: build replay, probe execution and the reconciler.

Agents never see this port. They get a PydanticAI ``WorkspaceBackend`` (``Sandboxes.agent_workspace``); trusted code
gets the synchronous operations below, which every backend implements with the same semantics:

- ``create`` never adopts: an identity already held raises ``SandboxExists`` (an earlier, uncertain attempt that
  trusted code must not reuse, and must not remove either; the reconciler sweeps it with its run).
- ``exec_once`` runs a command exactly once and is never retried; a timeout or a lost sandbox is an ``Exec`` fact.
- ``remove`` returns whether the sandbox's absence was confirmed; False is ``cleanup_unconfirmed``.
- An environment (``seal_environment`` / ``open_environment``) is the replayed recipe on the revision tree. Docker
  commits it to an image; a backend that cannot snapshot replays the sealed recipe into each fresh sandbox.

Backends are selected explicitly (``corsair.workspace.sandboxes``); there is no silent fallback.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic_ai.workspaces import WorkspaceError

if TYPE_CHECKING:
    from ..contracts import Environment, Recipe

LABEL = "corsair.v2"
RUN_LABEL = "corsair.v2.run"
STAGE_LABEL = "corsair.v2.stage"
ROLE_LABEL = "corsair.v2.role"


def labels(run_id: str, stage: str, role: str | None = None, **extra: str) -> dict[str, str]:
    """The identity labels of one sandbox: the run, the stage and, where there is one, the role."""
    found = {RUN_LABEL: run_id, STAGE_LABEL: stage} | ({ROLE_LABEL: role} if role else {})
    return found | {f"{LABEL}.{key}": value for key, value in extra.items()}


def sandbox_name(sandbox_labels: Mapping[str, str]) -> str:
    """Deterministic: the same labels always name the same sandbox, so a retried create finds it."""
    all_labels = {LABEL: "1", **sandbox_labels}
    digest = hashlib.sha256(json.dumps(all_labels, sort_keys=True).encode()).hexdigest()[:12]
    parts = [sandbox_labels.get(key, "") for key in (RUN_LABEL, STAGE_LABEL, ROLE_LABEL)]
    slug = re.sub(r"[^a-z0-9_.-]+", "-", "-".join(part for part in parts if part).lower()).strip("-.")[:48]
    return f"corsair-v2-{slug + '-' if slug else ''}{digest}"


class SandboxExists(WorkspaceError):
    """A sandbox already holds this identity: an earlier, uncertain attempt that trusted code must not reuse."""


@dataclass(frozen=True)
class SandboxSpec:
    """Everything needed to create one sandbox, as data. Building it does no I/O.

    ``network`` is ``none`` (probes, baselines) or ``build`` (recipe setup that installs declared dependencies);
    each backend maps ``build`` to its own egress rule (Docker: the default bridge; OpenShell: the operator's build
    policy)."""

    image: str
    labels: Mapping[str, str] = field(default_factory=dict)
    network: Literal["none", "build"] = "none"
    workdir: str = "/work"

    def __post_init__(self) -> None:
        if self.network not in ("none", "build"):
            raise ValueError("network must be 'none' or 'build'")
        if not self.workdir.startswith("/") or posixpath.normpath(self.workdir) != self.workdir:
            raise ValueError("workdir must be an absolute, normalized path")

    @property
    def name(self) -> str:
        return sandbox_name(self.labels)


@dataclass(frozen=True)
class Exec:
    """One command's observed result. ``exit_code`` is None when it timed out or the sandbox failed."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    container_failed: bool = False


@runtime_checkable
class Sandboxes(Protocol):
    """One backend's trusted operations. Every method is synchronous and bounded by the backend's own limits."""

    provider: str
    workdir: str
    """The directory trusted code works in on this backend: writable by the command user under its own policy
    (Docker ``/work``; OpenShell its native workdir ``/sandbox``). Replay records it in the Environment."""

    def create(self, spec: SandboxSpec) -> str:
        """Create and start the sandbox named ``spec.name`` with ``spec.workdir`` existing and writable by the user
        commands run as (Docker makes that user its owner; OpenShell's ``/sandbox`` is root-owned and writable under
        ``include_workdir``). Raises ``SandboxExists`` when that name is already held."""
        ...

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        """Copy a host directory's contents into an existing directory, owned by the sandbox user; symlinks are
        copied as links, never followed."""
        ...

    def write_file(self, name: str, path: str, data: bytes) -> None:
        """Write one file as the sandbox user, creating its parents."""
        ...

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        """Read declared regular files; a missing or non-regular path maps to None."""
        ...

    def exec_once(self, name: str, argv: Sequence[str], *, workdir: str, env: Mapping[str, str] | None = None,
                  timeout: float | None = None) -> Exec:
        ...

    def drop_network(self, name: str) -> None:
        """Remove all network from a ``build`` sandbox before anything is tested in it; raises if not confirmed."""
        ...

    def image_id(self, name: str) -> str | None:
        """The immutable id of the image the sandbox was created from; None when the backend cannot say."""
        ...

    def resolve_image(self, reference: str) -> str | None:
        """The immutable id of an image reference (provenance of a runtime row's image); None when unknown. Never
        raises."""
        ...

    def remove(self, name: str) -> bool:
        ...

    def labelled(self, run_id: str | None = None) -> list[str]:
        """Names of every sandbox carrying ``corsair.v2=1`` (and, given one, this run's label)."""
        ...

    def find_environment(self, tag: str, key: str) -> str | None:
        """The build-log digest of a sealed environment with this tag and key; None when none is sealed or what it
        was sealed from can no longer be opened (so replay rebuilds it)."""
        ...

    def seal_environment(self, name: str, tag: str, key: str, log_sha256: str, *, recipe: Recipe,
                         tree_source: Path, base_image: str, setup_timeout: float | None = None,
                         baseline_timeout: float | None = None) -> None:
        """Record the replayed sandbox ``name`` as the environment ``tag`` (whose baseline passed). The timeouts are
        the ones replay used, for a backend that replays the recipe again on open."""
        ...

    def open_environment(self, environment: Environment, sandbox_labels: Mapping[str, str]) -> str:
        """A fresh, offline sandbox holding the sealed environment, ready for one probe. Raises ``SandboxExists``
        when the identity is held; the returned name is always ``sandbox_name(sandbox_labels)``."""
        ...

    def agent_workspace(self, image: str, sandbox_labels: Mapping[str, str]):  # -> WorkspaceBackend
        """A PydanticAI ``WorkspaceBackend`` with build network, plus ``copy_in(source)`` and ``destroy()``."""
        ...
