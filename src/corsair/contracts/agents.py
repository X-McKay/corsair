"""Canonical agents wire contracts; no vendor SDK types."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, JsonValue, model_validator
from pydantic.json_schema import JsonSchemaValue, SkipJsonSchema
from pydantic_core import CoreSchema

from .common import Contract, Feedback, Identifier, Usage
from .sources import DEFAULT_MAX_OUTPUT_TOKENS, Budget, Finding, PreparedCase, PythonRecipe

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


class _ObjectParameter:
    """Give an optional model field a top-level ``"type": "object"`` in its JSON schema.

    Pydantic renders such a field as a bare ``$ref``.  ADK turns the output schema's
    fields into ``set_model_response`` parameters, and OpenAI-compatible tool-call
    parsers that decode each argument by its parameter's top-level ``type`` (vLLM's
    XML-style parsers) pass an untyped one through as a string, so the object arrives
    as JSON text and fails validation.  ``anyOf`` keeps the reference resolvable by
    the genai schema converter.  Only the JSON schema changes; validation does not.
    """

    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "object", "anyOf": [handler(core_schema)]}


class ProducerDecision(Contract):
    """The producer's sole native ADK output: a proposal or an explicit abstention.

    One flat object, so a schema-completion tool declares typed top-level parameters;
    ``kind`` selects which one of ``submission`` and ``reason`` must be present.
    """

    schema_version: Literal["corsair.producer-decision/1"] = "corsair.producer-decision/1"
    kind: Literal["proposal", "no_grounded_candidate"] = Field(
        description="proposal: a source-grounded payload pair in submission; "
        "no_grounded_candidate: an explicit abstention explained in reason."
    )
    submission: Annotated[Submission, _ObjectParameter()] | SkipJsonSchema[None] = Field(
        default=None,
        description="Required when kind is proposal; omit it when kind is no_grounded_candidate.",
    )
    reason: Annotated[str, Field(min_length=1, max_length=2000)] | SkipJsonSchema[None] = Field(
        default=None,
        description="Required when kind is no_grounded_candidate; omit it for a proposal.",
    )

    @model_validator(mode="after")
    def kind_carries_exactly_its_field(self):
        if self.kind == "proposal":
            if self.submission is None:
                raise ValueError("a proposal requires submission")
            if self.reason is not None:
                raise ValueError("a proposal must omit reason")
        else:
            if self.reason is None:
                raise ValueError("no_grounded_candidate requires reason")
            if self.submission is not None:
                raise ValueError("no_grounded_candidate must omit submission")
        return self

    def abstention_reason(self) -> str | None:
        """Return the abstention reason when the producer declined to propose."""

        return self.reason if self.kind == "no_grounded_candidate" else None


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
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None

    def submission_for_verification(self) -> Submission | None:
        """Return the proposal submission when the producer made one."""

        if self.decision is not None and self.decision.kind == "proposal":
            return self.decision.submission
        return None

    def abstention_reason(self) -> str | None:
        """Return the producer's abstention reason when it declined to propose."""

        return None if self.decision is None else self.decision.abstention_reason()


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
    # The per-request output cap, reasoning tokens included.  The workflow copies the
    # request's Budget.max_output_tokens; a standalone review uses the Budget default.
    max_output_tokens: int = Field(default=DEFAULT_MAX_OUTPUT_TOKENS, ge=256, le=16384)
    llm_call_limit: int = Field(default=2, ge=0, le=2)
    tool_call_limit: int = Field(default=4, ge=0, le=4)


class AuditOutput(Contract):
    review: AuditResult | None = None
    usage: Usage = Field(default_factory=Usage)
    feedback: Feedback | None = None
