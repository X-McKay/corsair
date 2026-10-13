import asyncio
import json

import pytest
from httpx2 import MockTransport, Response
from corsair.ports.tickets import TicketError
from corsair.tickets.config import AzureConfig, GitHubConfig
from corsair.tickets.source import ticket_source
from corsair.tickets.inputs import identification_input

NOW = '2026-10-13T12:00:00Z'


def issue(**extra):
    return dict(number=7, title='Reported behavior', body='Investigate the parser.', state='open', updated_at=NOW,
                comments=0) | extra


def capture(config, respond):
    async def go():
        async with ticket_source(config, transport=MockTransport(respond)) as source:
            return await source.capture(7)
    return asyncio.run(go())


def test_github_paginates_on_own_origin_and_maps_to_shared_input(monkeypatch):
    monkeypatch.setenv('TICKET_TOKEN', 'private-test-token')
    urls = []
    def respond(request):
        urls.append(str(request.url))
        assert request.headers['authorization'] == 'Bearer private-test-token'
        assert request.method == 'GET' and request.url.host == 'api.github.com'
        if not request.url.path.endswith('/comments'):
            return Response(200, json=issue(comments=2))
        page = request.url.params['page']
        return Response(200, json=[{'id': int(page), 'body': 'comment ' + page, 'user': {'login': 'reader'},
                                    'updated_at': NOW}], headers={'link': '<https://other.example/steal>; rel="next"'} if page == '1' else {})
    snapshot = capture(GitHubConfig(provider='github', repository='owner/repo', token_env='TICKET_TOKEN'), respond)
    assert len(snapshot.comments) == 2 and len(urls) == 4
    assert snapshot.provider == 'github' and snapshot.revision == NOW
    assert 'private-test-token' not in snapshot.model_dump_json()
    inputs = identification_input(snapshot, scope='component', source_files=())
    assert 'Reported behavior' in inputs.issue and 'comment 1' not in inputs.issue
    discussion = identification_input(snapshot, scope='component', source_files=(), include_comments=True).issue
    parsed = json.loads(discussion.split('\n', 1)[1])
    assert parsed['comments'][0]['author'] == 'reader'
    assert parsed['comments'][0]['body'] == 'comment 1'
    assert parsed['comments'][0]['role'] == 'unverified participant'
    assert parsed['comments'][0]['format'] == 'markdown'
    assert inputs.fixture_id == snapshot.digest


def test_azure_pat_pagination_and_revision(monkeypatch):
    monkeypatch.setenv('AZURE_TOKEN', 'test-pat')
    calls = []
    item = {'id': 7, 'rev': 3, 'fields': {'System.Title': 'Finding', 'System.Description': '<p>body</p>',
                                         'System.State': 'Active', 'System.ChangedDate': NOW}}
    def respond(request):
        calls.append(request)
        assert request.url.host == 'dev.azure.com'
        assert request.headers['authorization'].startswith('Basic ')
        if not request.url.path.endswith('/comments'):
            return Response(200, json=item)
        token = request.url.params.get('continuationToken')
        return Response(200, json={'comments': [{'id': 2 if token else 1, 'text': 'discussion',
                                               'modifiedDate': NOW, 'createdBy': {'displayName': 'Reader'}}],
                                  **({} if token else {'continuationToken': 'next-token'})})
    snapshot = capture(AzureConfig(provider='azure_devops', organization='org', project='Project Space',
                                   token_env='AZURE_TOKEN'), respond)
    assert snapshot.revision == '3' and snapshot.format == 'html' and len(snapshot.comments) == 2
    assert calls[2].url.params['continuationToken'] == 'next-token'
    assert 'test-pat' not in snapshot.model_dump_json()


@pytest.mark.parametrize('status,code', [(401, 'authentication'), (403, 'access_or_rate_limit'),
                                        (404, 'not_found_or_hidden'), (429, 'rate_limit'), (500, 'http_error'),
                                        (302, 'http_error')])
def test_errors_are_attributed_without_response_secrets(status, code):
    calls = []
    def respond(request):
        calls.append(request)
        return Response(status, text='secret response', headers={'location': 'https://other.example'})
    with pytest.raises(TicketError) as error:
        capture(GitHubConfig(provider='github', repository='o/r'), respond)
    assert error.value.code == code and 'secret' not in str(error.value) and len(calls) == 1


def test_missing_credentials_prevent_dispatch(monkeypatch):
    monkeypatch.delenv('MISSING_TICKET_TOKEN', raising=False)
    with pytest.raises(TicketError, match='credential_missing'):
        capture(GitHubConfig(provider='github', repository='o/r', token_env='MISSING_TICKET_TOKEN'),
                lambda _: pytest.fail('must not dispatch'))


