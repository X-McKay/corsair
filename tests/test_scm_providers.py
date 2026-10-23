"""Read-only provider source acquisition mechanics and archive safety."""

from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from corsair.adapters.scm import (
    AzureDevOpsSCM,
    GitHubSCM,
    GitSCM,
    SourceRouter,
    azure_devops,
    github,
    source_control,
    source_control_for,
)
from corsair.adapters.scm import archive as archives
from corsair.domain.case import GitSource

COMMIT = "a" * 40


def _zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as source:
        for name, content in entries.items():
            source.writestr(name, content)
    return output.getvalue()


def _tar(member: tarfile.TarInfo, content: bytes = b"") -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as source:
        source.addfile(member, io.BytesIO(content) if member.isfile() else None)
    return output.getvalue()


def _tar_links(links: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as source:
        for name, target in links.items():
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = target
            source.addfile(member)
    return output.getvalue()


def _github_source(**changes: object) -> GitSource:
    values: dict[str, object] = {
        "provider": "github",
        "url": "https://github.com/example/project",
        "commit": COMMIT,
    }
    values.update(changes)
    return GitSource(**values)


def _azure_source(**changes: object) -> GitSource:
    values: dict[str, object] = {
        "provider": "azure_devops",
        "url": "https://dev.azure.com/example/project/_git/repository",
        "commit": COMMIT,
    }
    values.update(changes)
    return GitSource(**values)


def test_passive_constructors_and_explicit_provider_router(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    assert isinstance(GitHubSCM(), GitHubSCM)
    assert isinstance(AzureDevOpsSCM(), AzureDevOpsSCM)
    assert isinstance(source_control(), SourceRouter)
    assert isinstance(
        source_control_for(GitSource(url="https://example.invalid/r.git", commit=COMMIT)), GitSCM
    )
    assert isinstance(source_control_for(_github_source()), GitHubSCM)
    assert isinstance(source_control_for(_azure_source()), AzureDevOpsSCM)


def test_router_selects_provider_and_forwards_root(monkeypatch, tmp_path):
    calls: list[tuple[GitSource, Path | None]] = []

    class FakeSCM:
        def acquire(self, source: GitSource) -> Path:
            calls.append((source, None))
            return tmp_path / "tree"

    def fake_factory(source: GitSource, root: Path | None = None) -> FakeSCM:
        calls.append((source, root))
        return FakeSCM()

    monkeypatch.setattr("corsair.adapters.scm.source_control_for", fake_factory)
    source = _github_source()
    assert SourceRouter(tmp_path).acquire(source) == tmp_path / "tree"
    assert calls == [(source, tmp_path), (source, None)]


def test_github_uses_pygithub_commit_then_sdk_archive_link_and_atomic_cache(monkeypatch, tmp_path):
    source = _github_source(subdir="src")
    calls: list[object] = []

    class FakeRepository:
        def get_commit(self, sha: str):
            calls.append(("commit", sha))
            return SimpleNamespace(sha=COMMIT)

        def get_archive_link(self, archive_format: str, ref: str):
            calls.append(("archive-link", archive_format, ref))
            return "https://codeload.github.com/example/project/zip/refs/heads/main"

    class FakeGithub:
        def get_repo(self, name: str):
            calls.append(("repo", name))
            return FakeRepository()

        def close(self):
            calls.append("client-close")

    def fake_client(api_url: str, token: str | None) -> FakeGithub:
        calls.append(("client", api_url, token))
        return FakeGithub()

    def fake_download(url: str, target: Path, *, api_url: str, token: str | None) -> None:
        calls.append(("download", url, api_url, token))
        archives.install_archive(_zip({"project/src/main.py": b"print('ok')\n"}), target, strip_root=True)

    monkeypatch.setattr(github, "_github_token", lambda api_url: "not-logged")
    monkeypatch.setattr(github, "_github_client", fake_client)
    monkeypatch.setattr(github, "_download_archive", fake_download)
    scm = GitHubSCM(tmp_path)
    assert scm.acquire(source) == tmp_path / archives.cache_key(source, provider="github") / "src"
    assert calls == [
        ("client", "https://api.github.com", "not-logged"),
        ("repo", "example/project"),
        ("commit", COMMIT),
        ("archive-link", "zipball", COMMIT),
        (
            "download",
            "https://codeload.github.com/example/project/zip/refs/heads/main",
            "https://api.github.com",
            "not-logged",
        ),
        "client-close",
    ]
    target = tmp_path / archives.cache_key(source, provider="github")
    assert (target / ".corsair-complete").read_text() == "complete\n"
    assert "not-logged" not in (target / ".corsair-complete").read_text()
    assert (scm.acquire(source) / "main.py").read_text() == "print('ok')\n"
    assert len(calls) == 6


def test_github_rejects_unverified_commit_without_archive(monkeypatch, tmp_path):
    closed = False

    class FakeRepository:
        def get_commit(self, sha: str):
            return SimpleNamespace(sha="b" * 40)

    class FakeGithub:
        def get_repo(self, name: str):
            return FakeRepository()

        def close(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(github, "_github_client", lambda api_url, token: FakeGithub())
    monkeypatch.setattr(github, "_github_token", lambda api_url: None)
    monkeypatch.setattr(
        github, "_download_archive", lambda *args, **kwargs: pytest.fail("archive must not download")
    )
    source = _github_source()
    with pytest.raises(ValueError, match="immutable commit"):
        GitHubSCM(tmp_path).acquire(source)
    assert not (tmp_path / archives.cache_key(source, provider="github")).exists()
    assert closed


def test_github_download_uses_bounded_https_redirects_without_leaking_token(monkeypatch, tmp_path):
    requests: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"location": "https://codeload.github.com/example/project/zip/commit"},
                request=request,
            )
        return httpx.Response(200, content=_zip({"project/file.txt": b"ok"}), request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        github.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(send), **kwargs),
    )
    github._download_archive(
        "https://api.github.com/repos/example/project/zipball/commit",
        tmp_path,
        api_url="https://api.github.com",
        token="not-logged",
    )
    assert (tmp_path / "file.txt").read_bytes() == b"ok"
    assert [(request.url.host, request.headers.get("Authorization")) for request in requests] == [
        ("api.github.com", "Bearer not-logged"),
        ("codeload.github.com", None),
    ]
    with pytest.raises(ValueError, match="safe HTTPS"):
        github._download_archive(
            "https://untrusted.invalid/archive", tmp_path, api_url="https://api.github.com", token=None
        )


