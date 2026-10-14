"""Small durable state for the shared direct/Temporal coordinator."""
from __future__ import annotations

from typing import Any

from corsair.v2.contracts import (
    AgentResult,
    ArtifactRef,
    Budget,
    Contract,
    RevisionExecution,
    RunSpec,
    Verdict,
)


class Episode(Contract):
    run_id: str
    spec: RunSpec
    spec_sha256: str
    config_sha256: str
    build_sha256: str
    source_ref: ArtifactRef | None = None
    candidate_ref: ArtifactRef | None = None
    plan_ref: ArtifactRef | None = None
    pair_ref: ArtifactRef | None = None
    validity_ref: ArtifactRef | None = None
    stages: tuple[AgentResult, ...] = ()
    revisions: tuple[RevisionExecution, ...] = ()
    plan_revision: int = 0
    qualified: bool = False
    budget: Budget
    verdict: Verdict | None = None
    cached_result_ref: ArtifactRef | None = None


class StageEnvelope(Contract):
    role: str
    public_input: dict[str, Any]
    deps: dict[str, Any]
    budget: Budget
    stage_id: str


class EpisodeInput(Contract):
    spec: RunSpec
    config_sha256: str
    build_sha256: str
