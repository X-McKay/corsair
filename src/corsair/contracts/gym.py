"""Canonical evaluation-gym records: trajectories, scorecards, gates, budgets, verify, ledger.

These are evaluator-side records derived from a scored report, its frozen dataset and the
stored results. They never reach an agent, tool or workflow input. Usage counts that were
not reported stay ``None``; nothing here turns an unknown into zero.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, RootModel, model_validator

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


class DominantCall(Contract):
    """The episode's largest model call by output tokens; the first one wins a tie.

    ``position`` is the 1-based place in the trajectory's ``model_calls`` list (producer
    calls of every round, then auditor calls); ``index`` is the call's dispatch ordinal
    within its own episode, so it repeats across episodes.
    """

    position: int = Field(ge=1)
    index: int = Field(ge=1)
    output_tokens: int = Field(ge=0)
    seconds: float = Field(ge=0)


class RunIdentity(Contract):
    """The full configuration identity one stored result's ``RunManifest`` records.

    Read from the result, never from the checkout: the package version, the settings
    identity (``config``), each role's instruction, agent spec, output schema and runtime
    skills digests from the manifest's ``capabilities``, the risk-assessment and
    budget-policy digests, the trusted image and each role's model. A value an older
    manifest did not record stays ``None``. The per-case ``request_digest`` stays in
    ``Trajectory.identity``; ``image`` varies per language and ``budget_policy`` per
    request budget, so a scorecard keeps every distinct value of each component.
    """

    package_version: str | None = Field(default=None, max_length=64)
    config: Digest | None = None
    producer_prompt: Digest | None = None
    auditor_prompt: Digest | None = None
    producer_spec: str | None = Field(default=None, max_length=128)
    auditor_spec: str | None = Field(default=None, max_length=128)
    producer_output_schema: str | None = Field(default=None, max_length=128)
    auditor_output_schema: str | None = Field(default=None, max_length=128)
    producer_skills: str | None = Field(default=None, max_length=128)
    auditor_skills: str | None = Field(default=None, max_length=128)
    risk_assessment: str | None = Field(default=None, max_length=128)
    budget_policy: str | None = Field(default=None, max_length=128)
    image: str | None = Field(default=None, max_length=256)
    producer_model: str | None = Field(default=None, max_length=256)
    auditor_model: str | None = Field(default=None, max_length=256)


class OperationalReason(StrEnum):
    """Why a failed episode stopped for an operational, not a behavioural, reason.

    Derived only from code-owned gate-ledger gates and workflow-owned reason text (see
    ``evaluation.gym.scoring.operational_stop``); never from model-authored text.
    """

    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    ACTIVITY_TIMEOUT = "activity_timeout"
    EPISODE_TIMEOUT = "episode_timeout"
    PROVIDER_TEMPORARY = "provider_temporary"
    OPERATION_RECONCILIATION = "operation_reconciliation"
    EXECUTION_CANCELLED = "execution_cancelled"
    EVIDENCE_NOT_RUN = "evidence_not_run"
    RESULT_UNAVAILABLE = "result_unavailable"


class OperationalEpisode(Contract):
    """One operational stop on a scorecard: which case and repeat, and why."""

    case_id: Identifier
    repeat: int = Field(ge=0)
    language: str = Field(min_length=1, max_length=64)
    reason: OperationalReason


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
    # Reasoning markers; observations only, never a reward, gate or verdict input.
    # ``thought_share`` is thought / output tokens, unknown when either is unknown.
    thought_share: float | None = Field(default=None, ge=0)
    # The per-call output cap: the frozen request's ``Budget.max_output_tokens``.
    output_cap: int | None = Field(default=None, ge=1)
    # Calls whose reported output reached ``output_cap``; unknown without a cap or calls.
    capped_calls: int | None = Field(default=None, ge=0)
    # Whether a capped call's reported thought tokens filled its whole output.
    reasoning_cap_exhausted: bool | None = None
    dominant_call: DominantCall | None = None
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
    # The stored result's full manifest identity; ``None`` without a stored manifest.
    run_identity: RunIdentity | None = None
    # Visibility only: an operational stop keeps its reward and counts against accuracy.
    operational: bool = False
    operational_reason: OperationalReason | None = None

    @model_validator(mode="after")
    def coherent_operational(self):
        if self.operational != (self.operational_reason is not None):
            raise ValueError("an operational episode needs its reason, and only it has one")
        return self


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
    # Reasoning markers (see ``Trajectory``): case means of repeat means, and attempt
    # counts that stay unknown when no attempt in the group knows its output cap.
    mean_thought_share: float | None = None
    capped_call_episodes: int | None = Field(default=None, ge=0)
    reasoning_cap_exhausted: int | None = Field(default=None, ge=0)
    # Operational stops (see ``Trajectory.operational``); unknown on older scorecards.
    operational_episodes: int | None = Field(default=None, ge=0)
    # Majority verified accuracy had every operational episode verified: the gate's
    # confounding check, never an accuracy, reward or objective input.
    verified_accuracy_without_operational_failures: float | None = None


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
    # Reasoning markers: the mean over languages and the attempt totals; none feeds J.
    macro_thought_share: float | None = None
    capped_call_episodes: int | None = Field(default=None, ge=0)
    reasoning_cap_exhausted: int | None = Field(default=None, ge=0)
    # Every distinct value of each ``RunIdentity`` component across the trajectories;
    # a component no stored result recorded is absent (unknown).
    run_identity: dict[str, list[str]] = Field(default_factory=dict)
    # Operational stops: the total, unknown on older scorecards, and each episode.
    operational_episodes: int | None = Field(default=None, ge=0)
    operational_stops: list[OperationalEpisode] = Field(default_factory=list)


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
    # Names a rejection, never causes one: a regressed language would not regress had
    # its operational episodes verified, so the orchestrator orders a clean re-run.
    OPERATIONALLY_CONFOUNDED = "operationally_confounded"


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
    # Regressed languages explained entirely by operational episodes.
    operationally_confounded_languages: list[str] = Field(default_factory=list)
    # Per ``RunIdentity`` component: whether its values differ; ``None`` when unknown on
    # either side. Reported only; identity never makes a gate INCOMPARABLE.
    identity_changes: dict[str, bool | None] = Field(default_factory=dict)
    # A smoke gate reports ``objective_below_threshold`` without rejecting on it, so its
    # ACCEPTED is a smoke result, never an acceptance.
    smoke: bool = False

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


class TierGate(Contract):
    """One tier's gate: a candidate scorecard against the reference it was gated against.

    ``reference`` is the baseline ledger row id or reference scorecard path, as given;
    the per-language deltas are ``gate.language_deltas``.
    """

    reference: str = Field(min_length=1, max_length=300)
    scorecard: str = Field(min_length=1, max_length=300)
    run_dir: str | None = Field(default=None, max_length=300)
    gate: GateVerdict


# Why ``corsair gym verify`` did not run a tier: on request, or after an earlier rejection.
SkipReason = Literal["skipped_by_request", "rejected_at_tier0"]


class VerifyRecord(Contract):
    """``verdict.json`` of a verified candidate: its git identity and each tier's gate.

    ``corsair gym verify`` writes one; ``corsair gym ledger append --verdict`` copies the
    identity and tier gates into one experiment row. ``decision`` is the chain decision
    over the gates that ran; ``complete`` is false when a tier was not run (``skipped``),
    so its decision is not an acceptance. Fields ``verify`` records but a hand-written
    record may omit (``reference``, ``invocation``, ``recorded_at``, ``complete``) stay
    unknown rather than defaulted.
    """

    schema_version: Literal["corsair.gym-verify/1"] = "corsair.gym-verify/1"
    branch: str | None = Field(default=None, min_length=1, max_length=200)
    commit: str | None = Field(default=None, min_length=7, max_length=64)
    tier0: TierGate | None = None
    tier1: TierGate | None = None
    decision: GateDecision | None = None
    complete: bool | None = None
    skipped: dict[str, SkipReason] = Field(default_factory=dict)
    # The reference directory holding ``<tier>.json``; each tier gate names its file.
    reference: str | None = Field(default=None, min_length=1, max_length=300)
    invocation: list[str] | None = Field(default=None, max_length=256)
    recorded_at: datetime | None = None


LedgerDecision = Literal["accepted", "rejected", "inconclusive", "merged"]


class LedgerRow(Contract):
    """One append-only experiment-ledger record: a reference run or an experiment.

    A baseline carries its scorecard's headline metrics. An experiment may carry a
    scorecard (gated against ``--baseline`` into ``gate``), the tier0 and tier1 gates of
    its candidate, and the orchestrator's decision; an offline change may carry none.
    ``branch`` and ``commit`` always name the candidate.
    """

    schema_version: Literal["corsair.gym-ledger/1"] = "corsair.gym-ledger/1"
    id: Identifier
    recorded_on: date
    wave: int = Field(ge=0)
    entry: Literal["baseline", "experiment"]
    branch: str = Field(min_length=1, max_length=200)
    commit: str = Field(min_length=7, max_length=64)
    tier: str | None = Field(default=None, min_length=1, max_length=64)
    track: str | None = Field(default=None, max_length=64)
    idea: str | None = Field(default=None, max_length=300)
    dataset_digest: Digest | None = None
    identity_digests: list[str] = Field(default_factory=list)
    budgets_digest: Digest | None = None
    repeats: int | None = Field(default=None, ge=0)
    scorecard: str | None = Field(default=None, max_length=300)
    objective_j: float | None = None
    macro_verified_accuracy: float | None = None
    worst_language_verified_accuracy: float | None = None
    macro_effective_tokens: float | None = None
    macro_p50_seconds: float | None = None
    gate: GateVerdict | None = None
    tier0: TierGate | None = None
    tier1: TierGate | None = None
    decision: LedgerDecision | None = None
    merge_commit: str | None = Field(default=None, min_length=7, max_length=64)
    lesson: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def coherent_entry(self):
        if self.entry == "baseline" and (
            self.tier is None or self.dataset_digest is None or self.objective_j is None
        ):
            raise ValueError("a baseline row needs a scorecard and its tier")
        if (self.decision == "merged") != (self.merge_commit is not None):
            raise ValueError("a merged decision needs its merge commit, and only it has one")
        return self


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
