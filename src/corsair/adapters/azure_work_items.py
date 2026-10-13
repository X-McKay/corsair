"""Azure DevOps Services work items and paginated comments through documented REST APIs."""
from datetime import datetime, timezone
from urllib.parse import quote
from pydantic import ValidationError
from corsair.ports.tickets import TicketComment, TicketError, TicketSnapshot
from corsair.tickets.http import CaptureHTTP


class AzureWorkItems:
    def __init__(self, config, client):
        self.config, self.client = config, client

    async def capture(self, ticket_id: int) -> TicketSnapshot:
        if type(ticket_id) is not int or ticket_id < 1:
            raise ValueError('positive integer ticket ID required')
        c = self.config
        http = CaptureHTTP(c.provider, self.client, c)
        root = f'https://dev.azure.com/{c.organization}/{quote(c.project, safe="")}'
        endpoint = f'{root}/_apis/wit/workitems/{ticket_id}'
        item, _ = await http.get(endpoint, params={'api-version': '7.1'})
        try:
            if not isinstance(item, dict) or item['id'] != ticket_id:
                raise ValueError()
            fields = item['fields']
            async def read_comments():
                comments, token, seen = [], None, set()
                for _ in range(c.max_pages):
                    params = {'api-version': '7.1-preview.4', '$top': 100, 'order': 'asc', 'includeDeleted': 'false'}
                    if token is not None:
                        params['continuationToken'] = token
                    batch, _ = await http.get(endpoint + '/comments', params=params)
                    for entry in batch['comments']:
                        comments.append(TicketComment(id=str(entry['id']), author=(entry.get('createdBy') or {}).get('displayName'),
                                                      body=entry['text'], updated_at=entry['modifiedDate'],
                                                      format='html' if entry.get('format') == 'html' else 'markdown'))
                    token = batch.get('continuationToken')
                    if token is None or token == '':
                        break
                    if not isinstance(token, str) or token in seen:
                        raise ValueError()
                    seen.add(token)
                else:
                    raise http.limit()
                if len({c.id for c in comments}) != len(comments):
                    raise ValueError()
                return tuple(comments)
            comments = await read_comments()
            if await read_comments() != comments:
                raise TicketError(c.provider, 'changed_during_capture', 'Capture again after comment updates settle.')
            latest, _ = await http.get(endpoint, params={'api-version': '7.1'})
            if latest['rev'] != item['rev']:
                raise TicketError(c.provider, 'changed_during_capture', 'Capture again after work-item updates settle.')
            return TicketSnapshot(provider=c.provider, source=f'{c.organization}/{c.project}', id=str(ticket_id),
                                  url=f'{root}/_workitems/edit/{ticket_id}', revision=str(item['rev']), title=fields['System.Title'],
                                  body=fields.get('System.Description') or '', format='html', state=fields['System.State'],
                                  updated_at=fields['System.ChangedDate'], observed_at=datetime.now(timezone.utc), comments=tuple(comments))
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            raise http.malformed() from None
