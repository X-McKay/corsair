"""An issue id becomes the same issue request an issue JSON file carries; no network (mock transport)."""
import asyncio
import json

import pytest
from httpx2 import MockTransport, Response

from corsair.investigate import request_for_id
from corsair.investigation.build import repository_of
from corsair.investigation.issue_id import IssueIdRefused, capture, parse, source_config
from corsair.tickets.config import AzureConfig, GitHubConfig

NOW = "2026-10-13T12:00:00Z"
ISSUE = {"number": 42, "title": "Command injection in lib/run.js", "body": "lib/run.js reaches a shell.",
         "state": "open", "updated_at": NOW, "comments": 0}


def github(request):
    assert request.method == "GET" and request.url.path.startswith("/repos/acme/files/issues/42")
    assert request.url.host == "api.github.com" and "authorization" not in request.headers
    return Response(200, json=[] if request.url.path.endswith("/comments") else ISSUE)


def test_issue_ids_parse_and_refuse_anything_else():
    assert parse("github:acme/files#42") == ("github", "acme/files", 42)
    assert parse("azure:contoso/Payments API#7") == ("azure", "contoso/Payments API", 7)
    for text in ("acme/files#42", "github:acme/files", "github:acme/files#0", "gitlab:acme/files#1", "github:acme#x"):
        with pytest.raises(IssueIdRefused):
            parse(text)


def test_a_source_uses_the_operators_configuration_when_it_names_it():
    configured = GitHubConfig(provider="github", repository="acme/files", token_env="GH_TOKEN")
    assert source_config("github", "acme/files", configured) is configured
    assert source_config("github", "ACME/Files", configured) is configured
    # The configured source is the allowlist: another repository, or none configured, is refused.
    for source, given in (("other/repo", configured), ("acme/files", None)):
        with pytest.raises(IssueIdRefused, match="not the configured tickets source"):
            source_config("github", source, given)
    azure = AzureConfig(provider="azure_devops", organization="contoso", project="Payments", token_env="ADO_PAT")
    assert source_config("azure", "contoso/Payments", azure) is azure
    with pytest.raises(IssueIdRefused, match="configured organization, project and token"):
        source_config("azure", "contoso/Other", azure)


def test_a_github_issue_id_becomes_an_issue_request_with_its_own_repository(tmp_path, monkeypatch):
    configured = GitHubConfig(provider="github", repository="acme/files")
    snapshot = asyncio.run(capture("github:acme/files#42", configured, transport=MockTransport(github)))
    assert (snapshot.provider, snapshot.source, snapshot.id, snapshot.title) == (
        "github", "acme/files", "42", "Command injection in lib/run.js")

    async def captured(text, configured):
        assert isinstance(configured, GitHubConfig) and configured.repository == "acme/files"
        return await capture(text, configured, transport=MockTransport(github))
    monkeypatch.setattr("corsair.investigate.capture_issue", captured)
    config = tmp_path / "provider.json"
    config.write_text(json.dumps({"inference": {"models": {"m": {"provider": "vllm", "base_url": "https://model.example/v1",
                                                                 "model_name": "m"}}, "default": "m"},
                                  "tickets": {"provider": "github", "repository": "acme/files"}}))
    request = asyncio.run(request_for_id("github:acme/files#42", config, repository=None, revision="a" * 40,
                                         fixed_revision="b" * 40, scope=None))
    assert request.label == "github:acme/files#42" and "Command injection in lib/run.js" in request.issue_text()
    assert (request.revision, request.fixed_revision, request.repository) == ("a" * 40, "b" * 40, None)
    assert repository_of(request) == ("https://github.com/acme/files", "ticket")


def test_the_command_takes_an_id_or_a_file_never_both_and_flags_only_with_an_id(tmp_path, capsys):
    from corsair.investigate import main
    base = ["--provider-config", str(tmp_path / "provider.json"), "--evidence", str(tmp_path / "out")]
    for argv in (["--id", "github:acme/files#42", "--issue-json", "x.json"], ["--issue-json", "x.json", "--revision", "a" * 40]):
        with pytest.raises(SystemExit):
            main(argv + base)
    assert "--issue-json carries revision itself" in capsys.readouterr().err
