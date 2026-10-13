"""GitHub REST issue capture; pull requests and incomplete discussions are refused."""
from datetime import datetime, timezone
from pydantic import ValidationError
from corsair.ports.tickets import TicketComment, TicketError, TicketSnapshot
from corsair.tickets.http import CaptureHTTP


class GitHubIssues:
    def __init__(self, config, client):
        self.config, self.client = config, client

    async def capture(self, ticket_id: int) -> TicketSnapshot:
        if type(ticket_id) is not int or ticket_id < 1:
            raise ValueError('positive integer ticket ID required')
        c = self.config
        http = CaptureHTTP(c.provider, self.client, c)
        endpoint = f'https://api.github.com/repos/{c.repository}/issues/{ticket_id}'
        item, _ = await http.get(endpoint)
        try:
            if not isinstance(item, dict) or item['number'] != ticket_id:
                raise ValueError()
            if 'pull_request' in item:
                raise TicketError(c.provider, 'not_issue', 'Provide an issue number, not a pull request.')
            comments = []
            for page in range(1, c.max_pages + 1):
                batch, headers = await http.get(endpoint + '/comments', params={'per_page': 100, 'page': page})
                if not isinstance(batch, list):
                    raise ValueError()
                for entry in batch:
                    comments.append(TicketComment(id=str(entry['id']), author=(entry.get('user') or {}).get('login'),
                                                  body=entry.get('body') or '', updated_at=entry['updated_at']))
                # Construct our own same-origin URL for every page; never follow provider-supplied links with credentials.
                if 'rel="next"' not in headers.get('link', ''):
                    break
            else:
                raise http.limit()
            if len({c.id for c in comments}) != len(comments) or len(comments) != item['comments']:
                raise TicketError(c.provider, 'changed_during_capture', 'Capture again after ticket discussion updates settle.')
            latest, _ = await http.get(endpoint)
            if (latest['updated_at'], latest['comments']) != (item['updated_at'], item['comments']):
                raise TicketError(c.provider, 'changed_during_capture', 'Capture again after ticket updates settle.')
            return TicketSnapshot(provider=c.provider, source=c.repository, id=str(ticket_id),
                                  url=f'https://github.com/{c.repository}/issues/{ticket_id}', revision=item['updated_at'],
                                  title=item['title'], body=item.get('body') or '', format='markdown', state=item['state'],
                                  updated_at=item['updated_at'], observed_at=datetime.now(timezone.utc), comments=tuple(comments))
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            raise http.malformed() from None
