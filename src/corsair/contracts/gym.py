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
    identity (``config``), each role's instruction and packet digests, its agent spec,
    output schema and runtime skills digests from the manifest's ``capabilities``, the
    risk-assessment and
    budget-policy digests, the trusted image and each role's model. A value an older
    manifest did not record stays ``None``. The per-case ``request_digest`` stays in
    ``Trajectory.identity``; ``image`` varies per language and ``budget_policy`` per
    request budget, so a scorecard keeps every distinct value of each component.
    """

    package_version: str | None = Field(default=None, max_length=64)
    config: Digest | None = None
    producer_prompt: Digest | None = None
    auditor_prompt: Digest | None = None
    producer_packet: Digest | None = None
    auditor_packet: Digest | None = None
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

    Derived only from code-owned gate-ledger gates, workflow-owned reason text and the
    stored raw receipts' structure (see ``evaluation.gym.scoring.operational_stop``);
    never from model-authored text.
    """

    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    ACTIVITY_TIMEOUT = "activity_timeout"
    EPISODE_TIMEOUT = "episode_timeout"
    PROVIDER_TEMPORARY = "provider_temporary"
    OPERATION_RECONCILIATION = "operation_reconciliation"
    EXECUTION_CANCELLED = "execution_cancelled"
    EVIDENCE_NOT_RUN = "evidence_not_run"
    RESULT_UNAVAILABLE = "result_unavailable"
    # A recorded role ``ERROR`` whose stored raw receipt has no driver record (the sandbox
    # adapter's own record, e.g. ``SandboxExecutionError``), or whose evidence bundle or
    # raw receipt is missing: the sandbox, not the payload or the target, failed.
    SANDBOX_FAULT = "sandbox_fault"


class OperationalEpisode(Contract):
    """One operational stop on a scorecard: which case and repeat, and why."""

    case_id: Identifier
    repeat: int = Field(ge=0)
    language: str = Field(min_length=1, max_length=64)
    reason: OperationalReason


class TargetExceptionEpisode(Contract):
    """One target-side exception episode on a scorecard: which case and repeat.

    See ``Trajectory.target_exception``; the stored raw receipts, never model text or the
    admitted observation, decide it.
    """

    case_id: Identifier
    repeat: int = Field(ge=0)
    language: str = Field(min_length=1, max_length=64)


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
    # A terminal ``ERROR`` whose errored roles' raw receipts each show a completed native
    # run with ``observation_kind=execution_error``, the bound finding line covered,
    # cleanup confirmed and no ``error`` or ``driver_error``: an exception the target
    # raised outside the recipe's allowed exceptions. The kernel's ``ERROR`` verdict is
    # unchanged; the gym scores it 0, like an abstention, and names its stop
    # ``target_exception``. Never operational.
    target_exception: bool = False

    @model_validator(mode="after")
    def coherent_operational(self):
        if self.operational != (self.operational_reason is not None):
            raise ValueError("an operational episode needs its reason, and only it has one")
        if self.operational and self.target_exception:
            raise ValueError("a target-side exception episode is never operational")
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
    # Target-side exception episodes (see ``Trajectory``); unknown on older scorecards.
    target_exception_episodes: int | None = Field(default=None, ge=0)


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
    # Target-side exception episodes: the total, unknown on older scorecards, and each one.
    target_exception_episodes: int | None = Field(default=None, ge=0)
    target_exceptions: list[TargetExceptionEpisode] = Field(default_factory=list)


class GateDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INCOMPARABLE = "INCOMPARABLE"
    # Only with a noise band: every deciding regression lies inside the band, so the
    # gate cannot tell the candidate from run-to-run noise; a confirmation run decides.
    INCONCLUSIVE = "INCONCLUSIVE"

    @property
    def exit_code(self) -> int:
        """0 accepted, 1 rejected, 2 incomparable, 3 inconclusive."""
        return _EXIT_CODES[self]


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
    # Accuracy track: neither macro nor the target language's verified accuracy rose.
    ACCURACY_NOT_IMPROVED = "accuracy_not_improved"
    # Efficiency track: macro verified accuracy fell below the baseline's.
    ACCURACY_BELOW_BASELINE = "accuracy_below_baseline"
    # Efficiency track: neither macro effective tokens nor (comparable) p50 seconds fell 10 %.
    EFFICIENCY_NOT_IMPROVED = "efficiency_not_improved"
    # Never causes a rejection: p50 seconds were not counted, because the runs recorded
    # different or unknown concurrency, or either run had (or may have had) an
    # operational episode.
    LATENCY_NOT_COMPARABLE = "latency_not_comparable"
    # The noise band (``--noise``) scored another dataset, budgets or repeat count than
    # the gated scorecards: the gate is INCOMPARABLE rather than reading the wrong band.
    NOISE_MISMATCH = "noise_mismatch"
    # Names an INCONCLUSIVE gate, never causes one: every deciding regression lies inside
    # the noise band, so a confirmation run decides.
    WITHIN_NOISE = "within_noise"
    # Paired per-case outcomes: among the deciding languages more cases went from a
    # majority pass to a majority fail than the reverse, on a gate that would otherwise
    # accept (accuracy or objective track).
    PAIRED_REGRESSION = "paired_regression"
    # Slice gate only (``GateVerdict.slice``): the candidate ran cases the baseline did
    # not score, a sliced baseline ran other cases than the candidate, or no case was
    # scored on both sides; INCOMPARABLE.
    SLICE_MISMATCH = "slice_mismatch"
    # Slice gate only: a slice case went from a majority pass to a majority fail outside
    # the noise band.
    SLICE_REGRESSED = "slice_regressed"
    # Slice gate only: no slice case went from a majority fail to a majority pass outside
    # the noise band.
    SLICE_NOT_IMPROVED = "slice_not_improved"
    # ``corsair gym noise`` only, never a gate reason: the runs recorded different (or
    # unknown) configuration identities, or different repeat counts, so their spread is
    # not one configuration's noise.
    IDENTITY_MISMATCH = "identity_mismatch"
    REPEATS_MISMATCH = "repeats_mismatch"


# Which criterion a gate decides on (see ``evaluation.gym.gate.gate``): the overall
# objective J, an accuracy hypothesis or an efficiency hypothesis.
GateTrack = Literal["accuracy", "efficiency", "objective"]


_EXIT_CODES = {
    GateDecision.ACCEPTED: 0,
    GateDecision.REJECTED: 1,
    GateDecision.INCOMPARABLE: 2,
    GateDecision.INCONCLUSIVE: 3,
}

# The headline metrics a noise band covers; per-language verified accuracy is keyed by
# language beside them.
NoiseMetric = Literal[
    "objective_j", "macro_verified_accuracy", "macro_effective_tokens", "macro_p50_seconds"
]
# Floating-point slack for a recomputed spread.
_SPREAD_TOLERANCE = 1e-9
_MAX_NOISE_RUNS = 64


class NoiseSpread(Contract):
    """One metric across the runs of one configuration: pure arithmetic over scorecards.

    ``values`` follow ``NoiseBand.runs``. ``half_range`` is (max - min) / 2 and ``stdev``
    the sample standard deviation. A gate reads a difference within ``band`` (max - min,
    the largest difference two of these runs showed) as noise, and for a positive scale
    metric (tokens, seconds) a ratio to ``mean`` within min / mean to max / mean.
    ``max_ratio`` (max / min) is recorded for information.
    """

    values: list[float] = Field(min_length=2, max_length=_MAX_NOISE_RUNS)
    mean: float
    half_range: float = Field(ge=0)
    stdev: float = Field(ge=0)
    # max / min of a positive scale metric; ``None`` for a difference metric.
    max_ratio: float | None = Field(default=None, ge=1)

    @property
    def band(self) -> float:
        """The largest difference between two runs: twice the half-range."""
        return 2 * self.half_range

    @model_validator(mode="after")
    def coherent_spread(self):
        values = self.values
        mean = sum(values) / len(values)
        stdev = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
        expected = (mean, (max(values) - min(values)) / 2, stdev)
        recorded = (self.mean, self.half_range, self.stdev)
        if any(abs(a - b) > _SPREAD_TOLERANCE for a, b in zip(expected, recorded, strict=True)):
            raise ValueError("a noise spread's mean, half-range and stdev follow its values")
        if self.max_ratio is not None and (
            min(values) <= 0 or abs(self.max_ratio - max(values) / min(values)) > _SPREAD_TOLERANCE
        ):
            raise ValueError("a noise spread's max_ratio is max / min of positive values")
        return self


