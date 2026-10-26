"""Native execution returns an immutable raw receipt, never a trusted verdict."""

from collections.abc import Callable
from typing import Literal, Protocol

from corsair.contracts import ArtifactRef, Budget, PreparedCase, Submission

SandboxRole = Literal["control", "adversarial"]


class SandboxUnavailable(RuntimeError):
    """Configured execution dependency is unavailable."""


class SandboxPort(Protocol):
    @property
    def image_id(self) -> str: ...

    def image_id_for(self, recipe_kind: str) -> str: ...

    def has_unknown_operation(self, operation_id: str) -> bool: ...

    def execute_role(
        self,
        prepared: PreparedCase,
        submission: Submission,
        role: SandboxRole,
        budget: Budget,
        heartbeat: Callable[[], None],
        *,
        operation_id: str,
    ) -> ArtifactRef: ...
