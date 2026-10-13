"""Select exactly one configured read-only source; tokens never enter the snapshot."""
from contextlib import asynccontextmanager
import base64
import os
from httpx2 import AsyncClient
from corsair.adapters.azure_work_items import AzureWorkItems
from corsair.adapters.github_issues import GitHubIssues
from corsair.ports.tickets import TicketError
from .config import AzureConfig, GitHubConfig


@asynccontextmanager
async def ticket_source(config, *, transport=None):
    token = None
    if config.token_env is not None:
        token = os.environ.get(config.token_env)
        if not token:
            raise TicketError(config.provider, 'credential_missing', f'Set {config.token_env} in the operator environment.')
    headers = {}
    if isinstance(config, GitHubConfig):
        headers.update({'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        if token:
            headers['Authorization'] = f'Bearer {token}'
        adapter = GitHubIssues
    elif isinstance(config, AzureConfig):
        headers['Authorization'] = ('Basic ' + base64.b64encode((':' + token).encode()).decode()
                                    if config.auth == 'pat' else 'Bearer ' + token)
        adapter = AzureWorkItems
    else:
        raise TypeError('validated ticket configuration required')
    async with AsyncClient(headers=headers, transport=transport, follow_redirects=False, timeout=config.timeout_seconds) as client:
        yield adapter(config, client)
