"""Score a saved evaluation report into per-repeat trajectories and one scorecard.

Pure functions over a report (``{rows, summary, dataset_digest}``), its frozen dataset
manifest (the only source of expected labels; rows never echo an oracle) and each row's
stored ``InvestigationResult``. Rows are produced by ``corsair.evaluation.scoring.score``;
this module adds the reward decomposition and the per-kind and per-language aggregates.
Unknown usage stays unknown: it earns no efficiency bonus and is never counted as zero.
"""

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import mean
from typing import Any, NamedTuple

from pydantic import BaseModel

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    Digest,
    GroupSummary,
    InvestigationResult,
    ModelCall,
    Observation,
    OperationalEpisode,
    OperationalReason,
    Oracle,
    PreparedCase,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    RoundSummary,
    RunContext,
    RunIdentity,
    RunManifest,
    Scorecard,
    TargetExceptionEpisode,
    Trajectory,
    Usage,
    Verdict,
    digest,
)
from corsair.contracts.gym import Budgets, DominantCall
from corsair.evaluation.comparison import row_stop
from corsair.evaluation.datasets import LoadedDataset, load_dataset
from corsair.evaluation.gym.budgets import budgets_digest
from corsair.evaluation.ledger import qualify_unverified, row_ledger
from corsair.policies.verdicts import candidate_key

DEMONSTRATED = frozenset({Verdict.EXPLOIT_DEMONSTRATED, Verdict.COMPONENT_EXPLOIT_DEMONSTRATED})
DECISIVE = DEMONSTRATED | {Verdict.EXPLOIT_NOT_DEMONSTRATED}
_OPERATIONAL_VERDICTS = frozenset({Verdict.ERROR, Verdict.UNABLE_TO_RUN})
_OPERATIONAL_STATUSES = frozenset({"ERROR", "BLOCKED", "CANCELLED"})
# Ledger gates that cost a shaping penalty each: a request too large to send, or a
# response cut off at the output cap.
SHAPED_GATES = frozenset({"packet_too_large", "provider_max_tokens"})
# Round gates whose feedback the adapters mark operational and that no agent output
# causes: an episode's elapsed-time limit, a transient provider or connection fault,
# and a replay refused after an earlier, unconfirmed execution (a lost host).
# ``provider_max_tokens``, ``packet_too_large`` and ``provider_permanent`` stay
# behavioural: the request or the reasoning spend can cause them.
_OPERATIONAL_ROUND_GATES = {
    "episode_timeout": OperationalReason.EPISODE_TIMEOUT,
    "provider_temporary": OperationalReason.PROVIDER_TEMPORARY,
    "operation-reconciliation": OperationalReason.OPERATION_RECONCILIATION,
}
# The workflow's terminal reason for a Temporal activity timeout: ``<phase>: <cause>``,
# where the cause is the SDK's timeout message, e.g. ``evidence: activity Heartbeat timeout``.
_ACTIVITY_TIMEOUT = re.compile(
    r"[a-z]+: activity (Heartbeat|StartToClose|ScheduleToStart|ScheduleToClose) timeout"
)

# The gym's stop name for a terminal ``ERROR`` that the raw receipts show as an exception
# the target raised (see ``target_exception``); the kernel's ledger gate stays
# ``execution_error``.
TARGET_EXCEPTION_STOP = "target_exception"
_TARGET_EXCEPTION_KIND = "execution_error"
_ROLES = ("control", "adversarial")

REWARD_VERIFIED = 1.0
REWARD_UNRESOLVED = 0.0
# Neither a false label nor an infrastructure fault: scored like an abstention.
REWARD_TARGET_EXCEPTION = 0.0
REWARD_OPERATIONAL = -0.5
REWARD_FALSE_LABEL = -1.0
BONUS_WEIGHT = 0.25
BONUS_CLAMP = 0.5
SHAPING_PENALTY = -0.05
CACHED_TOKEN_WEIGHT = 0.1
OUTPUT_TOKEN_WEIGHT = 4.0
WORST_LANGUAGE_WEIGHT = 0.5

# A gym run directory holds these three files.
REPORT_FILE = "report.json"
TRAJECTORIES_FILE = "trajectories.jsonl"
SCORECARD_FILE = "scorecard.json"


def language_of(kind: str) -> str:
    """The runtime language of a recipe kind: its prefix before the first dot."""
    return kind.split(".", 1)[0]


def allowed_verdicts(oracle: Oracle) -> frozenset[Verdict]:
    return frozenset(verdict for verdict in Verdict if oracle.verdict_allowed(verdict))


def expects_decisive(oracle: Oracle) -> bool:
    """Whether the oracle allows only decisive verdicts, so an abstention cannot pass."""
    allowed = allowed_verdicts(oracle)
    return bool(allowed) and allowed <= DECISIVE


def _clamp(value: float) -> float:
    return max(-BONUS_CLAMP, min(BONUS_CLAMP, value))


def effective_tokens(
    input_tokens: int | None, output_tokens: int | None, cached_input_tokens: int | None
) -> float | None:
    """``uncached_in + 0.1 * cached_in + 4 * out``; unreported cached tokens get no discount."""
    if input_tokens is None or output_tokens is None:
        return None
    cached = min(cached_input_tokens or 0, input_tokens)
    return (
        (input_tokens - cached) + CACHED_TOKEN_WEIGHT * cached + OUTPUT_TOKEN_WEIGHT * output_tokens
    )


