"""Canonical agents wire contracts; no vendor SDK types."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

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
    submission: Submission | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None

    def submission_for_verification(self) -> Submission | None:
        """Return the canonical proposal projection used by evidence and scoring."""
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