@pytest.mark.parametrize(
    "destination",
    [
        "http://untrusted.invalid/archive",
        "https://untrusted.invalid/archive",
        "https://api.github.com:8443/archive",
    ],
)
def test_github_download_rejects_redirect_before_sending_to_untrusted_host(
    monkeypatch, tmp_path, destination
):
    requests: list[str] = []

    def send(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": destination}, request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        github.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(send), **kwargs),
    )
    with pytest.raises(ValueError, match="safe HTTPS"):
        github._download_archive(
            "https://api.github.com/repos/example/project/zipball/commit",
            tmp_path,
            api_url="https://api.github.com",
            token="not-logged",
        )
    assert requests == ["https://api.github.com/repos/example/project/zipball/commit"]


def test_github_download_bounds_redirects_and_sanitizes_signed_url_errors(monkeypatch, tmp_path):
    requests = 0

    def redirect_forever(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(302, headers={"location": str(request.url)}, request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        github.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(redirect_forever), **kwargs),
    )
    with pytest.raises(ValueError, match="GitHub archive download failed"):
        github._download_archive(
            "https://api.github.com/repos/example/project/zipball/commit?signature=secret",
            tmp_path,
            api_url="https://api.github.com",
            token=None,
        )
    assert requests == github.MAX_REDIRECTS + 1


def test_github_cli_token_fallback_uses_configured_enterprise_host(monkeypatch):
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="token\n")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github.subprocess, "run", run)
    assert github._github_token("https://github.example.test/api/v3") == "token"
    assert github._github_token("https://api.github.com") == "token"
    assert calls == [
        ["gh", "auth", "token", "--hostname", "github.example.test"],
        ["gh", "auth", "token"],
    ]


def test_azure_uses_native_commit_and_pinned_zip_interface(monkeypatch, tmp_path):
    source = _azure_source(subdir="src")
    calls: list[object] = []

    class FakeTransport:
        def __init__(self, name: str):
            self.name = name

        def close(self):
            calls.append(("close", self.name))

    class FakeConnection:
        _client = FakeTransport("connection")

    class FakeGitClient:
        _client = FakeTransport("git")

        def get_commit(self, commit_id: str, repository_id: str, project: str):
            calls.append(("commit", commit_id, repository_id, project))
            return SimpleNamespace(commit_id=COMMIT)

        def get_item_zip(self, **kwargs):
            calls.append(("zip", kwargs))
            return io.BytesIO(_zip({"src/module.py": b"x = 1\n"}))

    descriptor = SimpleNamespace(version=COMMIT, version_type="commit")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "not-logged")
    monkeypatch.setattr(
        azure_devops,
        "_azure_client",
        lambda api, organization, token: (FakeConnection(), FakeGitClient()),
    )
    monkeypatch.setattr(azure_devops, "_version_descriptor", lambda commit: descriptor)
    assert (
        AzureDevOpsSCM(tmp_path).acquire(source)
        == tmp_path / archives.cache_key(source, provider="azure_devops") / "src"
    )
    assert calls[0] == ("commit", COMMIT, "repository", "project")
    assert calls[1] == (
        "zip",
        {
            "repository_id": "repository",
            "path": "/",
            "project": "project",
            "scope_path": "/",
            "recursion_level": "Full",
            "download": True,
            "version_descriptor": descriptor,
        },
    )
    marker = tmp_path / archives.cache_key(source, provider="azure_devops") / ".corsair-complete"
    assert marker.read_text() == "complete\n"
    assert "not-logged" not in marker.read_text()
    assert calls[-2:] == [("close", "git"), ("close", "connection")]