def phi_tokens(tokens: float, budget: float) -> float:
    return _clamp(1 - math.log1p(tokens) / math.log1p(budget))


def phi_time(seconds: float, budget: float) -> float:
    return _clamp(1 - seconds / budget)


def _verdict(value: object) -> Verdict | None:
    return Verdict(value) if isinstance(value, str) and value in Verdict else None


def _false_label(row: Mapping[str, Any], oracle: Oracle, verdict: Verdict | None) -> bool:
    """A forbidden label, or a decisive verdict the oracle does not allow."""
    if row.get("forbidden_label") is True or verdict in oracle.forbidden_verdicts:
        return True
    return verdict in DECISIVE and not oracle.verdict_allowed(verdict)


def _operational(row: Mapping[str, Any], verdict: Verdict | None) -> bool:
    if row.get("status") == "unavailable" or verdict in _OPERATIONAL_VERDICTS:
        return True
    return verdict is None and row.get("execution_status") in _OPERATIONAL_STATUSES


def verdict_reward(
    passed: bool,
    verified: bool,
    false_label: bool,
    operational: bool,
    target_exception: bool = False,
) -> float:
    """The complete reward table, in precedence order."""
    if passed and verified:
        return REWARD_VERIFIED
    if false_label:
        return REWARD_FALSE_LABEL
    if target_exception:
        return REWARD_TARGET_EXCEPTION
    if operational:
        return REWARD_OPERATIONAL
    return REWARD_UNRESOLVED


def _usages(result: InvestigationResult | None) -> list[Usage]:
    if result is None:
        return []
    usage = [item.producer.usage for item in result.rounds]
    return usage + [item.audit.usage for item in result.rounds if item.audit is not None]


def _known_sum(values: Iterable[object]) -> int | float | None:
    """Sum the reported values; ``None`` when none was reported."""
    known = [value for value in values if isinstance(value, int | float)]
    return sum(known) if known else None


def _call_details(usages: Sequence[Usage], field: str) -> list[dict[str, Any]]:
    """Per-call detail recorded by the inference adapter, when this Usage carries it."""
    details: list[dict[str, Any]] = []
    for usage in usages:
        for item in getattr(usage, field, None) or []:
            details.append(item.model_dump(mode="json") if isinstance(item, BaseModel) else item)
    return details


def dominant_call(calls: Sequence[ModelCall]) -> DominantCall | None:
    """The call with the most reported output tokens; the first one wins a tie."""
    known = [
        (position, call)
        for position, call in enumerate(calls, start=1)
        if call.output_tokens is not None
    ]
    if not known:
        return None
    position, call = max(known, key=lambda item: item[1].output_tokens or 0)
    return DominantCall(
        position=position,
        index=call.index,
        output_tokens=call.output_tokens or 0,
        seconds=call.seconds,
    )


def cap_markers(
    calls: Sequence[ModelCall], output_cap: int | None
) -> tuple[int | None, bool | None]:
    """Calls whose reported output reached the cap, and whether reasoning filled one.

    Both are unknown without a cap or without per-call reports. A capped call exhausted
    its cap on reasoning when its thought tokens are at least its output tokens (the
    OpenAI-compatible accounting, where output includes reasoning); a capped call whose
    thought tokens were not reported leaves that answer unknown unless another is known.
    """
    if output_cap is None or not calls:
        return None, None
    capped = [
        call
        for call in calls
        if call.output_tokens is not None and call.output_tokens >= output_cap
    ]
    thoughts = [(call.thought_tokens, call.output_tokens or 0) for call in capped]
    if any(thought is not None and thought >= output for thought, output in thoughts):
        return len(capped), True
    if any(thought is None for thought, _ in thoughts):
        return len(capped), None
    return len(capped), False


def _thought_share(thought_tokens: int | None, output_tokens: int | None) -> float | None:
    if thought_tokens is None or not output_tokens:
        return None
    return thought_tokens / output_tokens


def _role_seconds(role: RoleObservation | None, field: str) -> float | None:
    value = getattr(role, field, None) if role is not None else None
    return float(value) if isinstance(value, int | float) else None


def _round_seconds(item: RoundResult, field: str) -> float | None:
    observation = item.observation
    if observation is None:
        return None
    seconds = _known_sum(
        _role_seconds(role, field) for role in (observation.control, observation.adversarial)
    )
    return None if seconds is None else float(seconds)


def _round_stops(row: Mapping[str, Any]) -> dict[tuple[int, int], str]:
    stops: dict[tuple[int, int], str] = {}
    for entry in row_ledger(row):
        session, index, gate = entry.get("session"), entry.get("round"), entry.get("gate")
        if isinstance(session, int) and isinstance(index, int) and isinstance(gate, str):
            stops[(session, index)] = gate
    return stops