@pytest.mark.parametrize('mode', ['oversize', 'page_limit', 'pull_request', 'changed', 'invalid'])
def test_refuses_partial_or_nonissue_snapshot(mode):
    calls = []
    def respond(request):
        calls.append(request)
        if mode == 'oversize':
            return Response(200, content=b'x' * 1025)
        if mode == 'invalid':
            return Response(200, json=[])
        if mode == 'pull_request':
            return Response(200, json=issue(pull_request={}))
        if request.url.path.endswith('/comments'):
            return Response(200, json=[], headers={'link': '<https://api.github.com/next>; rel="next"'} if mode == 'page_limit' else {})
        return Response(200, json=issue(updated_at='2026-10-14T00:00:00Z' if mode == 'changed' and len(calls) > 1 else NOW))
    with pytest.raises(TicketError) as error:
        capture(GitHubConfig(provider='github', repository='o/r', max_bytes=1024, max_pages=1), respond)
    assert error.value.code == {'oversize': 'size_limit', 'page_limit': 'page_limit', 'pull_request': 'not_issue',
                                 'changed': 'changed_during_capture', 'invalid': 'invalid_response'}[mode]


def test_large_ticket_bridge_refuses_instead_of_truncating():
    snapshot = capture(GitHubConfig(provider='github', repository='o/r'),
                       lambda r: Response(200, json=[] if r.url.path.endswith('/comments') else issue(body='x' * 9000)))
    with pytest.raises(ValueError, match='budget'):
        snapshot.issue_text()


def test_azure_bearer_repeated_token_is_refused(monkeypatch):
    monkeypatch.setenv('AZURE_TOKEN', 'test-access-token')
    item = {'id': 7, 'rev': 1, 'fields': {}}
    def respond(request):
        assert request.headers['authorization'] == 'Bearer test-access-token'
        return Response(200, json={'comments': [], 'continuationToken': 'same'} if request.url.path.endswith('/comments') else item)
    with pytest.raises(TicketError, match='invalid_response'):
        capture(AzureConfig(provider='azure_devops', organization='org', project='p', token_env='AZURE_TOKEN', auth='bearer'), respond)


def test_transport_error_is_actionable_and_redacted():
    from httpx2 import ConnectError
    def respond(request):
        raise ConnectError('secret-proxy-token', request=request)
    with pytest.raises(TicketError) as error:
        capture(GitHubConfig(provider='github', repository='o/r'), respond)
    assert error.value.code == 'transport' and 'TLS' in error.value.action
    assert 'secret-proxy-token' not in str(error.value)


def test_capture_output_is_exclusive_private_and_digested(tmp_path, monkeypatch):
    import stat
    from contextlib import asynccontextmanager
    from corsair.configuration import ProviderConfig
    from corsair.tickets import capture as cli
    snapshot = capture(GitHubConfig(provider='github', repository='o/r'),
                       lambda r: Response(200, json=[] if r.url.path.endswith('/comments') else issue()))
    @asynccontextmanager
    async def source(_):
        class Source:
            async def capture(self, number):
                return snapshot
        yield Source()
    monkeypatch.setattr(cli, 'ticket_source', source)
    config = ProviderConfig.model_validate({'inference': {'models': {'m': {'provider': 'vllm',
        'base_url': 'https://model.example/v1', 'model_name': 'm'}}, 'default': 'm'},
        'tickets': {'provider': 'github', 'repository': 'o/r'}})
    output = tmp_path / 'ticket.json'
    asyncio.run(cli.capture(config, 7, output))
    assert json.loads(output.read_text())['sha256'] == snapshot.digest
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        asyncio.run(cli.capture(config, 7, output))


@pytest.mark.parametrize('repository', ['../repo', 'owner/..', './repo', 'owner/.'])
def test_github_repository_rejects_dot_segments(repository):
    with pytest.raises(ValueError):
        GitHubConfig(provider='github', repository=repository)


def test_azure_comment_edit_without_revision_change_is_refused(monkeypatch):
    monkeypatch.setenv('AZURE_TOKEN', 'test')
    calls = 0
    item = {'id': 7, 'rev': 3, 'fields': {'System.Title': 'Finding', 'System.State': 'Active', 'System.ChangedDate': NOW}}
    def respond(request):
        nonlocal calls
        if not request.url.path.endswith('/comments'):
            return Response(200, json=item)
        calls += 1
        return Response(200, json={'comments': [{'id': 1, 'text': f'edit {calls}', 'modifiedDate': NOW}]})
    with pytest.raises(TicketError) as error:
        capture(AzureConfig(provider='azure_devops', organization='org', project='project', token_env='AZURE_TOKEN'), respond)
    assert error.value.code == 'changed_during_capture'


def test_failed_capture_releases_reserved_output(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from corsair.tickets import capture as cli
    @asynccontextmanager
    async def fail(config):
        raise TicketError('github', 'transport', 'Check connectivity.')
        yield
    monkeypatch.setattr(cli, 'ticket_source', fail)
    path = tmp_path / 'ticket.json'
    for _ in range(2):
        with pytest.raises(TicketError):
            asyncio.run(cli.capture(SimpleNamespace(tickets=object()), 1, path))
        assert not path.exists()
