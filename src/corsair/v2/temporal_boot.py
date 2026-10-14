"""Immutable worker boot bindings, passed through the Temporal workflow sandbox.

Only worker construction mutates this registry. A workflow reads its exact
submitted configuration digest; it cannot discover providers or change policy.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any


@dataclass(frozen=True)
class Binding:
    agents: Mapping[str, Any]
    build_sha256: str
    stage_timeout: timedelta
    effect_timeout: timedelta
    readonly_timeout: timedelta
    episode_timeout: timedelta


BINDINGS: dict[str, Binding] = {}