def round_summary(item: RoundResult, stop: str | None) -> RoundSummary:
    submission = item.producer.submission_for_verification()
    review = item.audit.review if item.audit is not None else None
    observation = item.observation
    return RoundSummary(
        session=item.session,
        index=item.index,
        stop=stop,
        payload_identity=None if submission is None else candidate_key(submission),
        control_payload=None if submission is None else submission.control_payload,
        exploit_payload=None if submission is None else submission.exploit_payload,
        producer_abstained=item.producer.abstention_reason() is not None,
        audit_decision=None if review is None else review.decision,
        audit_rule=None if review is None else review.rule,
        control_outcome=None
        if observation is None or observation.control is None
        else observation.control.outcome,
        adversarial_outcome=None
        if observation is None or observation.adversarial is None
        else observation.adversarial.outcome,
        sandbox_wall_seconds=_round_seconds(item, "wall_seconds"),
        sandbox_cpu_seconds=_round_seconds(item, "cpu_seconds"),
        sandbox_host_seconds=_round_seconds(item, "host_seconds"),
    )


def shaping(row: Mapping[str, Any], rounds: Sequence[RoundSummary]) -> float:
    """-0.05 per repeated candidate payload and per shaped ledger gate."""
    seen: set[str] = set()
    repeated = 0
    for item in rounds:
        if item.payload_identity is None:
            continue
        repeated += item.payload_identity in seen
        seen.add(item.payload_identity)
    shaped = sum(
        str(entry.get("gate", "")).split(":", 1)[0] in SHAPED_GATES for entry in row_ledger(row)
    )
    return SHAPING_PENALTY * (repeated + shaped)


def operational_stop(
    row: Mapping[str, Any], rounds: Sequence[RoundSummary], *, sandbox_fault: bool = False
) -> OperationalReason | None:
    """Why a failed episode stopped operationally, from code-owned records only.

    An unavailable row lost its result. Otherwise a recorded role ``ERROR`` decides:
    ``sandbox_fault`` when the stored raw receipts show the sandbox produced it
    (``sandbox_fault(store, result)``), else the episode is behavioural (a payload or the
    target raised in the sandbox). Then the episode's terminal stop decides: the
    workflow's ``execution_cancelled``; an ``execution_error`` whose reason is a Temporal
    activity timeout; a final round stopped by an operational gate in
    ``_OPERATIONAL_ROUND_GATES``; or a final round with no observation
    (``evidence_not_run``) that the workflow ended with an ``execution_*`` stop. Reasons
    of other gates, which may hold model-authored text, are never read.
    """
    status = row.get("status")
    if status == "pass":
        return None
    if status != "fail":
        return OperationalReason.RESULT_UNAVAILABLE
    if any(
        RoleOutcome.ERROR in (item.control_outcome, item.adversarial_outcome) for item in rounds
    ):
        return OperationalReason.SANDBOX_FAULT if sandbox_fault else None
    ledger = [entry for entry in row_ledger(row) if isinstance(entry, Mapping)]
    execution = next(
        (
            entry
            for entry in reversed(ledger)
            if entry.get("stage") == "policy" and str(entry.get("gate")).startswith("execution_")
        ),
        None,
    )
    if execution is not None:
        if execution.get("gate") == "execution_cancelled":
            return OperationalReason.EXECUTION_CANCELLED
        timeout = _ACTIVITY_TIMEOUT.fullmatch(str(execution.get("reason", "")))
        if execution.get("gate") == "execution_error" and timeout is not None:
            if timeout.group(1) == "Heartbeat":
                return OperationalReason.HEARTBEAT_TIMEOUT
            return OperationalReason.ACTIVITY_TIMEOUT
    last_round = next((entry for entry in reversed(ledger) if entry.get("stage") != "policy"), None)
    gate = None if last_round is None else last_round.get("gate")
    if isinstance(gate, str) and gate in _OPERATIONAL_ROUND_GATES:
        return _OPERATIONAL_ROUND_GATES[gate]
    if gate == "evidence_not_run" and execution is not None:
        return OperationalReason.EVIDENCE_NOT_RUN
    return None


def _target_exception_receipt(
    raw: object, *, operation_id: str, role: str, prepared: PreparedCase
) -> bool:
    """One role's raw receipt shows a completed native run that raised in the target.

    The adapter's own record (``error``) or the driver's (``driver_error``), a missing
    driver record, unconfirmed cleanup, or a run that never covered the bound finding
    line in the recipe module is a harness or sandbox fault, not a target exception.
    """
    if not isinstance(raw, dict) or raw.get("schema_version") != "corsair.raw-evidence/1":
        return False
    if raw.get("operation_id") != operation_id or raw.get("role") != role:
        return False
    if raw.get("cleanup_confirmed") is not True or raw.get("error") is not None:
        return False
    record = raw.get("driver")
    if not isinstance(record, dict) or record.get("schema_version") != "corsair.driver/1":
        return False
    junit, lines, line = record.get("junit"), record.get("covered_lines"), prepared.bound_line
    return (
        record.get("driver_error") is None
        and record.get("operation_id") == operation_id
        and record.get("role") == role
        and record.get("outcome") == RoleOutcome.ERROR.value
        and record.get("observation_kind") == _TARGET_EXCEPTION_KIND
        and isinstance(junit, dict)
        and junit.get("status") == "ERROR"
        and record.get("coverage_file") == prepared.recipe.module_file == prepared.finding.file
        and line is not None
        and isinstance(lines, list)
        and line in lines
    )


def _errored_roles(observation: Observation) -> list[str]:
    return [
        role
        for role in _ROLES
        if (item := getattr(observation, role)) is not None and item.outcome is RoleOutcome.ERROR
    ]


