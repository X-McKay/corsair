"""Small fixture payloads without Temporal or other vendor objects."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FixtureRequest:
    operation_id: str
    value: str
    scenario: Literal["success", "transient", "permanent", "unknown"] = "success"
    wait_for_release: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not 1 <= len(self.operation_id) <= 128:
            raise ValueError("A bounded operation identity is required")
        if not isinstance(self.value, str) or len(self.value.encode("utf-8")) > 4096:
            raise ValueError("Fixture value must be at most 4096 UTF-8 bytes")
        if self.scenario not in {"success", "transient", "permanent", "unknown"}:
            raise ValueError("An explicit supported fixture scenario is required")
        if type(self.wait_for_release) is not bool:
            raise ValueError("wait_for_release must be boolean")


@dataclass(frozen=True)
class PreparedFixture:
    request: FixtureRequest
    attempts: int


@dataclass(frozen=True)
class FixtureResult:
    operation_id: str
    outcome: Literal["completed", "failed", "unknown"]
    value: str | None
    failure_type: str | None
    prepare_attempts: int
    operation_attempts: int
    cleanup: Literal["not_required"] = "not_required"
