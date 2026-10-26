"""Canonical results wire contracts; no vendor SDK types."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .agents import AuditOutput, ProducerOutput
from .common import ArtifactRef, Contract, DiagnosticText, Identifier, format_diagnostic
from .evidence import Observation
from .sources import RunManifest, Scope

TERMINAL_RESULT_MAX_BYTES = 1_000_000
# Budget.max_rounds (16) per session, times the session cap (2).
MAX_TERMINAL_ROUNDS = 32
# The workflow keeps only its most recent phase transitions, live and recorded.
MAX_TERMINAL_TIMELINE = 32


class RoundResult(Contract):
    index: int
    session: int = Field(default=1, ge=1, le=8)
    producer: ProducerOutput
    observation: Observation | None = None
    audit: AuditOutput | None = None


class PhaseTransition(Contract):
    """One workflow phase change at deterministic workflow time; no model or payload
    content. ``at`` is unknown only when finalization ran outside a workflow."""

    phase: Identifier
    session: int = Field(ge=0)
    round: int = Field(ge=0)
    at: datetime | None = None


class Disposition(StrEnum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    CONDITIONAL = "CONDITIONAL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FixStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    DEMONSTRATION_BLOCKED = "DEMONSTRATION_BLOCKED"
    NOT_BLOCKED = "NOT_BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class Verdict(StrEnum):
    """The canonical per-case label decided by code, layered over the internal
    Disposition/ExecutionStatus/FixStatus. A false EXPLOIT_NOT_DEMONSTRATED is the
    costliest mistake, so it is the hardest verdict to reach.

    EXPLOIT_DEMONSTRATED and COMPONENT_EXPLOIT_DEMONSTRATED differ only in scope:
    both require a genuine control-vs-exploit differential (coverage in both runs,
    accepted audit). EXPLOIT_DEMONSTRATED is for a finding whose claimed scope the
    demonstration covers; COMPONENT_EXPLOIT_DEMONSTRATED is for an application-scope
    claim proven only at the component seam, where reachability to the claimed
    application entry point was not established. Neither is ever a soft landing for
    a weak demonstration -- merely reaching a sink stays non-decisive."""

    EXPLOIT_DEMONSTRATED = "EXPLOIT_DEMONSTRATED"
    COMPONENT_EXPLOIT_DEMONSTRATED = "COMPONENT_EXPLOIT_DEMONSTRATED"
    EXPLOIT_NOT_DEMONSTRATED = "EXPLOIT_NOT_DEMONSTRATED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNABLE_TO_RUN = "UNABLE_TO_RUN"
    ERROR = "ERROR"


class InvestigationResult(Contract):
    schema_version: Literal["corsair.result/1"] = "corsair.result/1"
    run_id: Identifier
    case_id: Identifier
    disposition: Disposition
    verdict: Verdict | None = None
    execution_status: ExecutionStatus
    reason: DiagnosticText
    scope: Scope = Scope.COMPONENT
    manifest: RunManifest | None = None
    rounds: list[RoundResult] = Field(default_factory=list, max_length=MAX_TERMINAL_ROUNDS)
    usage_complete: bool = True
    fix_status: FixStatus = FixStatus.NOT_REQUESTED
    fix_observation: Observation | None = None
    result_artifact: ArtifactRef | None = None
    # Presentation metadata recorded at finalization; never an input to a verdict.
    # Results recorded before the field existed decode to an empty timeline.
    timeline: list[PhaseTransition] = Field(default_factory=list, max_length=MAX_TERMINAL_TIMELINE)

    @model_validator(mode="after")
    def bounded_terminal_wire(self) -> Self:
        if len(self.model_dump_json(warnings="error").encode()) > TERMINAL_RESULT_MAX_BYTES:
            raise ValueError("final result exceeds the 1 MB terminal wire budget")
        return self


def _format_observation_diagnostics(value: dict[str, Any]) -> None:
    for role in ("control", "adversarial"):
        detail = value.get(role)
        if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
            detail["reason"] = format_diagnostic(detail["reason"])
    feedback = value.get("feedback")
    if isinstance(feedback, dict) and isinstance(feedback.get("reason"), str):
        feedback["reason"] = format_diagnostic(feedback["reason"])


def _format_round_diagnostics(value: dict[str, Any]) -> None:
    producer = value.get("producer")
    if isinstance(producer, dict):
        feedback = producer.get("feedback")
        if isinstance(feedback, dict) and isinstance(feedback.get("reason"), str):
            feedback["reason"] = format_diagnostic(feedback["reason"])
    observation = value.get("observation")
    if isinstance(observation, dict):
        _format_observation_diagnostics(observation)
    audit = value.get("audit")
    if isinstance(audit, dict):
        review = audit.get("review")
        if isinstance(review, dict) and isinstance(review.get("reason"), str):
            review["reason"] = format_diagnostic(review["reason"])
        feedback = audit.get("feedback")
        if isinstance(feedback, dict) and isinstance(feedback.get("reason"), str):
            feedback["reason"] = format_diagnostic(feedback["reason"])


def format_terminal_result(result: InvestigationResult) -> InvestigationResult:
    """Bound optional diagnostics then validate the exact final JSON wire result.

    Structured evidence, immutable artifact references, and submitted operation
    claims are deliberately not shortened. An oversized non-diagnostic value
    therefore remains an explicit validation failure rather than hidden loss.
    """
    value = json.loads(result.model_dump_json(warnings="error"))
    if not isinstance(value, dict):
        raise ValueError("final result did not serialize to a JSON object")
    if isinstance(value.get("reason"), str):
        value["reason"] = format_diagnostic(value["reason"])
    for round_result in value.get("rounds", []):
        if isinstance(round_result, dict):
            _format_round_diagnostics(round_result)
    fix_observation = value.get("fix_observation")
    if isinstance(fix_observation, dict):
        _format_observation_diagnostics(fix_observation)
    return InvestigationResult.model_validate_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