def _driver_recorded(raw: object, *, operation_id: str, role: str) -> bool:
    """This operation and role's raw receipt carries a driver record: the driver ran."""
    if not isinstance(raw, dict) or raw.get("schema_version") != "corsair.raw-evidence/1":
        return False
    record = raw.get("driver")
    return (
        raw.get("operation_id") == operation_id
        and raw.get("role") == role
        and isinstance(record, dict)
        and record.get("schema_version") == "corsair.driver/1"
    )


def _round_sandbox_fault(store: ArtifactStore, observation: Observation) -> bool:
    errored = _errored_roles(observation)
    if not errored:
        return False
    if observation.artifact is None:
        return True
    try:
        bundle = store.get_json(observation.artifact)
        if (
            not isinstance(bundle, dict)
            or bundle.get("schema_version") != "corsair.evidence/1"
            or bundle.get("operation_id") != observation.operation_id
        ):
            return True
        receipts = {
            role: store.get_json(ArtifactRef.model_validate(bundle["roles"][role]))
            for role in errored
        }
    except (OSError, ValueError, KeyError, TypeError):
        return True
    return not all(
        _driver_recorded(receipts[role], operation_id=observation.operation_id, role=role)
        for role in errored
    )


def sandbox_fault(store: ArtifactStore, result: InvestigationResult | None) -> bool:
    """Whether a recorded role ``ERROR`` came from the sandbox, from stored raw receipts.

    A round whose admitted observation records a role ``ERROR`` is a sandbox fault when
    its evidence bundle is missing, unreadable or another operation's, or when an errored
    role's raw receipt is missing, unreadable, another operation's or role's, or carries
    no driver record (the sandbox adapter's own record, e.g. ``SandboxExecutionError``).
    A receipt with a driver record, whether a target-side exception or a payload-level
    ``ERROR``, is not: the payload or the target raised, which stays behavioural.
    """
    if result is None:
        return False
    return any(
        item.observation is not None and _round_sandbox_fault(store, item.observation)
        for item in result.rounds
    )


def target_exception(store: ArtifactStore, result: InvestigationResult | None) -> bool:
    """Whether a terminal ``ERROR`` was an exception the target raised, from raw receipts.

    The final round's evidence bundle names each role's stored raw receipt. Every role
    the kernel admitted as ``ERROR`` must pass ``_target_exception_receipt``; one harness
    or sandbox fault, a missing or unreadable receipt, or no observation keeps the
    episode an ``ERROR``. The admitted ``RoleObservation`` is read only for its outcome,
    so the answer holds whether or not it kept the receipt's coverage.
    """
    if result is None or result.verdict is not Verdict.ERROR or not result.rounds:
        return False
    observation = result.rounds[-1].observation
    if observation is None or observation.artifact is None:
        return False
    errored = _errored_roles(observation)
    if not errored:
        return False
    try:
        bundle = store.get_json(observation.artifact)
        if (
            not isinstance(bundle, dict)
            or bundle.get("schema_version") != "corsair.evidence/1"
            or bundle.get("operation_id") != observation.operation_id
        ):
            return False
        prepared = PreparedCase.model_validate(
            store.get_json(ArtifactRef.model_validate(bundle["prepared"]))
        )
        receipts = {
            role: store.get_json(ArtifactRef.model_validate(bundle["roles"][role]))
            for role in errored
        }
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return all(
        _target_exception_receipt(
            receipts[role], operation_id=observation.operation_id, role=role, prepared=prepared
        )
        for role in errored
    )


def _capability(manifest: RunManifest, role: str, key: str) -> str | None:
    value = manifest.capabilities.get(role, {}).get(key)
    return value if isinstance(value, str) else None


def run_identity(manifest: RunManifest | None) -> RunIdentity | None:
    """The full identity a stored result's manifest records; ``None`` without one."""
    if manifest is None:
        return None
    return RunIdentity(
        package_version=manifest.package_version,
        config=manifest.config_digest,
        producer_prompt=manifest.producer_prompt_digest,
        auditor_prompt=manifest.auditor_prompt_digest,
        producer_packet=manifest.producer_packet_digest,
        auditor_packet=manifest.auditor_packet_digest,
        producer_spec=_capability(manifest, "producer", "spec_digest"),
        auditor_spec=_capability(manifest, "auditor", "spec_digest"),
        producer_output_schema=_capability(manifest, "producer", "output_schema_digest"),
        auditor_output_schema=_capability(manifest, "auditor", "output_schema_digest"),
        producer_skills=_capability(manifest, "producer", "runtime_skills_digest"),
        auditor_skills=_capability(manifest, "auditor", "runtime_skills_digest"),
        risk_assessment=_capability(manifest, "producer", "risk_assessment_digest")
        or _capability(manifest, "auditor", "risk_assessment_digest"),
        budget_policy=_capability(manifest, "producer", "budget_policy_digest")
        or _capability(manifest, "auditor", "budget_policy_digest"),
        image=manifest.image_id,
        producer_model=manifest.models.get("producer"),
        auditor_model=manifest.models.get("auditor"),
    )


