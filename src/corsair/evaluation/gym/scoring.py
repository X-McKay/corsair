"""Score a saved evaluation report into per-repeat trajectories and one scorecard.

Pure functions over a report (``{rows, summary, dataset_digest}``), its frozen dataset
manifest (the only source of expected labels; rows never echo an oracle) and each row's
stored ``InvestigationResult``. Rows are produced by ``corsair.evaluation.scoring.score``;
this module adds the reward decomposition and the per-kind and per-language aggregates.
Unknown usage stays unknown: it earns no efficiency bonus and is never counted as zero.
"""

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Digest,
    GroupSummary,
    InvestigationResult,
    Oracle,
    RoleObservation,
    RoundResult,
    RoundSummary,
    RunContext,
    Scorecard,
    Trajectory,
    Usage,
    Verdict,
    digest,
)
from corsair.contracts.gym import Budgets
from corsair.evaluation.comparison import row_stop
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.budgets import budgets_digest
from corsair.evaluation.ledger import row_ledger
from corsair.policies.verdicts import candidate_key

DEMONSTRATED = frozenset({Verdict.EXPLOIT_DEMONSTRATED, Verdict.COMPONENT_EXPLOIT_DEMONSTRATED})
DECISIVE = DEMONSTRATED | {Verdict.EXPLOIT_NOT_DEMONSTRATED}
_OPERATIONAL_VERDICTS = frozenset({Verdict.ERROR, Verdict.UNABLE_TO_RUN})
_OPERATIONAL_STATUSES = frozenset({"ERROR", "BLOCKED", "CANCELLED"})
# Ledger gates that cost a shaping penalty each: a request too large to send, or a
# response cut off at the output cap.
SHAPED_GATES = frozenset({"packet_too_large", "provider_max_tokens"})

REWARD_VERIFIED = 1.0
REWARD_UNRESOLVED = 0.0
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


def verdict_reward(passed: bool, verified: bool, false_label: bool, operational: bool) -> float:
    """The complete reward table, in precedence order."""
    if passed and verified:
        return REWARD_VERIFIED
    if false_label:
        return REWARD_FALSE_LABEL
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


def trajectory(
    row: Mapping[str, Any],
    repeat: int,
    kind: str,
    oracle: Oracle,
    result: InvestigationResult | None,
    budgets: Budgets | None,
    *,
    git_commit: str | None = None,
) -> Trajectory:
    """Score one report row; ``result`` is its stored result, or None when unavailable."""
    status = row.get("status")
    status = status if status in {"pass", "fail"} else "unavailable"
    verdict = _verdict(row.get("verdict"))
    passed = status == "pass"
    verified = passed and (verdict in DECISIVE or not expects_decisive(oracle))
    false_label = _false_label(row, oracle, verdict)
    r_verdict = verdict_reward(passed, verified, false_label, _operational(row, verdict))
    stops = _round_stops(row)
    rounds = [
        round_summary(item, stops.get((item.session, item.index)))
        for item in (result.rounds if result is not None else [])
    ]
    usages = _usages(result)
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
        failure_stop=None if passed else row_stop(dict(row)),
        rounds=rounds,
        llm_calls=_int_or_none(row.get("llm_calls")),
        tool_calls=_int_or_none(row.get("tool_calls")),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        thought_tokens=_int_or_none(
            _known_sum(getattr(usage, "thought_tokens", None) for usage in usages)
        ),
        agent_seconds=agent_seconds,
        sandbox_wall_seconds=_float_or_none(
            _known_sum(item.sandbox_wall_seconds for item in rounds)
        ),
        sandbox_cpu_seconds=_float_or_none(_known_sum(item.sandbox_cpu_seconds for item in rounds)),
        sandbox_host_seconds=_float_or_none(host),
        model_calls=_call_details(usages, "model_calls"),
        tool_calls_detail=_call_details(usages, "tool_calls_detail"),
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


def _fraction(flags: Sequence[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _majority_verified(repeats: Sequence[Trajectory]) -> bool:
    return 2 * sum(item.verified for item in repeats) > len(repeats)


def group_summary(trajectories: Sequence[Trajectory]) -> GroupSummary:
    """Case-level majority accuracy; reward and tokens are means over repeats, then cases."""
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
        verified_accuracy=_fraction([_majority_verified(case) for case in cases]),
        mean_reward=mean(mean(item.reward for item in case) for case in cases) if cases else None,
        mean_effective_tokens=_known_mean(
            _known_mean(item.effective_tokens for item in case) for case in cases
        ),
        p95_effective_tokens=percentile(tokens, 95),
        p50_seconds=percentile(seconds, 50),
        p95_seconds=percentile(seconds, 95),
        failure_stops=dict(sorted(stops.items(), key=lambda item: (-item[1], item[0]))),
        usage_unknown=sum(not item.usage_known for item in trajectories),
    )


def _grouped(trajectories: Sequence[Trajectory], field: str) -> dict[str, GroupSummary]:
    groups: dict[str, list[Trajectory]] = defaultdict(list)
    for item in trajectories:
        groups[getattr(item, field)].append(item)
    return {name: group_summary(groups[name]) for name in sorted(groups)}


def _repeats(trajectories: Sequence[Trajectory], cases: Mapping[str, str]) -> int:
    counts = Counter(item.case_id for item in trajectories)
    return min((counts.get(case, 0) for case in cases), default=0)


def _macro(values: Iterable[float | None]) -> float | None:
    """Mean over groups; unknown when any group is unknown."""
    collected = list(values)
    if not collected or any(value is None for value in collected):
        return None
    return mean(value for value in collected if value is not None)


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
    accuracy = [summary.verified_accuracy or 0.0 for summary in languages.values()]
    rewards = [summary.mean_reward or 0.0 for summary in languages.values()]
    macro_reward = mean(rewards)
    worst = min(accuracy)
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
        macro_verified_accuracy=mean(accuracy),
        worst_language_verified_accuracy=worst,
        macro_reward=macro_reward,
        objective_j=macro_reward + WORST_LANGUAGE_WEIGHT * worst,
        macro_effective_tokens=_macro(
            summary.mean_effective_tokens for summary in languages.values()
        ),
        macro_p50_seconds=_macro(summary.p50_seconds for summary in languages.values()),
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
) -> tuple[list[Trajectory], Scorecard]:
    """Score a saved report against its frozen dataset; ``results`` is keyed by run id."""
    dataset, requests, oracles = load_dataset(dataset_path)
    dataset_digest = digest(dataset)
    if report.get("dataset_digest") != dataset_digest:
        raise ValueError("report dataset digest differs from the frozen dataset manifest")
    kinds = {request.case.case_id: request.case.recipe.kind for request in requests}
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


def load_results(
    store: ArtifactStore, run_ids: Iterable[str]
) -> dict[str, InvestigationResult | None]:
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
    return results


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
