"""Source-control adapters and explicit provider selection."""

from __future__ import annotations

from pathlib import Path

from corsair.domain.case import GitSource
from corsair.ports.scm import SourceControl

from .azure_devops import AzureDevOpsSCM
from .git import GitSCM
from .github import GitHubSCM


def source_control_for(source: GitSource, root: Path | None = None) -> SourceControl:
    """Construct the one concrete adapter selected by ``GitSource.provider``."""
    adapters = {
        "git": GitSCM,
        "github": GitHubSCM,
        "azure_devops": AzureDevOpsSCM,
    }
    return adapters[source.provider](root)


def source_control(root: Path | None = None) -> SourceControl:
    """Return the source router used by the composition root."""
    return SourceRouter(root)


class SourceRouter:
    """Route each source acquisition to its explicitly selected provider adapter."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else None

    def acquire(self, source: GitSource, root: Path | None = None) -> Path:
        cache_root = Path(root) if root is not None else self.root
        return source_control_for(source, cache_root).acquire(source)


__all__ = ["AzureDevOpsSCM", "GitHubSCM", "GitSCM", "SourceRouter", "source_control", "source_control_for"]
