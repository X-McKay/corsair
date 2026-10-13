"""Bounded read-only REST transport shared by the two ticket adapters."""
import json
from httpx2 import AsyncClient, HTTPError
from corsair.ports.tickets import TicketError


class CaptureHTTP:
    def __init__(self, provider, client: AsyncClient, limits):
        self.provider, self.client, self.limits, self.total = provider, client, limits, 0

    async def get(self, url, *, params=None):
        try:
            async with self.client.stream('GET', url, params=params, follow_redirects=False,
                                          timeout=self.limits.timeout_seconds) as response:
                status = response.status_code
                if status != 200:
                    code, action = {
                        401: ('authentication', 'Check the configured token or identity.'),
                        403: ('access_or_rate_limit', 'Check ticket read permission and service rate limits.'),
                        404: ('not_found_or_hidden', 'Check the ticket, repository/project and identity access.'),
                        429: ('rate_limit', 'Inspect the service rate limit and retry later explicitly.'),
                    }.get(status, ('http_error', 'Check service availability and the configured ticket source.'))
                    raise TicketError(self.provider, code, action, status=status)
                chunks = []
                async for chunk in response.aiter_bytes():
                    self.total += len(chunk)
                    if self.total > self.limits.max_bytes:
                        raise TicketError(self.provider, 'size_limit', 'Increase the operator capture budget or narrow the ticket.')
                    chunks.append(chunk)
                try:
                    data = json.loads(b''.join(chunks))
                except (ValueError, UnicodeError, RecursionError):
                    raise TicketError(self.provider, 'invalid_response', 'Inspect the service response format.') from None
                return data, response.headers
        except HTTPError:
            # HTTP exceptions may contain request URLs or headers; do not copy credential-bearing detail.
            raise TicketError(self.provider, 'transport', 'Check DNS, TLS, proxy and connectivity to the configured service.') from None

    def malformed(self):
        return TicketError(self.provider, 'invalid_response', 'Check the ticket schema and API version; no partial snapshot was admitted.')

    def limit(self):
        return TicketError(self.provider, 'page_limit', 'Increase max_pages or narrow the discussion; no partial snapshot was admitted.')
