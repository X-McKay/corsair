"""Canonical sources wire contracts; no vendor SDK types."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import ArtifactRef, Contract, Digest, Identifier, safe_path
from .intake import ScannerClaim
from .recipes import Recipe


class Source(Contract):
    """An admitted local source tree, snapshotted before any agent invocation."""

    path: str = Field(min_length=1)
    expected_digest: Digest | None = None


class Scope(StrEnum):
    COMPONENT = "component"
    APPLICATION = "application"


class Finding(Contract):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=12000)
    file: str
    line: int | None = Field(default=None, ge=1)
    # An unspecified scope is treated as application: the conservative direction, so
    # a demonstration caps at COMPONENT_EXPLOIT_DEMONSTRATED unless the finding
    # explicitly claims component scope. Scanner findings, which omit a provable
    # scope, land here by default (Al 2026-10-26).
    claim_scope: Scope = Scope.APPLICATION
    # The upstream scanner's untrusted self-assessment, carried for reporting only.
    # The verdict kernel never reads this; see corsair.contracts.intake.
    scanner: ScannerClaim | None = None

    _safe_file = field_validator("file")(safe_path)


class Case(Contract):
    schema_version: Literal["corsair.case/1"] = "corsair.case/1"
    case_id: Identifier
    finding: Finding
    source: Source
    recipe: Recipe
    fixed_source: Source | None = None

    @model_validator(mode="after")
    def bind_recipe(self):
        if self.finding.file != self.recipe.module_file:
            raise ValueError("the recipe must bind to the original finding's file")
        return self


DEFAULT_MAX_OUTPUT_TOKENS = 12288


class Budget(Contract):
    """Bounded per-request limits for one investigation.

    Defaults are sized for a thinking model on a live provider: a producer episode
    must cover reading several files AND submitting a pair (``episode_llm_calls``),
    and the case budget must leave room for a second independent session
    (``max_llm_calls``).

    ``max_output_tokens`` caps every individual model request, for the producer and
    for the auditor alike (the workflow passes the same value into ``AuditInput``).
    On a thinking model the provider counts reasoning tokens against that same cap,
    so it must sit well above the model's reasoning spend plus the structured answer.
    A final response that stops at the cap is reported as the operational
    ``provider_max_tokens`` gate, never parsed into a decision or review.
    """

    max_rounds: int = Field(default=3, ge=1, le=16)
    max_llm_calls: int = Field(default=48, ge=2, le=128)
    episode_llm_calls: int = Field(default=12, ge=1, le=32)
    max_tool_calls: int = Field(default=48, ge=1, le=256)
    max_output_tokens: int = Field(default=DEFAULT_MAX_OUTPUT_TOKENS, ge=256, le=16384)
    max_elapsed_seconds: int = Field(default=900, ge=30, le=3600)
    probe_timeout_seconds: int = Field(default=30, ge=1, le=300)
    tool_output_bytes: int = Field(default=32768, ge=1024, le=131072)


class InvestigationRequest(Contract):
    intake_result: ArtifactRef | None = None
    case: Case
    budget: Budget = Field(default_factory=Budget)


class RunManifest(Contract):
    schema_version: Literal["corsair.manifest/1"] = "corsair.manifest/1"
    package_version: str
    request_digest: Digest
    config_digest: Digest
    producer_prompt_digest: Digest
    auditor_prompt_digest: Digest
    image_id: str
    image_reference: str | None = None
    models: dict[str, str]
    capabilities: dict[str, dict] = Field(default_factory=dict)
    # The admitted evidence policy, fixed when the case is prepared and replayed
    # from history: independent clean negatives required for
    # EXPLOIT_NOT_DEMONSTRATED, and the cap on independent producer sessions.
    negative_threshold: int = Field(default=2, ge=2, le=8)
    max_sessions: int = Field(default=2, ge=1, le=8)


class LineProvenance(StrEnum):
    """Where a prepared finding's target line came from.

    ``declared``: the request (or scanner) supplied it, or none was supplied.
    ``recipe_function``: the finding declared no line and trusted prepare code bound
    it, with ``ast`` over the admitted module, to the first body statement of the
    operator-owned recipe function. Never derived from model or narrative text.
    """

    DECLARED = "declared"
    RECIPE_FUNCTION = "recipe_function"


class PreparedCase(Contract):
    case_id: Identifier
    finding: Finding
    recipe: Recipe
    source: ArtifactRef
    fixed_source: ArtifactRef | None = None
    source_excerpt: str
    manifest: RunManifest
    # Defaulted so prepared cases recorded before line derivation still decode.
    line_provenance: LineProvenance = LineProvenance.DECLARED
    # The line the coverage gate binds to, chosen in code at prepare from finding.line
    # (declared, or derived when line_provenance is recipe_function) over the admitted
    # module (corsair.policies.line_binding). finding.line keeps the declared or
    # derived line. None in records made before line binding: the kernel then binds to
    # finding.line itself.
    target_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def target_line_needs_a_declared_line(self):
        if self.target_line is not None and self.finding.line is None:
            raise ValueError("a bound target line needs a declared finding line")
        return self

    @property
    def bound_line(self) -> int | None:
        """The exact line the kernel requires in both runs: bound, else declared."""
        return self.finding.line if self.target_line is None else self.target_line