# A case across the runs of a noise band. With pooled counts: a run of the band's repeats
# fails (``stable_pass``) or passes (``stable_fail``) its majority with probability at
# most ``SIGNIFICANCE_LEVEL``, else ``unstable``. A band without pooled counts (written
# before them) classifies by the per-run majority outcomes: the same in every run, or not.
CaseStability = Literal["stable_pass", "stable_fail", "unstable"]
# Why a noise band records no per-case stability: a run's trajectories reproducing its
# scorecard were not found.
NoiseCasesUnknown = Literal["trajectories_missing"]
# Why a paired flip is within noise. With a band carrying pooled counts for the case:
# Fisher's exact test on the candidate's episodes against the band's pooled episodes does
# not separate them in the flip's direction (``episode_rate``). Otherwise: the case's
# language band is a whole case, or the band classifies the case ``unstable`` (which wins
# when both hold).
FlipNoise = Literal["language_band", "unstable_case", "episode_rate"]
_MAX_NOISE_CASES = 4096
# The level the gym's exact rules read: a pooled majority probability at most this is
# stable, and Fisher's exact test separates two episode rates when p is below it.
SIGNIFICANCE_LEVEL = 0.05


class NoiseCase(Contract):
    """One case scored in every run of a noise band, per run in ``NoiseBand.runs`` order.

    ``majority_verified`` is the case's outcome in each run (whether more than half its
    repeats verified, ``evaluation.gym.scoring.majority_verified``); ``verified_episodes``
    counts the repeats that verified. ``episodes`` and ``verified`` pool the case's
    episodes and verified episodes over every run, and ``majority_pass_probability`` is
    the binomial probability that a run of the band's repeats at the pooled rate
    (verified / episodes) gets a majority pass. ``stability`` follows that probability
    (see ``CaseStability``); on a case recorded before pooled counts all three are
    ``None`` and ``stability`` follows the majority outcomes.
    """

    case_id: Identifier
    language: str = Field(min_length=1, max_length=64)
    majority_verified: list[bool] = Field(min_length=2, max_length=_MAX_NOISE_RUNS)
    verified_episodes: list[int] = Field(min_length=2, max_length=_MAX_NOISE_RUNS)
    stability: CaseStability
    episodes: int | None = Field(default=None, ge=1)
    verified: int | None = Field(default=None, ge=0)
    majority_pass_probability: float | None = Field(default=None, ge=0, le=1)

    @property
    def pooled(self) -> bool:
        """Whether the case carries pooled counts (a band written since they exist)."""
        return self.episodes is not None

    @staticmethod
    def pooled_stability(probability: float) -> CaseStability:
        """A case's stability from its majority-pass probability."""
        if 1 - probability <= SIGNIFICANCE_LEVEL + _SPREAD_TOLERANCE:
            return "stable_pass"
        if probability <= SIGNIFICANCE_LEVEL + _SPREAD_TOLERANCE:
            return "stable_fail"
        return "unstable"

    @model_validator(mode="after")
    def coherent_case(self):
        if len(self.majority_verified) != len(self.verified_episodes):
            raise ValueError("a noise case has one majority outcome and one count per run")
        if any(count < 0 for count in self.verified_episodes):
            raise ValueError("a noise case's verified episode counts are not negative")
        pooled = (self.episodes, self.verified, self.majority_pass_probability)
        if None in pooled and any(value is not None for value in pooled):
            raise ValueError("a noise case records all of its pooled counts or none")
        if self.episodes is not None and self.majority_pass_probability is not None:
            if self.verified != sum(self.verified_episodes) or self.verified > self.episodes:
                raise ValueError("a noise case pools its verified episodes, at most its episodes")
            if self.stability != self.pooled_stability(self.majority_pass_probability):
                raise ValueError("a noise case's stability follows its majority-pass probability")
            return self
        if all(self.majority_verified):
            expected = "stable_pass"
        elif any(self.majority_verified):
            expected = "unstable"
        else:
            expected = "stable_fail"
        if self.stability != expected:
            raise ValueError("a noise case's stability follows its majority outcomes")
        return self


