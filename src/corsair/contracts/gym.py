"""Canonical evaluation-gym records: trajectories, scorecards, gate verdicts, budgets, ledger.

These are evaluator-side records derived from a scored report, its frozen dataset and the
stored results. They never reach an agent, tool or workflow input. Usage counts that were
not reported stay ``None``; nothing here turns an unknown into zero.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, RootModel

from .agents import AuditDecision, AuditRule
from .common import Contract, DiagnosticText, Digest, Identifier
from .evaluation import Oracle
from .evidence import RoleOutcome
from .results import (
    MAX_TERMINAL_ROUNDS,
    Disposition,
    ExecutionStatus,
    FixStatus,
    RoundResult,
    Verdict,
)
from .sources import PreparedCase

# Per-call detail lists are copied from the recorded usage; the recorder caps them.
_MAX_CALL_DETAIL = 1024


class RoundSummary(Contract):
    """One recorded round: proposal identity, audit decision, role outcomes and timing."""

    session: int = Field(ge=1)
    index: int = Field(ge=1)
    # The round's stopping gate from the row's gate ledger, when it recorded one.
    stop: str | None = None
    # ``candidate_key`` of the proposal: the exploit payload's canonical digest.
    payload_identity: Digest | None = None
    control_payload: JsonValue = None
    exploit_payload: JsonValue = None
    producer_abstained: bool = False
    audit_decision: AuditDecision | None = None
    audit_rule: AuditRule | None = None
    control_outcome: RoleOutcome | None = None
    adversarial_outcome: RoleOutcome | None = None
    sandbox_wall_seconds: float | None = Field(default=None, ge=0)
    sandbox_cpu_seconds: float | None = Field(default=None, ge=0)
    sandbox_host_seconds: float | None = Field(default=None, ge=0)


class Trajectory(Contract):
    """One scored row (one case, one repeat) with its reward decomposition."""

    schema_version: Literal["corsair.gym-trajectory/1"] = "corsair.gym-trajectory/1"
    run_id: str = Field(min_length=1, max_length=128)
    case_id: Identifier
    repeat: int = Field(ge=0)
    kind: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=1, max_length=64)
    expected_verdict: Verdict | None = None
    acceptable_verdicts: list[Verdict] | None = None
    forbidden_verdicts: list[Verdict] = Field(default_factory=list)
    status: Literal["pass", "fail", "unavailable"]
    verdict: Verdict | None = None
    disposition: Disposition | None = None
    execution_status: ExecutionStatus | None = None
    passed: bool
    verified: bool
    false_label: bool
    failure_stop: str | None = None
    rounds: list[RoundSummary] = Field(default_factory=list, max_length=MAX_TERMINAL_ROUNDS)
    llm_calls: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    agent_seconds: float | None = Field(default=None, ge=0)
    sandbox_wall_seconds: float | None = Field(default=None, ge=0)
    sandbox_cpu_seconds: float | None = Field(default=None, ge=0)
    sandbox_host_seconds: float | None = Field(default=None, ge=0)
    model_calls: list[dict[str, JsonValue]] = Field(
        default_factory=list, max_length=_MAX_CALL_DETAIL
    )
    tool_calls_detail: list[dict[str, JsonValue]] = Field(
        default_factory=list, max_length=_MAX_CALL_DETAIL
    )
    usage_known: bool
    effective_tokens: float | None = Field(default=None, ge=0)
    seconds: float | None = Field(default=None, ge=0)
    reward_verdict: float
    phi_tokens: float = 0.0
    phi_time: float = 0.0
    shaping: float = 0.0
    reward: float
    identity: dict[str, str] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    git_commit: str | None = None


class GroupSummary(Contract):
    """Per-kind or per-language aggregate; case-level values use the majority of repeats."""

    cases: int = Field(ge=0)
    attempts: int = Field(ge=0)
    raw_accuracy: float | None = None
    verified_accuracy: float | None = None
    mean_reward: float | None = None
    mean_effective_tokens: float | None = None
    p95_effective_tokens: float | None = None
    p50_seconds: float | None = None
    p95_seconds: float | None = None
    failure_stops: dict[str, int] = Field(default_factory=dict)
    usage_unknown: int = Field(default=0, ge=0)


class RunContext(Contract):
    """Where and how a gym run executed; transport is recorded beside, not in, identity."""

    run_id: Identifier
    git_branch: str | None = None
    git_commit: str | None = None
    temporal_namespace: str | None = None
    task_queue: str | None = None
    concurrency: int | None = Field(default=None, ge=1)
    image_ids: dict[str, str] = Field(default_factory=dict)


class Scorecard(Contract):
    schema_version: Literal["corsair.gym-scorecard/1"] = "corsair.gym-scorecard/1"
    run: RunContext
    dataset_digest: Digest
    identity_digests: list[str] = Field(default_factory=list)
    budgets_digest: Digest | None = None
    models: dict[str, list[str]] = Field(default_factory=dict)
    repeats: int = Field(ge=0)
    sliced: bool
    kinds: dict[str, GroupSummary]
    languages: dict[str, GroupSummary]
    macro_verified_accuracy: float
    worst_language_verified_accuracy: float
    macro_reward: float
    objective_j: float
    macro_effective_tokens: float | None = None
    macro_p50_seconds: float | None = None


class GateDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INCOMPARABLE = "INCOMPARABLE"


class GateReason(StrEnum):
    """Code-owned reasons; human views map each to fixed text."""

    DATASET_MISMATCH = "dataset_mismatch"
    BUDGETS_MISMATCH = "budgets_mismatch"
    SLICED = "sliced"
    REPEATS_BELOW_MINIMUM = "repeats_below_minimum"
    TOKENS_UNKNOWN = "tokens_unknown"
    LANGUAGE_REGRESSED = "language_regressed"
    OBJECTIVE_BELOW_THRESHOLD = "objective_below_threshold"
    TOKENS_ABOVE_CEILING = "tokens_above_ceiling"


_EXIT_CODES = {GateDecision.ACCEPTED: 0, GateDecision.REJECTED: 1, GateDecision.INCOMPARABLE: 2}


class GateVerdict(Contract):
    decision: GateDecision
    reasons: list[GateReason] = Field(default_factory=list)
    baseline_run_id: Identifier
    candidate_run_id: Identifier
    delta_j: float | None = None
    token_ratio: float | None = None
    language_deltas: dict[str, float | None] = Field(default_factory=dict)
    regressed_languages: list[str] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """0 accepted, 1 rejected, 2 incomparable."""
        return _EXIT_CODES[self.decision]


class KindBudget(Contract):
    effective_tokens: float = Field(gt=0)
    seconds: float = Field(gt=0)


class Budgets(RootModel[dict[str, KindBudget]]):
    """Per-recipe-kind efficiency budgets: ``{kind: {effective_tokens, seconds}}``."""

    model_config = ConfigDict(frozen=True)


class LedgerRow(Contract):
    """One append-only experiment-ledger record: a reference run or a gated experiment."""

    schema_version: Literal["corsair.gym-ledger/1"] = "corsair.gym-ledger/1"
    id: Identifier
    recorded_on: date
    wave: int = Field(ge=0)
    entry: Literal["baseline", "experiment"]
    branch: str = Field(min_length=1, max_length=200)
    commit: str = Field(min_length=7, max_length=64)
    tier: str = Field(min_length=1, max_length=64)
    track: str | None = Field(default=None, max_length=64)
    idea: str | None = Field(default=None, max_length=300)
    dataset_digest: Digest
    identity_digests: list[str] = Field(default_factory=list)
    budgets_digest: Digest | None = None
    repeats: int = Field(ge=0)
    scorecard: str | None = Field(default=None, max_length=300)
    objective_j: float
    macro_verified_accuracy: float
    worst_language_verified_accuracy: float
    macro_effective_tokens: float | None = None
    macro_p50_seconds: float | None = None
    gate: GateVerdict | None = None
    lesson: str = Field(default="", max_length=500)


class KernelCase(Contract):
    """A captured result's rounds and observations for a model-free kernel replay.

    ``recorded_verdict`` is what the workflow decided; replaying ``rounds`` through
    ``corsair.policies.verdicts`` must reproduce it. ``oracle`` is the frozen case
    expectation, kept for the reader; it is never an input to the replayed decision.
    """

    schema_version: Literal["corsair.gym-kernel-case/1"] = "corsair.gym-kernel-case/1"
    case_id: Identifier
    run_id: Identifier
    kind: str = Field(min_length=1, max_length=128)
    oracle: Oracle
    recorded_verdict: Verdict | None
    execution_status: ExecutionStatus
    reason: DiagnosticText
    fix_status: FixStatus = FixStatus.NOT_REQUESTED
    negative_threshold: int = Field(ge=2, le=8)
    prepared: PreparedCase | None = None
    rounds: list[RoundResult] = Field(default_factory=list, max_length=MAX_TERMINAL_ROUNDS)