def _identity(result: InvestigationResult | None, row: Mapping[str, Any]) -> dict[str, str]:
    if result is not None and result.manifest is not None:
        manifest = result.manifest
        return {
            "config": manifest.config_digest,
            "request": manifest.request_digest,
            "producer_prompt": manifest.producer_prompt_digest,
            "auditor_prompt": manifest.auditor_prompt_digest,
        }
    config = row.get("config_digest")
    return {"config": config} if isinstance(config, str) else {}


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _qualified_row(row: Mapping[str, Any], result: InvestigationResult | None) -> Mapping[str, Any]:
    """The row with its stored ``evidence_unverified`` round stops named from the stored
    result (``ledger.qualify_unverified``), so a report saved before qualified labels
    scores under the same stop names as a new one. Only gate names change: no reward,
    shaping or operational rule reads an ``evidence_unverified`` stop."""
    ledger = row.get("gate_ledger")
    if result is None or not isinstance(ledger, list):
        return row
    return {**row, "gate_ledger": qualify_unverified(ledger, result)}


def trajectory(
    row: Mapping[str, Any],
    repeat: int,
    kind: str,
    oracle: Oracle,
    result: InvestigationResult | None,
    budgets: Budgets | None,
    *,
    git_commit: str | None = None,
    output_cap: int | None = None,
    target_exception: bool = False,
    sandbox_fault: bool = False,
) -> Trajectory:
    """Score one report row; ``result`` is its stored result, or None when unavailable.

    ``output_cap`` is the request's per-call output cap; it only sets the reasoning
    markers, which no reward, verified flag or gate reads. ``target_exception`` is
    ``target_exception(store, result)``; it applies only to a failed ``ERROR`` row.
    ``sandbox_fault`` is ``sandbox_fault(store, result)``; it names a failed row's recorded
    role ``ERROR`` operational (``operational_stop``) and never changes a reward.
    """
    row = _qualified_row(row, result)
    status = row.get("status")
    status = status if status in {"pass", "fail"} else "unavailable"
    verdict = _verdict(row.get("verdict"))
    passed = status == "pass"
    verified = passed and (verdict in DECISIVE or not expects_decisive(oracle))
    false_label = _false_label(row, oracle, verdict)
    target = target_exception and status == "fail" and verdict is Verdict.ERROR
    r_verdict = verdict_reward(
        passed, verified, false_label, _operational(row, verdict), target_exception=target
    )
    stops = _round_stops(row)
    rounds = [
        round_summary(item, stops.get((item.session, item.index)))
        for item in (result.rounds if result is not None else [])
    ]
    usages = _usages(result)
    calls = [call for usage in usages for call in usage.model_calls]
    capped_calls, reasoning_cap_exhausted = cap_markers(calls, output_cap)
    thought_tokens = _int_or_none(
        _known_sum(getattr(usage, "thought_tokens", None) for usage in usages)
    )
    cached = _int_or_none(
        _known_sum(getattr(usage, "cached_input_tokens", None) for usage in usages)
    )
    input_tokens = _int_or_none(row.get("input_tokens"))
    output_tokens = _int_or_none(row.get("output_tokens"))
    agent_seconds = _float_or_none(row.get("agent_seconds"))
    usage_known = None not in (input_tokens, output_tokens, agent_seconds)
    tokens = effective_tokens(input_tokens, output_tokens, cached)
    host = _known_sum(item.sandbox_host_seconds for item in rounds)
    seconds = None if agent_seconds is None else agent_seconds + float(host or 0)
    budget = None if budgets is None else budgets.root.get(kind)
    bonus_tokens = bonus_time = 0.0
    if passed and verified and usage_known and budget is not None:
        assert tokens is not None and seconds is not None
        bonus_tokens = phi_tokens(tokens, budget.effective_tokens)
        bonus_time = phi_time(seconds, budget.seconds)
    shaped = shaping(row, rounds)
    operational = None if target else operational_stop(row, rounds, sandbox_fault=sandbox_fault)
    reward = r_verdict + BONUS_WEIGHT * bonus_tokens + BONUS_WEIGHT * bonus_time + shaped
    disposition, execution = row.get("disposition"), row.get("execution_status")
    return Trajectory(
        run_id=str(row.get("run_id") or "unknown"),
        case_id=str(row["case_id"]),
        repeat=repeat,
        kind=kind,
        language=language_of(kind),
        expected_verdict=oracle.expected_verdict,
        acceptable_verdicts=oracle.acceptable_verdicts,
        forbidden_verdicts=oracle.forbidden_verdicts,
        status=status,
        verdict=verdict,
        disposition=disposition if isinstance(disposition, str) else None,
        execution_status=execution if isinstance(execution, str) else None,
        passed=passed,
        verified=verified,
        false_label=false_label,
        failure_stop=None if passed else (TARGET_EXCEPTION_STOP if target else row_stop(dict(row))),
        rounds=rounds,
        llm_calls=_int_or_none(row.get("llm_calls")),
        tool_calls=_int_or_none(row.get("tool_calls")),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        thought_tokens=thought_tokens,
        agent_seconds=agent_seconds,
        sandbox_wall_seconds=_float_or_none(
            _known_sum(item.sandbox_wall_seconds for item in rounds)
        ),
        sandbox_cpu_seconds=_float_or_none(_known_sum(item.sandbox_cpu_seconds for item in rounds)),
        sandbox_host_seconds=_float_or_none(host),
        model_calls=_call_details(usages, "model_calls"),
        tool_calls_detail=_call_details(usages, "tool_calls_detail"),
        thought_share=_thought_share(thought_tokens, output_tokens),
        output_cap=output_cap,
        capped_calls=capped_calls,
        reasoning_cap_exhausted=reasoning_cap_exhausted,
        dominant_call=dominant_call(calls),
        usage_known=usage_known,
        effective_tokens=tokens,
        seconds=seconds,
        reward_verdict=r_verdict,
        phi_tokens=bonus_tokens,
        phi_time=bonus_time,
        shaping=shaped,
        reward=reward,
        identity=_identity(result, row),
        models=dict(result.manifest.models) if result is not None and result.manifest else {},
        git_commit=git_commit,
        run_identity=run_identity(None if result is None else result.manifest),
        operational=operational is not None,
        operational_reason=operational,
        target_exception=target,
    )