class NoiseBand(Contract):
    """``corsair gym noise``: the spread of two or more runs of one configuration.

    Every run scored the same dataset with the same budgets, repeats and recorded
    ``run_identity``, unsliced, with known token usage; nothing is rescored. A gate given
    the band (``--noise``) reads a delta inside it as noise (see ``evaluation.gym.gate``).
    ``macro_p50_seconds`` is unknown when any run's is. ``cases`` classifies every case
    scored in all runs from the runs' trajectories; it is ``None`` with ``cases_unknown``
    (naming ``cases_unknown_runs``) when a run's trajectories were missing, and ``None``
    without a reason on a band written before per-case stability. A band whose cases carry
    pooled counts (``pooled``) lets a gate read flips and deciding languages by Fisher's
    exact test on episodes; a band without them is read by its spreads, as before.
    """

    schema_version: Literal["corsair.gym-noise/1"] = "corsair.gym-noise/1"
    dataset_digest: Digest
    budgets_digest: Digest | None = None
    repeats: int = Field(ge=1)
    run_identity: dict[str, list[str]] = Field(min_length=1)
    n_runs: int = Field(ge=2, le=_MAX_NOISE_RUNS)
    runs: list[Identifier] = Field(min_length=2, max_length=_MAX_NOISE_RUNS)
    objective_j: NoiseSpread
    macro_verified_accuracy: NoiseSpread
    macro_effective_tokens: NoiseSpread
    macro_p50_seconds: NoiseSpread | None = None
    # Per language: majority verified accuracy.
    languages: dict[str, NoiseSpread] = Field(min_length=1)
    # Per case, by case id; see the class docstring for ``None``.
    cases: list[NoiseCase] | None = Field(default=None, max_length=_MAX_NOISE_CASES)
    cases_unknown: NoiseCasesUnknown | None = None
    cases_unknown_runs: list[Identifier] = Field(default_factory=list, max_length=_MAX_NOISE_RUNS)

    @model_validator(mode="after")
    def coherent_band(self):
        if self.n_runs != len(self.runs) or len(set(self.runs)) != len(self.runs):
            raise ValueError("a noise band names each of its n_runs distinct runs once")
        spreads = [self.objective_j, self.macro_verified_accuracy, self.macro_effective_tokens]
        spreads += [*self.languages.values()]
        if self.macro_p50_seconds is not None:
            spreads.append(self.macro_p50_seconds)
        if any(len(spread.values) != self.n_runs for spread in spreads):
            raise ValueError("every noise spread has one value per run")
        if self.cases is not None and (self.cases_unknown or self.cases_unknown_runs):
            raise ValueError("a noise band records either its cases or why they are unknown")
        if not set(self.cases_unknown_runs) <= set(self.runs) or (
            bool(self.cases_unknown_runs) != (self.cases_unknown is not None)
        ):
            raise ValueError("a noise band names which of its runs left its cases unknown")
        cases = self.cases or []
        if any(len(case.majority_verified) != self.n_runs for case in cases):
            raise ValueError("a noise case has one entry per run")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("a noise band classifies each case once")
        if len({case.pooled for case in cases}) > 1:
            raise ValueError("a noise band pools the counts of every case or of none")
        return self

    @property
    def pooled(self) -> bool:
        """Whether the band carries pooled per-case episode counts."""
        return bool(self.cases) and all(case.pooled for case in self.cases or [])


class DecidingMetric(Contract):
    """One headline metric recomputed over the deciding languages only (``min_cases``).

    ``baseline`` is the installed baseline scorecard's figure, or, in the ``*_to_band``
    fields of ``GateVerdict``, the mean of the noise band's runs."""

    baseline: float
    candidate: float
    delta: float


