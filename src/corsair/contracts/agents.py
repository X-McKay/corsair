"""Canonical agents wire contracts; no vendor SDK types."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, RootModel, model_validator

from .common import Contract, Feedback, Identifier, Usage
from .sources import Budget, Finding, PreparedCase, PythonRecipe

# Explicit JSON shapes keep native output schemas informative; JsonValue alone emits {}.
JsonPayload = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class PlanRevision(Contract):
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    objective: str = Field(min_length=1, max_length=1000)
    next_steps: list[str] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=2000)


class Submission(Contract):
    schema_version: Literal["corsair.submission/1"] = "corsair.submission/1"
    hypothesis: str = Field(min_length=1, max_length=4000)
    plan: PlanRevision
    control_payload: JsonPayload = Field(
        description="Exact JSON value assigned to the recipe's payload_parameter for benign input; "
        "not a keyword-argument mapping unless the parameter itself expects a mapping."
    )
    exploit_payload: JsonPayload = Field(
        description="Exact JSON value assigned to the payload_parameter for adversarial input; "
        "not a keyword-argument mapping unless the parameter itself expects a mapping."
    )

    @model_validator(mode="after")
    def bounded_payloads(self):
        if len(json.dumps([self.control_payload, self.exploit_payload]).encode()) > 32768:
            raise ValueError("payloads exceed the submission limit")
        return self


class ProducerProposal(Contract):
    """A source-grounded payload proposal for trusted verification."""

    schema_version: Literal["corsair.producer-decision/1"] = "corsair.producer-decision/1"
    kind: Literal["proposal"] = "proposal"
    submission: Submission


class NoGroundedCandidate(Contract):
    """An explicit producer abstention when source grounding is unavailable."""

    schema_version: Literal["corsair.producer-decision/1"] = "corsair.producer-decision/1"
    kind: Literal["no_grounded_candidate"] = "no_grounded_candidate"
    reason: str = Field(min_length=1, max_length=2000)


_ProducerDecisionVariant = Annotated[
    ProducerProposal | NoGroundedCandidate,
    Field(discriminator="kind"),
]


class ProducerDecision(RootModel[_ProducerDecisionVariant]):
    """The producer's sole native ADK output: proposal or explicit abstention."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)


class ProducerInput(Contract):
    run_id: Identifier
    prepared: PreparedCase
    budget: Budget
    round_index: int = Field(ge=1)
    previous: Submission | None = None
    feedback: Feedback | None = None
    llm_call_limit: int = Field(ge=1)
    tool_call_limit: int = Field(ge=1)


class ProducerOutput(Contract):
    decision: ProducerDecision | None = None
    # This is retained only to decode activity/result payloads recorded before
    # corsair.producer-decision/1. New inference writes ``decision`` exclusively.
    submission: Submission | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None

    @model_validator(mode="after")
    def decision_or_legacy_submission(self):
        if self.decision is not None and self.submission is not None:
            raise ValueError("producer output cannot contain both a decision and a submission")
        return self

    def submission_for_verification(self) -> Submission | None:
        """Return the proposal submission, including pre-decision persisted output."""

        if self.decision is not None:
            variant = self.decision.root
            return variant.submission if isinstance(variant, ProducerProposal) else None
        return self.submission


class AuditDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    INSUFFICIENT = "INSUFFICIENT_CONTEXT"


class AuditResult(Contract):
    decision: AuditDecision
    rule: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


class AuditInput(Contract):
    finding: Finding
    recipe: PythonRecipe
    source_excerpt: str
    submission: Submission
    max_output_tokens: int = Field(ge=256, le=16384)


class AuditOutput(Contract):
    review: AuditResult | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None
