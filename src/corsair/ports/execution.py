"""Recipe-free process execution boundary, with no SDK types."""

from typing import Protocol

from corsair.contracts.execution import PreparedExecution, ProcessObservation, TestPlan


class ExecutionPort(Protocol):
    def execute(
        self,
        prepared: PreparedExecution,
        plan: TestPlan,
        operation_id: str,
        *,
        fixed: bool = False,
        timeout_seconds: int | None = None,
    ) -> ProcessObservation: ...