def percentile(values: Sequence[float], rank: float) -> float | None:
    """Nearest-rank percentile; ``None`` for an empty population."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(rank / 100 * len(ordered)) - 1)]


def _known_mean(values: Iterable[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return mean(known) if known else None


def _known_count(flags: Iterable[bool | None]) -> int | None:
    """How many known flags are set; ``None`` when no flag is known."""
    known = [flag for flag in flags if flag is not None]
    return sum(known) if known else None


def _known_total(counts: Iterable[int | None]) -> int | None:
    known = [count for count in counts if count is not None]
    return sum(known) if known else None


def _fraction(flags: Sequence[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def is_majority(verified: int, repeats: int) -> bool:
    """Whether ``verified`` of ``repeats`` episodes is more than half: a majority pass."""
    return 2 * verified > repeats


def majority_verified(repeats: Sequence[Trajectory]) -> bool:
    """A case's outcome: whether more than half of its repeats verified."""
    return is_majority(sum(item.verified for item in repeats), len(repeats))


def case_outcomes(trajectories: Sequence[Trajectory]) -> dict[str, tuple[str, bool]]:
    """Per case id: its language and its majority outcome (``majority_verified``)."""
    by_case: dict[str, list[Trajectory]] = defaultdict(list)
    for item in trajectories:
        by_case[item.case_id].append(item)
    return {
        case: (repeats[0].language, majority_verified(repeats))
        for case, repeats in sorted(by_case.items())
    }


def _majority_verified_without_operational_failures(repeats: Sequence[Trajectory]) -> bool:
    """The majority had every operational episode verified; the confounding counterfactual."""
    return 2 * sum(item.verified or item.operational for item in repeats) > len(repeats)


def _case_cpu_seconds(repeats: Sequence[Trajectory]) -> float | None:
    """A case's mean sandbox CPU seconds over its repeats; unknown when any lacks it."""
    figures = [item.sandbox_cpu_seconds for item in repeats]
    if not figures or any(figure is None for figure in figures):
        return None
    return mean(figure for figure in figures if figure is not None)


def group_summary(trajectories: Sequence[Trajectory]) -> GroupSummary:
    """Case-level majority accuracy; reward, tokens and sandbox CPU seconds are means over
    repeats, then cases (a case lacking any episode's CPU figure is left out)."""
    by_case: dict[str, list[Trajectory]] = defaultdict(list)
    for item in trajectories:
        by_case[item.case_id].append(item)
    cases = list(by_case.values())
    tokens = [item.effective_tokens for item in trajectories if item.effective_tokens is not None]
    seconds = [item.seconds for item in trajectories if item.seconds is not None]
    stops = Counter(item.failure_stop for item in trajectories if item.failure_stop is not None)
    return GroupSummary(
        cases=len(cases),
        attempts=len(trajectories),
        raw_accuracy=_fraction([item.passed for item in trajectories]),
        verified_accuracy=_fraction([majority_verified(case) for case in cases]),
        mean_reward=mean(mean(item.reward for item in case) for case in cases) if cases else None,
        mean_effective_tokens=_known_mean(
            _known_mean(item.effective_tokens for item in case) for case in cases
        ),
        p95_effective_tokens=percentile(tokens, 95),
        p50_seconds=percentile(seconds, 50),
        p95_seconds=percentile(seconds, 95),
        mean_sandbox_cpu_seconds=_known_mean(_case_cpu_seconds(case) for case in cases),
        sandbox_cpu_unknown=sum(item.sandbox_cpu_seconds is None for item in trajectories),
        failure_stops=dict(sorted(stops.items(), key=lambda item: (-item[1], item[0]))),
        usage_unknown=sum(not item.usage_known for item in trajectories),
        mean_thought_share=_known_mean(
            _known_mean(item.thought_share for item in case) for case in cases
        ),
        capped_call_episodes=_known_count(
            None if item.capped_calls is None else item.capped_calls > 0 for item in trajectories
        ),
        reasoning_cap_exhausted=_known_count(item.reasoning_cap_exhausted for item in trajectories),
        operational_episodes=sum(item.operational for item in trajectories),
        verified_accuracy_without_operational_failures=_fraction(
            [_majority_verified_without_operational_failures(case) for case in cases]
        ),
        target_exception_episodes=sum(item.target_exception for item in trajectories),
    )