class EpisodeRate(Contract):
    """A candidate's episodes against a noise band's pooled reference episodes.

    ``p_value`` is Fisher's exact test, two-sided, on verified against unverified
    episodes (``evaluation.gym.exact.fisher_exact``).
    """

    reference_verified: int = Field(ge=0)
    reference_episodes: int = Field(ge=1)
    candidate_verified: int = Field(ge=0)
    candidate_episodes: int = Field(ge=1)
    p_value: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def coherent_counts(self):
        if (
            self.reference_verified > self.reference_episodes
            or self.candidate_verified > self.candidate_episodes
        ):
            raise ValueError("verified episodes are at most the episodes")
        return self

    @property
    def direction(self) -> int:
        """+1 when the candidate's rate is higher than the reference's, -1 lower, 0 equal."""
        candidate = self.candidate_verified * self.reference_episodes
        reference = self.reference_verified * self.candidate_episodes
        return (candidate > reference) - (candidate < reference)

    def separates(self, direction: int) -> bool:
        """Whether the candidate's rate moved in ``direction`` with p below the level."""
        return self.direction == direction and self.p_value < SIGNIFICANCE_LEVEL


class PairedCase(Contract):
    """One case whose majority outcome flipped between baseline and candidate."""

    case_id: Identifier
    language: str = Field(min_length=1, max_length=64)
    # Whether the language decides the gate (see ``GateVerdict.min_cases``).
    deciding: bool = True
    # With a noise band carrying pooled counts for the case: Fisher's exact test does not
    # separate the candidate's episodes from the pooled reference episodes in the flip's
    # direction. With a band without them: its spread for the case's language is a whole
    # case (±1.0), or it classifies the case ``unstable``. Such a flip is read as noise,
    # never as a regression or an improvement.
    within_noise: bool = False
    # Why the flip is within noise; ``None`` on records written before reasons existed.
    noise_reason: FlipNoise | None = None
    # With a band carrying pooled counts for the case: the episodes the test read and its
    # p-value; all ``None`` otherwise.
    reference_verified: int | None = Field(default=None, ge=0)
    reference_episodes: int | None = Field(default=None, ge=1)
    candidate_verified: int | None = Field(default=None, ge=0)
    candidate_episodes: int | None = Field(default=None, ge=1)
    p_value: float | None = Field(default=None, ge=0, le=1)

    @property
    def rate(self) -> EpisodeRate | None:
        """The episode comparison the flip was read by, when there was one."""
        if (
            self.reference_verified is None
            or self.reference_episodes is None
            or self.candidate_verified is None
            or self.candidate_episodes is None
            or self.p_value is None
        ):
            return None
        return EpisodeRate(
            reference_verified=self.reference_verified,
            reference_episodes=self.reference_episodes,
            candidate_verified=self.candidate_verified,
            candidate_episodes=self.candidate_episodes,
            p_value=self.p_value,
        )

    @model_validator(mode="after")
    def coherent_noise_reason(self):
        if self.noise_reason is not None and not self.within_noise:
            raise ValueError("a noise reason names a flip within noise")
        counts = (
            self.reference_verified,
            self.reference_episodes,
            self.candidate_verified,
            self.candidate_episodes,
            self.p_value,
        )
        if None in counts and any(value is not None for value in counts):
            raise ValueError("a paired case records all of its episode counts and p-value or none")
        if self.rate is not None and self.within_noise != (self.noise_reason == "episode_rate"):
            raise ValueError("a flip read by its episodes is within noise only by episode rate")
        return self


class PairedCounts(Contract):
    """Cases present on both sides by baseline and candidate majority outcome (verified)."""

    pass_to_fail: int = Field(default=0, ge=0)
    fail_to_pass: int = Field(default=0, ge=0)
    stable_pass: int = Field(default=0, ge=0)
    stable_fail: int = Field(default=0, ge=0)


