"""Serializable dependencies admitted to Corsair v2 cognitive stages.

These models deliberately carry only IDs, immutable references, and role-scoped
path authority.  They never carry a provider client, database/store handle,
workspace object, credential, or other process-local SDK object.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..contracts import ArtifactRef, Contract, confined_path


class WorkspaceRef(Contract):
    """A Corsair-owned reference to a materialized immutable source workspace."""

    provider: Literal["corsair-source"] = "corsair-source"
    id: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentDeps(Contract):
    """Small Pydantic/Temporal-safe dependency payload for a single role run."""

    run_id: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=128)
    source_manifest: ArtifactRef
    workspace_ref: WorkspaceRef | None = None
    expected_probe_path: str | None = None
    allowed_repair_paths: tuple[str, ...] = ()
    other_refs: dict[str, ArtifactRef] = Field(default_factory=dict)

    @field_validator("run_id", "stage_id")
    @classmethod
    def bounded_identifier(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
            raise ValueError("run_id and stage_id require bounded opaque identifiers")
        return value

    @field_validator("expected_probe_path")
    @classmethod
    def confined_probe_path(cls, value: str | None) -> str | None:
        return None if value is None else confined_path(value)

    @field_validator("allowed_repair_paths")
    @classmethod
    def confined_repair_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > 16:
            raise ValueError("Repair authority exceeds the file envelope")
        return tuple(confined_path(value) for value in values)

    @model_validator(mode="after")
    def workspace_matches_immutable_source(self) -> AgentDeps:
        if self.workspace_ref is not None and self.workspace_ref.id != self.source_manifest.sha256:
            raise ValueError("workspace_ref must be pinned to source_manifest.sha256")
        if self.expected_probe_path is not None and not self.expected_probe_path:
            raise ValueError("expected_probe_path must be a canonical source path")
        return self


__all__ = ["AgentDeps", "WorkspaceRef"]