def _grouped(trajectories: Sequence[Trajectory], field: str) -> dict[str, GroupSummary]:
    groups: dict[str, list[Trajectory]] = defaultdict(list)
    for item in trajectories:
        groups[getattr(item, field)].append(item)
    return {name: group_summary(groups[name]) for name in sorted(groups)}


def _repeats(trajectories: Sequence[Trajectory], cases: Mapping[str, str]) -> int:
    counts = Counter(item.case_id for item in trajectories)
    return min((counts.get(case, 0) for case in cases), default=0)


def _identity_components(trajectories: Sequence[Trajectory]) -> dict[str, list[str]]:
    """Every distinct recorded value of each ``RunIdentity`` component, sorted."""
    values: dict[str, set[str]] = defaultdict(set)
    for item in trajectories:
        if item.run_identity is None:
            continue
        for component, value in item.run_identity.model_dump().items():
            if value is not None:
                values[component].add(value)
    return {
        component: sorted(values[component])
        for component in RunIdentity.model_fields
        if values[component]
    }


def _operational_stops(trajectories: Sequence[Trajectory]) -> list[OperationalEpisode]:
    return [
        OperationalEpisode(
            case_id=item.case_id,
            repeat=item.repeat,
            language=item.language,
            reason=item.operational_reason,
        )
        for item in sorted(
            trajectories, key=lambda item: (item.language, item.case_id, item.repeat)
        )
        if item.operational_reason is not None
    ]


def _target_exceptions(trajectories: Sequence[Trajectory]) -> list[TargetExceptionEpisode]:
    return [
        TargetExceptionEpisode(case_id=item.case_id, repeat=item.repeat, language=item.language)
        for item in sorted(
            trajectories, key=lambda item: (item.language, item.case_id, item.repeat)
        )
        if item.target_exception
    ]


def _macro(values: Iterable[float | None]) -> float | None:
    """Mean over groups; unknown when any group is unknown."""
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return mean(value for value in collected if value is not None)


class ObjectiveTerms(NamedTuple):
    """The objective and its terms over a set of language summaries."""

    macro_verified_accuracy: float
    worst_language_verified_accuracy: float
    macro_reward: float
    objective_j: float


def objective_terms(languages: Mapping[str, GroupSummary]) -> ObjectiveTerms:
    """J = macro reward + ``WORST_LANGUAGE_WEIGHT`` x worst language verified accuracy.

    Means over ``languages``; a language with unknown accuracy or reward counts as 0.
    """
    if not languages:
        raise ValueError("the objective needs at least one language")
    accuracy = [summary.verified_accuracy or 0.0 for summary in languages.values()]
    rewards = [summary.mean_reward or 0.0 for summary in languages.values()]
    macro_reward = mean(rewards)
    worst = min(accuracy)
    return ObjectiveTerms(
        macro_verified_accuracy=mean(accuracy),
        worst_language_verified_accuracy=worst,
        macro_reward=macro_reward,
        objective_j=macro_reward + WORST_LANGUAGE_WEIGHT * worst,
    )


def build_scorecard(
    trajectories: Sequence[Trajectory],
    *,
    run: RunContext,
    dataset_digest: Digest,
    cases: Mapping[str, str],
    budgets: Budgets | None = None,
    sliced: bool = False,
) -> Scorecard:
    """Aggregate trajectories; ``cases`` maps every dataset case to its recipe kind."""
    if not trajectories:
        raise ValueError("a scorecard needs at least one scored row")
    languages = _grouped(trajectories, "language")
    terms = objective_terms(languages)
    models: dict[str, set[str]] = defaultdict(set)
    for item in trajectories:
        for role, model in item.models.items():
            models[role].add(model)
    missing = set(cases) - {item.case_id for item in trajectories}
    return Scorecard(
        run=run,
        dataset_digest=dataset_digest,
        identity_digests=sorted(
            {item.identity["config"] for item in trajectories if item.identity.get("config")}
        ),
        budgets_digest=None if budgets is None else budgets_digest(budgets),
        models={role: sorted(names) for role, names in sorted(models.items())},
        repeats=_repeats(trajectories, cases),
        sliced=sliced or bool(missing),
        kinds=_grouped(trajectories, "kind"),
        languages=languages,
        macro_verified_accuracy=terms.macro_verified_accuracy,
        worst_language_verified_accuracy=terms.worst_language_verified_accuracy,
        macro_reward=terms.macro_reward,
        objective_j=terms.objective_j,
        macro_effective_tokens=_macro(
            summary.mean_effective_tokens for summary in languages.values()
        ),
        macro_p50_seconds=_macro(summary.p50_seconds for summary in languages.values()),
        macro_sandbox_cpu_seconds=_macro(
            summary.mean_sandbox_cpu_seconds for summary in languages.values()
        ),
        sandbox_cpu_unknown=sum(item.sandbox_cpu_seconds is None for item in trajectories),
        macro_thought_share=_macro(summary.mean_thought_share for summary in languages.values()),
        capped_call_episodes=_known_total(
            summary.capped_call_episodes for summary in languages.values()
        ),
        reasoning_cap_exhausted=_known_total(
            summary.reasoning_cap_exhausted for summary in languages.values()
        ),
        run_identity=_identity_components(trajectories),
        operational_episodes=sum(item.operational for item in trajectories),
        operational_stops=_operational_stops(trajectories),
        target_exception_episodes=sum(item.target_exception for item in trajectories),
        target_exceptions=_target_exceptions(trajectories),
    )


