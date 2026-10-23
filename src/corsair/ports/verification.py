"""The narrow verification contract consumed by untrusted-agent orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from corsair.domain.verification import Evaluation, Submission
from corsair.ports.artifacts import Artifacts


@runtime_checkable
class Verification(Protocol):
    run_id: str
    artifacts: Artifacts

    async def evaluate(self, submission: Submission) -> Evaluation: ...
