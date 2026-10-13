"""One operator configuration with independent model and ticket-source selection."""
from pydantic import BaseModel, ConfigDict
from corsair.inference.config import InferenceConfig
from corsair.tickets.config import TicketConfig


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    inference: InferenceConfig
    tickets: TicketConfig | None = None
