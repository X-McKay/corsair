"""Bounded domain operations supplied by an inference integration."""

from typing import Protocol

from corsair.contracts import AuditInput, AuditOutput, ProducerInput, ProducerOutput


class InferencePort(Protocol):
    async def produce(self, request: ProducerInput) -> ProducerOutput: ...

    async def audit(self, request: AuditInput) -> AuditOutput: ...
