"""Read-only, pinned GitHub source acquisition through PyGithub."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from corsair.domain.case import GitSource

from .archive import acquire_cached, install_archive, tree_at

GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
GITHUB_API_URL_ENV = "CORSAIR_GITHUB_API_URL"
DEFAULT_GITHUB_API_URL = "https://api.github.com"
HTTP_TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 5
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def _operator_url(value: str, *, name: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{name} has an invalid port") from error
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
        raise ValueError(f"{name} must be an HTTPS URL without credentials, query, or fragment")
    return parsed


def _github_repository(source: GitSource, api_url: str) -> tuple[str, str]:
    """Parse only a GitHub repository root URL belonging to the configured host."""
    api = _operator_url(api_url, name=GITHUB_API_URL_ENV)
    parsed = urlsplit(source.url)
    source_port = parsed.port
    expected_host = "github.com" if api.hostname == "api.github.com" else api.hostname
    if parsed.hostname != expected_host or source_port != api.port:
        raise ValueError("GitHub source URL host does not match the configured GitHub API")
    if parsed.path.endswith("/"):
        raise ValueError("GitHub source URL must not have a trailing slash")
    parts = parsed.path.removeprefix("/").split("/")
    if len(parts) != 2:
        raise ValueError("GitHub source URL must be https://host/owner/repository")
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not _NAME.fullmatch(owner) or not _NAME.fullmatch(repository):
        raise ValueError("GitHub source URL has an invalid owner or repository name")
    return owner, repository


def _github_token(api_url: str) -> str | None:
    token = os.environ.get(GITHUB_TOKEN_ENV)
    if token:
        return token
    hostname = urlsplit(api_url).hostname
    command = ["gh", "auth", "token"]
    if hostname != "api.github.com":
        command.extend(["--hostname", hostname or ""])
    try:
        result = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _github_client(api_url: str, token: str | None):
    """Instantiate PyGithub only while an acquisition is in progress."""
    from github import Auth, Github

    kwargs = {
        "base_url": api_url,
        "timeout": HTTP_TIMEOUT_SECONDS,
        "retry": 0,
        "seconds_between_requests": 0,
        "seconds_between_writes": 0,
    }
    if token:
        kwargs["auth"] = Auth.Token(token)
    return Github(**kwargs)


def _download_archive(url: str, target: Path, *, api_url: str, token: str | None) -> None:
    archive = urlsplit(url)
    api = urlsplit(api_url)
    api_origin = (api.hostname, api.port or 443)
    allowed_origins = {api_origin}
    if api.hostname == "api.github.com":
        allowed_origins.update({("github.com", 443), ("codeload.github.com", 443)})
    if (
        archive.scheme != "https"
        or (archive.hostname, archive.port or 443) not in allowed_origins
        or archive.username is not None
        or archive.password is not None
    ):
        raise ValueError("GitHub archive location is not a safe HTTPS URL")

    def validate_destination(request: httpx.Request) -> None:
        if (
            request.url.scheme != "https"
            or (request.url.host, request.url.port or 443) not in allowed_origins
        ):
            raise ValueError("GitHub archive location is not a safe HTTPS URL")

    headers = {"User-Agent": "corsair"}
    # PyGithub's archive location is an API URL which may redirect to codeload.
    # Let HTTPX strip Authorization on that cross-origin redirect; never attach
    # an API credential to a direct codeload location.
    if token and (archive.hostname, archive.port or 443) == api_origin:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            event_hooks={"request": [validate_destination]},
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                install_archive(response.iter_bytes(), target, strip_root=True)
    except httpx.HTTPError:
        # HTTPX error text includes the request URL, whose query can contain a
        # signed archive credential. Keep operational errors non-sensitive.
        raise ValueError("GitHub archive download failed") from None


def _normalized_api_url(value: str) -> str:
    parsed = _operator_url(value, name=GITHUB_API_URL_ENV)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


class GitHubSCM:
    """Acquire an exact GitHub commit without cloning or provider write operations."""

    def __init__(self, root: Path | None = None, *, api_url: str | None = None):
        self.root = Path(root) if root is not None else None
        self.api_url = api_url

    def acquire(self, source: GitSource, root: Path | None = None) -> Path:
        api_url = _normalized_api_url(
            self.api_url or os.environ.get(GITHUB_API_URL_ENV, DEFAULT_GITHUB_API_URL)
        )
        owner, repository = _github_repository(source, api_url)
        cache_root = Path(root) if root is not None else self.root

        def populate(target: Path) -> None:
            token = _github_token(api_url)
            client = _github_client(api_url, token)
            try:
                remote = client.get_repo(f"{owner}/{repository}")
                commit = remote.get_commit(source.commit)
                if commit.sha != source.commit:
                    raise ValueError("GitHub did not resolve the requested immutable commit")
                _download_archive(
                    remote.get_archive_link("zipball", source.commit),
                    target,
                    api_url=api_url,
                    token=token,
                )
            finally:
                client.close()

        target = acquire_cached(source, provider="github", root=cache_root, populate=populate)
        return tree_at(source, target)