class PairedOutcomes(PairedCounts):
    """``GateVerdict.paired``: every case scored on both sides, compared by its majority.

    A case's outcome is whether the majority of its repeats verified, read from each run's
    trajectories. The totals cover every paired case; ``languages`` splits them by
    language; the flipped cases are listed per direction. ``deciding_pass_to_fail`` and
    ``deciding_fail_to_pass`` count flips in deciding languages outside the noise band,
    which ``paired_regression`` compares. Cases only one side scored are never paired.
    """

    languages: dict[str, PairedCounts] = Field(default_factory=dict)
    pass_to_fail_cases: list[PairedCase] = Field(default_factory=list)
    fail_to_pass_cases: list[PairedCase] = Field(default_factory=list)
    deciding_pass_to_fail: int = Field(default=0, ge=0)
    deciding_fail_to_pass: int = Field(default=0, ge=0)
    baseline_only: list[Identifier] = Field(default_factory=list)
    candidate_only: list[Identifier] = Field(default_factory=list)


class GateVerdict(Contract):
    decision: GateDecision
    reasons: list[GateReason] = Field(default_factory=list)
    baseline_run_id: Identifier
    candidate_run_id: Identifier
    # The track decided on; records written before tracks existed were objective gates.
    track: GateTrack = "objective"
    # The accuracy track's named target language, when one was given.
    target_language: str | None = Field(default=None, min_length=1, max_length=64)
    # Always reported, whatever the track.
    delta_j: float | None = None
    # Candidate minus baseline macro (majority) verified accuracy.
    delta_macro_verified_accuracy: float | None = None
    # Candidate over the installed baseline's macro effective tokens.
    token_ratio: float | None = None
    # Candidate over baseline macro p50 seconds; reported even when not comparable.
    seconds_ratio: float | None = None
    # With a noise band: the candidate over the mean of the band's runs. The token
    # ceiling, the efficiency ratios and their noise (the band's min / mean to max / mean)
    # are then read on these. ``None`` without a band, or when either side is unknown.
    token_ratio_to_band: float | None = None
    seconds_ratio_to_band: float | None = None
    language_deltas: dict[str, float | None] = Field(default_factory=dict)
    # ``delta_j``, ``delta_macro_verified_accuracy`` and ``language_deltas`` are always
    # measured from the installed baseline scorecard. With a noise band (of the gated
    # dataset, budgets and repeats) the same deltas measured from the mean of the band's
    # runs follow, and every rule reads them: ``language_regressed``, the accuracy steps,
    # J's gain, the efficiency accuracy floor and the noise checks. A language the band
    # lacks keeps its installed-reference delta in ``language_deltas_to_band``, and the
    # worst-language delta is unknown when the band lacks a baseline language. ``None``
    # and empty without a band, and on records written before them.
    delta_j_to_band: float | None = None
    delta_macro_verified_accuracy_to_band: float | None = None
    delta_worst_language_verified_accuracy_to_band: float | None = None
    language_deltas_to_band: dict[str, float | None] = Field(default_factory=dict)
    # With a band carrying pooled counts and the candidate's trajectories: per deciding
    # language, the candidate's episodes of its cases against the band's pooled episodes
    # of its cases. A language regresses only when its rate is lower with p below
    # ``SIGNIFICANCE_LEVEL`` and improves only when it is higher with p below it.
    language_rates: dict[str, EpisodeRate] = Field(default_factory=dict)
    regressed_languages: list[str] = Field(default_factory=list)
    # Regressed languages explained entirely by operational episodes.
    operationally_confounded_languages: list[str] = Field(default_factory=list)
    # Per ``RunIdentity`` component: whether its values differ; ``None`` when unknown on
    # either side. Reported only; identity never makes a gate INCOMPARABLE.
    identity_changes: dict[str, bool | None] = Field(default_factory=dict)
    # A smoke gate reports ``objective_below_threshold`` without rejecting on it, so its
    # ACCEPTED is a smoke result, never an acceptance.
    smoke: bool = False
    # Baseline languages with one case: one episode flips their verified accuracy, and so
    # moves J's worst-language term by its whole range. Reported only.
    single_case_languages: list[str] = Field(default_factory=list)
    # The noise band the gate read (``--noise``), when one was given.
    noise: NoiseBand | None = None
    # With a band: the headline metrics and the languages whose delta lies inside it.
    within_noise: list[NoiseMetric] = Field(default_factory=list)
    languages_within_noise: list[str] = Field(default_factory=list)
    # Only baseline languages with at least this many cases decide ``language_regressed``,
    # ``accuracy_not_improved`` and ``accuracy_below_baseline``; 1 (every language, and
    # every record before ``--min-cases``) leaves the next five fields empty.
    min_cases: int = Field(default=1, ge=1)
    deciding_languages: list[str] = Field(default_factory=list)
    # Shown with their deltas, never deciding: fewer than ``min_cases`` baseline cases.
    reported_languages: list[str] = Field(default_factory=list)
    # Macro and worst-language verified accuracy over the deciding languages, as decided on.
    deciding_macro_verified_accuracy: DecidingMetric | None = None
    deciding_worst_language: DecidingMetric | None = None
    # With a noise band: the same two figures with ``baseline`` the mean over the band's
    # runs of each run's figure over the deciding languages; the gate then decides on
    # these. ``None`` without a band or when the band lacks a deciding language (the
    # installed-reference figures then decide).
    deciding_macro_verified_accuracy_to_band: DecidingMetric | None = None
    deciding_worst_language_to_band: DecidingMetric | None = None
    # J recomputed over the deciding languages; informational, never decided on.
    objective_j_deciding: DecidingMetric | None = None
    # Paired per-case majority outcomes, when both runs' trajectories were read.
    paired: PairedOutcomes | None = None
    # A slice screen (``gate(..., slice=True)``): decided only on the paired outcomes of
    # ``slice_cases`` (the candidate's cases, each also scored by the baseline), run
    # ``slice_repeats`` times each by the candidate. J, accuracy, tokens and language
    # deltas are then over the slice and never decide; an ACCEPTED slice is a screen
    # for a full run, never an acceptance. Records before slices decode as full gates.
    slice: bool = False
    slice_cases: list[Identifier] = Field(default_factory=list)
    slice_repeats: int | None = Field(default=None, ge=0)
    # Slice cases the noise band classifies ``unstable`` (coin-flips): a sentinel among
    # them guards nothing. Reported only; empty without a band or its per-case stability.
    slice_unstable_cases: list[Identifier] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """0 accepted, 1 rejected, 2 incomparable, 3 inconclusive."""
        return self.decision.exit_code

    @property
    def anchored_to_band(self) -> bool:
        """Whether the gate measured its deltas from the noise band's mean."""
        return self.delta_j_to_band is not None


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
    # The track every tier was gated on; unknown on records written before tracks.
    track: GateTrack | None = None
    tier0: TierGate | None = None
    tier1: TierGate | None = None
    decision: GateDecision | None = None
    complete: bool | None = None
    skipped: dict[str, SkipReason] = Field(default_factory=dict)
    # The reference directory holding ``<tier>.json``; each tier gate names its file.
    reference: str | None = Field(default=None, min_length=1, max_length=300)
    invocation: list[str] | None = Field(default=None, max_length=256)
    recorded_at: datetime | None = None
    # The noise band files given (``--noise``); each tier gate embeds the band it read.
    noise: list[str] = Field(default_factory=list, max_length=8)


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
    # The noise band files the row's gates read (``--noise``, or the verify record's).
    noise: list[str] = Field(default_factory=list, max_length=8)
    # A signal-slice screen of the candidate against the tier1 reference (``--slice``):
    # a screen before the full tier1 run, never an acceptance by itself.
    slice: TierGate | None = None

    @model_validator(mode="after")
    def coherent_entry(self):
        if self.entry == "baseline" and (
            self.tier is None or self.dataset_digest is None or self.objective_j is None
        ):
            raise ValueError("a baseline row needs a scorecard and its tier")
        if (self.decision == "merged") != (self.merge_commit is not None):
            raise ValueError("a merged decision needs its merge commit, and only it has one")
        if self.slice is not None and not self.slice.gate.slice:
            raise ValueError("a slice row's gate must be a slice gate")
        if any(gated is not None and gated.gate.slice for gated in (self.tier0, self.tier1)):
            raise ValueError("a slice gate belongs in the row's slice, not a tier gate")
        accepted = self.decision in ("accepted", "merged")
        if self.slice is not None and self.tier1 is None and accepted:
            raise ValueError(
                "a slice screen alone is never an acceptance; gate the full tier1 run first"
            )
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
