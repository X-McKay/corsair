"""An issue id (`github:owner/repo#N`, `azure:org/project#N`) captured into the ticket snapshot an issue request
carries, through the existing read-only ticket readers (`corsair.tickets`). Tokens come from the operator's
configured source and never enter the snapshot or the request.
"""
import re

from corsair.ports.tickets import TicketSnapshot
from corsair.tickets.config import AzureConfig, GitHubConfig
from corsair.tickets.source import ticket_source

ISSUE_ID = re.compile(r"(?P<provider>github|azure):(?P<source>[^#\s]+(?:/[^#\n]+)?)#(?P<number>[1-9][0-9]{0,9})")


class IssueIdRefused(ValueError):
    """The id is malformed or names a source the operator has not configured."""


def parse(text: str) -> tuple[str, str, int]:
    found = ISSUE_ID.fullmatch(text.strip())
    if found is None:
        raise IssueIdRefused(f"{text!r}: expected github:owner/repo#N or azure:org/project#N")
    return found["provider"], found["source"], int(found["number"])


def source_config(provider: str, source: str, configured=None):
    """The configured source when it names this one (its token and limits); otherwise a public GitHub repository
    without a token. Azure DevOps always needs the operator's configured source and token."""
    if provider == "github":
        if isinstance(configured, GitHubConfig) and configured.repository.lower() == source.lower():
            return configured
        try:
            return GitHubConfig(provider="github", repository=source)
        except ValueError as error:
            raise IssueIdRefused(f"github:{source}: expected owner/repo") from error
    organization, _, project = source.partition("/")
    if isinstance(configured, AzureConfig) and (configured.organization, configured.project) == (organization, project):
        return configured
    raise IssueIdRefused(f"azure:{source} is not the configured tickets source; Azure DevOps needs the operator's "
                         "configured organization, project and token")


async def capture(text: str, configured=None, *, transport=None) -> TicketSnapshot:
    provider, source, number = parse(text)
    async with ticket_source(source_config(provider, source, configured), transport=transport) as reader:
        return await reader.capture(number)
