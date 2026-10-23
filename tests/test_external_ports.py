"""Offline contracts for concrete external adapters and their application ports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from corsair.adapters.inference.openai import OpenAIInference
from corsair.adapters.scm.git import GitSCM
from corsair.application.cases import from_request
from corsair.domain.case import GitSource
from corsair.runtime.inference import ModelProfile, ProviderConfig


class FakeSCM:
    def __init__(self, tree: Path):
        self.tree = tree
        self.sources: list[GitSource] = []

    def acquire(self, source: GitSource, root: Path | None = None) -> Path:
        assert root is None
        self.sources.append(source)
        return self.tree


def _git_request(path: Path, *, subdir: str | None = None) -> GitSource:
    source = GitSource(url="https://example.invalid/repository.git", commit="a" * 40, subdir=subdir)
    path.write_text(json.dumps({"finding": {"title": "t"}, "source": source.model_dump()}))
    return source


def _key(source: GitSource) -> str:
    return hashlib.sha256(f"{source.url}\n{source.commit}".encode()).hexdigest()[:24]


def test_git_case_requires_an_explicit_scm_but_local_cases_do_not(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("x = 1\n")
    request = tmp_path / "input.json"
    source = _git_request(request)

    with pytest.raises(ValueError, match="SourceControl dependency"):
        from_request(request)

    scm = FakeSCM(tree)
    case = from_request(request, scm=scm)
    assert scm.sources == [source]
    assert case.revision.source == str(tree.resolve())
    assert case.revision.commit == source.commit


def test_git_scm_reuses_complete_cache_and_rejects_subdir_escape(tmp_path, monkeypatch):
    source = GitSource(url="https://example.invalid/repository.git", commit="b" * 40)
    target = tmp_path / _key(source)
    target.mkdir()
    (target / ".corsair-complete").write_text("complete\n")

    def no_network(*args, **kwargs):
        raise AssertionError("a marked complete cache must not invoke git")

    import corsair.adapters.scm.git as git

    monkeypatch.setattr(git.subprocess, "run", no_network)
    adapter = GitSCM()
    assert adapter.acquire(source, tmp_path) == target

    escaped = source.model_copy(update={"subdir": "../outside"})
    (tmp_path / "outside").mkdir()
    with pytest.raises(ValueError, match="inside the checkout"):
        adapter.acquire(escaped, tmp_path)


def test_git_scm_uses_pinned_hookless_commands_and_completion_marker(tmp_path, monkeypatch):
    source = GitSource(url="https://example.invalid/repository.git", commit="c" * 40)
    calls: list[tuple[list[str], dict]] = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))

    import corsair.adapters.scm.git as git

    monkeypatch.setattr(git.subprocess, "run", run)
    tree = GitSCM().acquire(source, tmp_path)
    target = tmp_path / _key(source)
    assert tree == target
    assert (target / ".corsair-complete").read_text() == f"{source.url}\n{source.commit}\n"

    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "-C", str(target)]
    assert [argv for argv, _ in calls] == [
        [*command, "init", "-q"],
        [*command, "fetch", "-q", "--depth", "1", source.url, source.commit],
        [*command, "-c", "advice.detachedHead=false", "checkout", "-q", source.commit],
    ]
    assert calls[1][1]["timeout"] == 900


class FakeAsyncOpenAI:
    instances: list["FakeAsyncOpenAI"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.entered = False
        self.closed = False
        self.instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closed = True


def _shared_config(*, api_key_env: str | None = None) -> ProviderConfig:
    profile = ModelProfile(
        base_url="https://models.example/v1", model_name="test-model", api_key_env=api_key_env
    )
    return ProviderConfig(profiles={"shared": profile}, agents={"producer": "shared", "auditor": "shared"})


@pytest.mark.anyio
async def test_openai_inference_shares_and_closes_native_sdk_model_clients(monkeypatch):
    import openai

    import corsair.adapters.inference.openai as adapter

    FakeAsyncOpenAI.instances = []
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(
        adapter, "_build_model", lambda profile, *, openai_client: TestModel(model_name=profile.model_name)
    )
    async with OpenAIInference().models(_shared_config()) as models:
        assert set(models) == {"producer", "auditor"}
        assert all(isinstance(model, TestModel) for model in models.values())
        assert len(FakeAsyncOpenAI.instances) == 1
        assert FakeAsyncOpenAI.instances[0].entered and not FakeAsyncOpenAI.instances[0].closed
    assert FakeAsyncOpenAI.instances[0].closed


@pytest.mark.anyio
async def test_openai_inference_rejects_missing_credential_before_client_creation(monkeypatch):
    import openai

    created = False

    def unexpected_client(**kwargs):
        nonlocal created
        created = True
        raise AssertionError("credential validation should run before client creation")

    monkeypatch.delenv("MISSING_CORSAIR_KEY", raising=False)
    monkeypatch.setattr(openai, "AsyncOpenAI", unexpected_client)
    with pytest.raises(ValueError, match="MISSING_CORSAIR_KEY"):
        async with OpenAIInference().models(_shared_config(api_key_env="MISSING_CORSAIR_KEY")):
            pass
    assert not created