def test_azure_preserves_a_single_directory_archive_root(monkeypatch, tmp_path):
    calls: list[str] = []

    class FakeTransport:
        def close(self):
            calls.append("closed")

    class FakeClient:
        _client = FakeTransport()

        def get_commit(self, *args, **kwargs):
            return SimpleNamespace(commit_id=COMMIT)

        def get_item_zip(self, **kwargs):
            return io.BytesIO(_zip({"src/module.py": b"x = 1\n"}))

    class FakeConnection:
        _client = FakeTransport()

    monkeypatch.setenv("AZURE_DEVOPS_PAT", "not-logged")
    monkeypatch.setattr(
        azure_devops, "_azure_client", lambda api, organization, token: (FakeConnection(), FakeClient())
    )
    target = AzureDevOpsSCM(tmp_path).acquire(_azure_source())
    assert (target / "src/module.py").read_text() == "x = 1\n"
    assert calls == ["closed", "closed"]


def test_azure_requires_token_before_creating_sdk_client(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.setattr(azure_devops, "_azure_client", lambda *args: pytest.fail("client must stay lazy"))
    with pytest.raises(ValueError, match="AZURE_DEVOPS_PAT"):
        AzureDevOpsSCM(tmp_path).acquire(_azure_source())


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/project",
        "https://user@github.com/example/project",
        "https://github.com/example/project?token=no",
        "https://github.com/example/project#fragment",
    ],
)
def test_source_schema_rejects_noncanonical_https_urls(url):
    with pytest.raises(ValueError):
        GitSource(provider="github", url=url, commit=COMMIT)


@pytest.mark.parametrize(
    ("source", "api_url", "module", "parser"),
    [
        (
            _github_source(url="https://github.com/example/project/"),
            "https://api.github.com",
            github,
            "_github_repository",
        ),
        (
            _github_source(url="https://elsewhere.invalid/example/project"),
            "https://api.github.com",
            github,
            "_github_repository",
        ),
        (
            _azure_source(url="https://dev.azure.com/example/project/_git/repository/"),
            "https://dev.azure.com",
            azure_devops,
            "_azure_repository",
        ),
        (
            _azure_source(url="https://dev.azure.com/example//project/_git/repository"),
            "https://dev.azure.com",
            azure_devops,
            "_azure_repository",
        ),
    ],
)
def test_provider_urls_are_parsed_strictly(source, api_url, module, parser):
    with pytest.raises(ValueError):
        getattr(module, parser)(source, api_url)


def test_archive_rejects_path_traversal_and_does_not_publish_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        archives.install_archive(_zip({"root/../../escape": b"no"}), tmp_path, strip_root=True)
    assert not (tmp_path.parent / "escape").exists()


def test_archive_rejects_escaping_links_and_special_files(tmp_path):
    symlink = tarfile.TarInfo("root/link")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "../../escape"
    with pytest.raises(ValueError, match="symlink"):
        archives.install_archive(_tar(symlink), tmp_path, strip_root=True)
    hard_link = tarfile.TarInfo("root/link")
    hard_link.type = tarfile.LNKTYPE
    hard_link.linkname = "root/file"
    with pytest.raises(ValueError, match="special file or hard link"):
        archives.install_archive(_tar(hard_link), tmp_path, strip_root=True)
    device = tarfile.TarInfo("root/device")
    device.type = tarfile.CHRTYPE
    device.mode = stat.S_IFCHR | 0o600
    with pytest.raises(ValueError, match="special file or hard link"):
        archives.install_archive(_tar(device), tmp_path, strip_root=True)


def test_archive_enforces_count_and_expanded_size_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(archives, "MAX_ARCHIVE_FILES", 1)
    with pytest.raises(ValueError, match="file-count"):
        archives.install_archive(_zip({"root/one": b"1", "root/two": b"2"}), tmp_path, strip_root=True)
    monkeypatch.setattr(archives, "MAX_ARCHIVE_FILES", 10_000)
    monkeypatch.setattr(archives, "MAX_EXTRACTED_BYTES", 3)
    with pytest.raises(ValueError, match="extracted-size"):
        archives.install_archive(_zip({"root/four": b"1234"}), tmp_path, strip_root=True)


