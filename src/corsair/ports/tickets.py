"""Immutable ticket observations; no vendor SDKs or authority inferred from ticket text."""
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TicketComment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str
    author: str | None
    body: str
    updated_at: datetime
    format: Literal['markdown', 'html'] = 'markdown'


class TicketSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    provider: Literal['github', 'azure_devops']
    source: str
    id: str
    url: str
    revision: str
    title: str = Field(min_length=1)
    body: str
    format: Literal['markdown', 'html']
    state: str
    updated_at: datetime
    observed_at: datetime
    comments: tuple[TicketComment, ...]

    @property
    def digest(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()

    def issue_text(self, *, max_chars: int = 8192) -> str:
        """Explicit bridge to existing identification inputs; refuse over-budget tickets, never truncate silently."""
        text = '\n\n'.join([self.title, self.body, *(c.body for c in self.comments)])
        if len(text) > max_chars:
            raise ValueError('ticket exceeds identification input budget; operator must supply a scoped issue excerpt')
        return text


class TicketSource(Protocol):
    async def capture(self, ticket_id: int) -> TicketSnapshot: ...


class TicketError(RuntimeError):
    def __init__(self, provider: str, code: str, action: str, *, status: int | None = None):
        self.provider, self.code, self.action, self.status = provider, code, action, status
        super().__init__(f'{provider}: {code}' + (f' (HTTP {status})' if status else '') + f'; {action}')
