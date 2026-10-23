"""Inference model-lifetime boundary."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic_ai.models import Model

from corsair.runtime.inference import AGENTS, ProviderConfig


class Inference(Protocol):
    """Build named native SDK models and own their client lifetime."""

    def models(
        self, config: ProviderConfig, agents: Iterable[str] = AGENTS
    ) -> AbstractAsyncContextManager[dict[str, Model]]: ...
