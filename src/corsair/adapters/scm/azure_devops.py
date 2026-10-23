"""Read-only, pinned Azure DevOps source acquisition through azure-devops."""

from __future__ import annotations

import os
from contextlib import closing, nullcontext
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from corsair.domain.case import GitSource

from .archive import acquire_cached, install_archive, tree_at

AZURE_DEVOPS_PAT_ENV = "AZURE_DEVOPS_PAT"
AZURE_DEVOPS_API_URL_ENV = "CORSAIR_AZURE_DEVOPS_API_URL"
DEFAULT_AZURE_DEVOPS_API_URL = "https://dev.azure.com"
HTTP_TIMEOUT_SECONDS = 30


def _operator_url(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{AZURE_DEVOPS_API_URL_ENV} has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise ValueError(
            f"{AZURE_DEVOPS_API_URL_ENV} must be an HTTPS URL without credentials, query, or fragment"
        )
    return parsed


def _segment(value: str, *, name: str) -> str:
    decoded = unquote(value)
    if not decoded or len(decoded) > 256 or any(character in decoded for character in "/\\\0"):
        raise ValueError(f"Azure DevOps source URL has an invalid {name}")
    if decoded in (".", "..") or decoded.strip() != decoded:
        raise ValueError(f"Azure DevOps source URL has an invalid {name}")
    return decoded


def _azure_repository(source: GitSource, api_url: str) -> tuple[str, str, str]:
    """Parse a canonical web URL below the operator-owned Azure API base URL."""
    base = _operator_url(api_url)
    parsed = urlsplit(source.url)
    if parsed.hostname != base.hostname or parsed.port != base.port:
        raise ValueError("Azure DevOps source URL host does not match the configured Azure DevOps API")
    prefix = [part for part in base.path.split("/") if part]
    if parsed.path.endswith("/"):
        raise ValueError("Azure DevOps source URL must not have a trailing slash")
    parts = parsed.path.removeprefix("/").split("/")
    if any(not part for part in parts):
        raise ValueError("Azure DevOps source URL has an empty path segment")
    if parts[: len(prefix)] != prefix:
        raise ValueError("Azure DevOps source URL is outside the configured API base path")
    suffix = parts[len(prefix) :]
    if len(suffix) != 4 or suffix[2] != "_git":
        raise ValueError("Azure DevOps source URL must be https://host/organization/project/_git/repository")
    organization, project, _, repository = suffix
    return (
        _segment(organization, name="organization"),
        _segment(project, name="project"),
        _segment(repository, name="repository"),
    )


def _normalized_api_url(value: str) -> str:
    parsed = _operator_url(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _azure_client(api_url: str, organization: str, token: str):
    """Instantiate the official SDK only while an acquisition is in progress."""
    from azure.devops.connection import Connection
    from msrest.authentication import BasicAuthentication

    connection = Connection(base_url=f"{api_url}/{organization}", creds=BasicAuthentication("", token))
    try:
        connection._config.connection.timeout = HTTP_TIMEOUT_SECONDS
        client = connection.clients_v7_1.get_git_client()
        client.config.connection.timeout = HTTP_TIMEOUT_SECONDS
        return connection, client
    except BaseException:
        # azure-devops 7.1.0b4 exposes no public close() on Connection or its
        # generated GitClient; their owned msrest ServiceClient is the SDK's
        # available cleanup handle.
        connection._client.close()
        raise


def _version_descriptor(commit: str):
    from azure.devops.v7_1.git.models import GitVersionDescriptor

    return GitVersionDescriptor(version=commit, version_type="commit")


class AzureDevOpsSCM:
    """Acquire an exact Azure DevOps commit with only Git read APIs."""

    def __init__(self, root: Path | None = None, *, api_url: str | None = None):
        self.root = Path(root) if root is not None else None
        self.api_url = api_url

    def acquire(self, source: GitSource, root: Path | None = None) -> Path:
        api_url = _normalized_api_url(
            self.api_url or os.environ.get(AZURE_DEVOPS_API_URL_ENV, DEFAULT_AZURE_DEVOPS_API_URL)
        )
        organization, project, repository = _azure_repository(source, api_url)
        cache_root = Path(root) if root is not None else self.root

        def populate(target: Path) -> None:
            token = os.environ.get(AZURE_DEVOPS_PAT_ENV)
            if not token:
                raise ValueError(f"{AZURE_DEVOPS_PAT_ENV} is required for Azure DevOps source acquisition")
            connection, client = _azure_client(api_url, organization, token)
            try:
                commit = client.get_commit(source.commit, repository_id=repository, project=project)
                if commit.commit_id != source.commit:
                    raise ValueError("Azure DevOps did not resolve the requested immutable commit")
                archive = client.get_item_zip(
                    repository_id=repository,
                    path="/",
                    project=project,
                    scope_path="/",
                    recursion_level="Full",
                    download=True,
                    version_descriptor=_version_descriptor(source.commit),
                )
                archive_context = closing(archive) if hasattr(archive, "close") else nullcontext(archive)
                with archive_context:
                    # Azure's get_item_zip returns the requested tree itself,
                    # unlike GitHub's documented zipball wrapper directory.
                    install_archive(archive, target, strip_root=False)
            finally:
                try:
                    client._client.close()
                finally:
                    connection._client.close()

        target = acquire_cached(source, provider="azure_devops", root=cache_root, populate=populate)
        return tree_at(source, target)
