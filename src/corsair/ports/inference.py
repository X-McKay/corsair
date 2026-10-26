"""Bounded domain operations supplied by an inference integration."""

from typing import Protocol

from corsair.contracts import AuditInput, AuditOutput, ProducerInput, ProducerOutput


class InferencePort(Protocol):
    """``window_seconds`` is the time left to the calling activity, when it has a bound.

    An implementation ends its episode inside that window so the activity returns a
    typed ``episode_timeout`` instead of timing out (see ``policies/time_bounds``).
    """

    async def produce(
        self, request: ProducerInput, *, window_seconds: float | None = None
    ) -> ProducerOutput: ...

    async def audit(
        self, request: AuditInput, *, window_seconds: float | None = None
    ) -> AuditOutput: ...