def test_cache_publishes_only_after_success_and_reuses_complete_entry(tmp_path):
    source = _github_source()
    with pytest.raises(RuntimeError, match="stop"):
        archives.acquire_cached(
            source,
            provider="github",
            root=tmp_path,
            populate=lambda _: (_ for _ in ()).throw(RuntimeError("stop")),
        )
    target = tmp_path / archives.cache_key(source, provider="github")
    assert not target.exists()
    calls = 0

    def populate(destination: Path) -> None:
        nonlocal calls
        calls += 1
        (destination / "file").write_text("ok")

    assert archives.acquire_cached(source, provider="github", root=tmp_path, populate=populate) == target
    assert archives.acquire_cached(source, provider="github", root=tmp_path, populate=populate) == target
    assert calls == 1


@pytest.mark.parametrize(
    ("entries", "strip_root"),
    [
        ({"wrapper/.corsair-complete": b"source file"}, True),
        ({"wrapper/.corsair-complete/": b""}, True),
        ({".corsair-complete": b"source file"}, False),
        ({".corsair-complete/": b""}, False),
    ],
)
def test_archive_reserved_completion_metadata_is_rejected_before_cache_publish(tmp_path, entries, strip_root):
    source = _github_source()
    target = tmp_path / archives.cache_key(source, provider="github")
    with pytest.raises(ValueError, match="reserved cache metadata"):
        archives.acquire_cached(
            source,
            provider="github",
            root=tmp_path,
            populate=lambda destination: archives.install_archive(
                _zip(entries), destination, strip_root=strip_root
            ),
        )
    assert not target.exists()


def test_archive_reserved_completion_symlink_is_rejected_before_cache_publish(tmp_path):
    source = _github_source()
    target = tmp_path / archives.cache_key(source, provider="github")
    with pytest.raises(ValueError, match="reserved cache metadata"):
        archives.acquire_cached(
            source,
            provider="github",
            root=tmp_path,
            populate=lambda destination: archives.install_archive(
                _tar_links({"wrapper/.corsair-complete": "source-file"}),
                destination,
                strip_root=True,
            ),
        )
    assert not target.exists()


@pytest.mark.parametrize("marker_target", ["wrong\n", "symlink"])
def test_cache_rejects_invalid_or_symlinked_completion_marker(tmp_path, marker_target):
    source = _github_source()
    target = tmp_path / archives.cache_key(source, provider="github")
    target.mkdir()
    marker = target / ".corsair-complete"
    if marker_target == "symlink":
        marker.symlink_to("outside")
    else:
        marker.write_text(marker_target)
    with pytest.raises(ValueError, match="completion marker is invalid"):
        archives.acquire_cached(
            source,
            provider="github",
            root=tmp_path,
            populate=lambda _: pytest.fail("invalid cached entry must not be replaced"),
        )


def test_archive_rejects_link_chain_escaping_after_github_wrapper_removal(tmp_path):
    source = _github_source()
    target = tmp_path / archives.cache_key(source, provider="github")
    with pytest.raises(ValueError, match="symlink escapes"):
        archives.acquire_cached(
            source,
            provider="github",
            root=tmp_path,
            populate=lambda destination: archives.install_archive(
                _tar_links({"wrapper/first": "second", "wrapper/second": "../outside"}),
                destination,
                strip_root=True,
            ),
        )
    assert not target.exists()


def test_archive_rejects_cyclic_symlink_chain_and_allows_dangling_internal_link(tmp_path):
    with pytest.raises(ValueError, match="symlink is cyclic"):
        archives.install_archive(
            _tar_links({"wrapper/first": "second", "wrapper/second": "first"}),
            tmp_path,
            strip_root=True,
        )
    archives.install_archive(_tar_links({"wrapper/link": "missing"}), tmp_path, strip_root=True)
    assert (tmp_path / "link").is_symlink()


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_archive_accepts_explicit_directory_entries_after_children(kind, tmp_path):
    output = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("wrapper/child", b"ok")
            archive.writestr("wrapper/", b"")
    else:
        with tarfile.open(fileobj=output, mode="w") as archive:
            child = tarfile.TarInfo("wrapper/child")
            child.size = 2
            archive.addfile(child, io.BytesIO(b"ok"))
            directory = tarfile.TarInfo("wrapper")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
    archives.install_archive(output.getvalue(), tmp_path, strip_root=True)
    assert (tmp_path / "child").read_bytes() == b"ok"