def _row_repeats(rows: Sequence[Mapping[str, Any]]) -> list[int]:
    """A row's explicit repeat, else its ordinal among the case's rows (as ``compare`` joins)."""
    seen: Counter[str] = Counter()
    repeats = []
    for row in rows:
        case_id = str(row.get("case_id"))
        explicit = row.get("repeat")
        repeats.append(explicit if isinstance(explicit, int) and explicit >= 0 else seen[case_id])
        seen[case_id] += 1
    return repeats


def score_report(
    report: Mapping[str, Any],
    dataset_path: Path,
    results: Mapping[str, InvestigationResult | None],
    *,
    run: RunContext,
    budgets: Budgets | None = None,
    sliced: bool = False,
    manifest_root: Path | None = None,
) -> tuple[list[Trajectory], Scorecard]:
    """Score a saved report against its frozen dataset; ``results`` is keyed by run id.

    ``results`` from ``load_results`` also name the target-side exception and sandbox
    fault runs; a plain mapping names none, so every ``ERROR`` keeps its operational reward
    and every recorded role ``ERROR`` stays behavioural. ``manifest_root`` resolves the
    entries of a manifest copied out of its evaluation tree (a run's pinned copy).
    """
    return score_loaded_report(
        report,
        load_dataset(dataset_path, root=manifest_root),
        results,
        run=run,
        budgets=budgets,
        sliced=sliced,
    )


def score_loaded_report(
    report: Mapping[str, Any],
    loaded: LoadedDataset,
    results: Mapping[str, InvestigationResult | None],
    *,
    run: RunContext,
    budgets: Budgets | None = None,
    sliced: bool = False,
) -> tuple[list[Trajectory], Scorecard]:
    """``score_report`` over a dataset already loaded, as a gym run loads it at admission."""
    dataset, requests, oracles = loaded
    dataset_digest = digest(dataset)
    if report.get("dataset_digest") != dataset_digest:
        raise ValueError("report dataset digest differs from the frozen dataset manifest")
    kinds = {request.case.case_id: request.case.recipe.kind for request in requests}
    # The per-call output cap each case ran under; results and manifests do not carry
    # the budget, but the frozen request does and ``request_digest`` binds it.
    caps = {request.case.case_id: request.budget.max_output_tokens for request in requests}
    stored = isinstance(results, StoredResults)
    targets = results.target_exceptions if stored else frozenset()
    faults = results.sandbox_faults if stored else frozenset()
    rows = [row for row in report.get("rows", []) if isinstance(row, Mapping)]
    unknown = sorted({str(row.get("case_id")) for row in rows} - set(kinds))
    if unknown:
        raise ValueError(f"report rows name cases outside the dataset: {', '.join(unknown)}")
    trajectories = [
        trajectory(
            row,
            repeat,
            kinds[row["case_id"]],
            oracles[row["case_id"]],
            results.get(str(row.get("run_id"))),
            budgets,
            git_commit=run.git_commit,
            output_cap=caps[row["case_id"]],
            target_exception=str(row.get("run_id")) in targets,
            sandbox_fault=str(row.get("run_id")) in faults,
        )
        for row, repeat in zip(rows, _row_repeats(rows), strict=True)
    ]
    card = build_scorecard(
        trajectories,
        run=run,
        dataset_digest=dataset_digest,
        cases=kinds,
        budgets=budgets,
        sliced=sliced,
    )
    return trajectories, card


class StoredResults(dict[str, InvestigationResult | None]):
    """Each run's committed result by run id, and the runs whose stored raw receipts show
    a terminal ``ERROR`` as a target-side exception (``target_exception``) or a recorded
    role ``ERROR`` as a sandbox fault (``sandbox_fault``)."""

    def __init__(
        self,
        results: Mapping[str, InvestigationResult | None],
        target_exceptions: Iterable[str] = (),
        sandbox_faults: Iterable[str] = (),
    ):
        super().__init__(results)
        self.target_exceptions = frozenset(target_exceptions)
        self.sandbox_faults = frozenset(sandbox_faults)


def load_results(store: ArtifactStore, run_ids: Iterable[str]) -> StoredResults:
    """Each run's committed result receipt, or None when it is unavailable."""
    results: dict[str, InvestigationResult | None] = {}
    for run_id in run_ids:
        try:
            ref = store.reconcile(f"result.{run_id}")
            results[run_id] = (
                None if ref is None else InvestigationResult.model_validate(store.get_json(ref))
            )
        except (OSError, ValueError):
            results[run_id] = None
    return StoredResults(
        results,
        (run_id for run_id, result in results.items() if target_exception(store, result)),
        (run_id for run_id, result in results.items() if sandbox_fault(store, result)),
    )


def write_trajectories(path: Path, trajectories: Iterable[Trajectory]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(item.model_dump_json() + "\n" for item in trajectories))


def read_trajectories(path: Path) -> list[Trajectory]:
    return [Trajectory.model_validate_json(line) for line in path.read_text().splitlines() if line]


def write_scorecard(path: Path, scorecard: Scorecard) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scorecard.model_dump(mode="json"), indent=2) + "\n")


def read_scorecard(path: Path) -> Scorecard:
    return Scorecard.model_validate_json(path.read_bytes())
