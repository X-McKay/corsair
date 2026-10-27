"""Gym reasoning markers: thought share, calls at the output cap and the dominant call.

The markers are evaluator-side observations only. The tests below pin reward, verified,
objective J and gate results to values computed before the markers existed, and show the
same scores when every per-call report is removed, so no marker feeds a score.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from corsair.contracts import (
    AuditOutput,
    Disposition,
    InvestigationResult,
    KindBudget,
    ModelCall,
    ProducerOutput,
    RoundResult,
    RunContext,
    Scorecard,
    Trajectory,
    Usage,
    Verdict,
    digest,
)
from corsair.contracts.gym import Budgets
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.scoring import build_scorecard, score_report, trajectory

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "evals/datasets/dev.json"
KIND = "python.secret_disclosure/1"
CAP = 12288
BUDGETS = Budgets({KIND: KindBudget(effective_tokens=60_000, seconds=200)})

# (output_tokens, thought_tokens, seconds) per call; the first tuple is the producer's.
Call = tuple[int, int | None, float]
DEMONSTRATED = [(900, 800, 20.0), (300, 250, 5.0)]
EXHAUSTED = [(CAP, CAP, 140.0), (400, 350, 6.0)]
CAPPED_WITH_ANSWER = [(CAP, 12100, 150.0)]
NEGATIVE = [(2000, 1800, 30.0)]
UNREPORTED_THOUGHT: list[Call] = [(700, None, 12.0)]

# (case, status, verdict, ledger gate, calls) in report order; three repeats per case.
EPISODES = [
    ("case01", "pass", "EXPLOIT_DEMONSTRATED", "demonstrated", DEMONSTRATED),
    ("case01", "pass", "EXPLOIT_DEMONSTRATED", "demonstrated", DEMONSTRATED),
    ("case01", "pass", "EXPLOIT_DEMONSTRATED", "demonstrated", DEMONSTRATED),
    ("case02", "fail", "ERROR", "provider_max_tokens", EXHAUSTED),
    ("case02", "pass", "INCONCLUSIVE", "audit_reject", CAPPED_WITH_ANSWER),
    ("case02", "pass", "EXPLOIT_NOT_DEMONSTRATED", "clean_negative", NEGATIVE),
    ("case03", "pass", "COMPONENT_EXPLOIT_DEMONSTRATED", "component_demonstrated", DEMONSTRATED),
    ("case03", "pass", "COMPONENT_EXPLOIT_DEMONSTRATED", "component_demonstrated", DEMONSTRATED),
    (
        "case03",
        "pass",
        "COMPONENT_EXPLOIT_DEMONSTRATED",
        "component_demonstrated",
        UNREPORTED_THOUGHT,
    ),
]


def _usage(calls: Sequence[Call], *, detail: bool = True) -> Usage:
    thoughts = [thought for _, thought, _ in calls if thought is not None]
    return Usage(
        llm_calls=len(calls),
        input_tokens=1000 * len(calls),
        output_tokens=sum(output for output, _, _ in calls),
        seconds=sum(seconds for _, _, seconds in calls),
        thought_tokens=sum(thoughts) if thoughts and detail else None,
        model_calls=[
            ModelCall(
                index=index,
                input_tokens=1000,
                output_tokens=output,
                thought_tokens=thought,
                seconds=seconds,
            )
            for index, (output, thought, seconds) in enumerate(calls, start=1)
        ]
        if detail
        else [],
    )


def _result(
    run_id: str, case_id: str, calls: Sequence[Call], *, detail: bool
) -> InvestigationResult:
    producer, audit = calls[:1], calls[1:]
    return InvestigationResult(
        run_id=run_id,
        case_id=case_id,
        disposition=Disposition.SUPPORTED,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
        execution_status="COMPLETED",
        reason="recorded",
        rounds=[
            RoundResult(
                index=1,
                producer=ProducerOutput(usage=_usage(producer, detail=detail)),
                audit=AuditOutput(usage=_usage(audit, detail=detail)) if audit else None,
            )
        ],
    )


def _report(
    *, failing: frozenset[str] = frozenset(), detail: bool = True
) -> tuple[dict, dict[str, InvestigationResult | None]]:
    """The fixture report and its stored results; ``failing`` cases become unresolved."""
    rows, results = [], {}
    for ordinal, (case, status, verdict, gate_name, calls) in enumerate(EPISODES):
        run_id = f"run-{ordinal}"
        if case in failing:
            status, verdict, gate_name = "fail", "INCONCLUSIVE", "coverage"
        rows.append(
            {
                "run_id": run_id,
                "case_id": case,
                "status": status,
                "verdict": verdict,
                "disposition": "SUPPORTED",
                "execution_status": "ERROR" if verdict == "ERROR" else "COMPLETED",
                "verdict_allowed": status == "pass",
                "forbidden_label": False,
                "llm_calls": len(calls),
                "tool_calls": 0,
                "input_tokens": 1000 * len(calls),
                "output_tokens": sum(output for output, _, _ in calls),
                "agent_seconds": sum(seconds for _, _, seconds in calls),
                "config_digest": "2" * 64,
                "reason": "recorded",
                "gate_ledger": [
                    {"session": 1, "round": 1, "stage": "kernel", "gate": gate_name, "reason": ""}
                ],
            }
        )
        results[run_id] = _result(run_id, case, calls, detail=detail)
    dataset, _, _ = load_dataset(DATASET)
    return {"rows": rows, "summary": {}, "dataset_digest": digest(dataset)}, results


def _score(
    run_id: str, *, failing: frozenset[str] = frozenset(), detail: bool = True
) -> tuple[list[Trajectory], Scorecard]:
    report, results = _report(failing=failing, detail=detail)
    return score_report(report, DATASET, results, run=RunContext(run_id=run_id), budgets=BUDGETS)


# Computed by this file's fixture on the scoring code before the reasoning markers existed.
GOLDEN_REWARDS = [
    1.1744743799301305,
    1.1744743799301305,
    1.1744743799301305,
    -0.55,
    1.0665738274191774,
    1.1681059229635895,
    1.1744743799301305,
    1.1744743799301305,
    1.1876946878085626,
]
GOLDEN_VERIFIED = [True, True, True, False, True, True, True, True, True]
GOLDEN_EFFECTIVE_TOKENS = [6800.0] * 3 + [52752.0, 50152.0, 9000.0, 6800.0, 6800.0, 3800.0]
GOLDEN_SECONDS = [25.0] * 3 + [146.0, 150.0, 30.0, 25.0, 25.0, 12.0]
GOLDEN_CANDIDATE = {
    "objective_j": 1.4716384819824424,
    "macro_reward": 0.9716384819824424,
    "macro_verified_accuracy": 1.0,
    "worst_language_verified_accuracy": 1.0,
    "macro_effective_tokens": 16633.777777777777,
    "macro_p50_seconds": 25.0,
}
GOLDEN_GATE = {
    "decision": "ACCEPTED",
    "reasons": [],
    "delta_j": 0.5596270497409803,
    "token_ratio": 1.0,
    "language_deltas": {"python": 0.33333333333333337},
}


def _legacy(card: Scorecard) -> dict:
    """The scorecard as the pre-marker schema had it: every new field removed."""
    data = card.model_dump(mode="json")
    for name in ("macro_thought_share", "capped_call_episodes", "reasoning_cap_exhausted"):
        data.pop(name, None)
    for groups in (data["kinds"], data["languages"]):
        for summary in groups.values():
            for name in ("mean_thought_share", "capped_call_episodes", "reasoning_cap_exhausted"):
                summary.pop(name, None)
    return data


def test_reward_verified_objective_and_gate_match_the_pre_marker_scores():
    trajectories, card = _score("cand")
    _, baseline = _score("base", failing=frozenset({"case03"}))
    assert [item.reward for item in trajectories] == pytest.approx(GOLDEN_REWARDS)
    assert [item.verified for item in trajectories] == GOLDEN_VERIFIED
    assert [item.effective_tokens for item in trajectories] == GOLDEN_EFFECTIVE_TOKENS
    assert [item.seconds for item in trajectories] == GOLDEN_SECONDS
    for name, value in GOLDEN_CANDIDATE.items():
        assert getattr(card, name) == pytest.approx(value), name
    verdict = gate(baseline, card)
    assert verdict.decision.value == GOLDEN_GATE["decision"]
    assert verdict.reasons == GOLDEN_GATE["reasons"]
    assert verdict.delta_j == pytest.approx(GOLDEN_GATE["delta_j"])
    assert verdict.token_ratio == pytest.approx(GOLDEN_GATE["token_ratio"])
    assert verdict.language_deltas == pytest.approx(GOLDEN_GATE["language_deltas"])


def test_removing_every_per_call_report_changes_no_score():
    with_detail, card = _score("cand")
    without, blind = _score("cand", detail=False)
    assert _legacy(card) == _legacy(blind)
    _, baseline = _score("base", failing=frozenset({"case03"}))
    assert gate(baseline, card) == gate(baseline, blind)
    for full, bare in zip(with_detail, without, strict=True):
        assert (full.reward, full.verified, full.passed, full.effective_tokens) == (
            bare.reward,
            bare.verified,
            bare.passed,
            bare.effective_tokens,
        )
    assert blind.capped_call_episodes is None
    assert blind.macro_thought_share is None
    assert card.capped_call_episodes == 2


def test_an_episode_that_spends_the_whole_cap_on_reasoning_is_marked():
    trajectories, _ = _score("cand")
    exhausted, capped, negative = trajectories[3:6]
    assert exhausted.output_cap == CAP
    assert exhausted.capped_calls == 1
    assert exhausted.reasoning_cap_exhausted is True
    assert exhausted.thought_tokens == CAP + 350
    assert exhausted.thought_share == pytest.approx((CAP + 350) / (CAP + 400))
    dominant = exhausted.dominant_call
    assert dominant is not None
    assert (dominant.position, dominant.index, dominant.output_tokens, dominant.seconds) == (
        1,
        1,
        CAP,
        140.0,
    )
    assert capped.capped_calls == 1
    assert capped.reasoning_cap_exhausted is False
    assert negative.capped_calls == 0
    assert negative.reasoning_cap_exhausted is False


def test_unreported_thought_tokens_stay_unknown():
    trajectories, _ = _score("cand")
    unreported = trajectories[8]
    assert unreported.thought_tokens is None
    assert unreported.thought_share is None
    assert unreported.capped_calls == 0


def test_markers_are_unknown_without_a_cap_or_per_call_reports():
    row = _report()[0]["rows"][3]
    result = _report()[1]["run-3"]
    oracle = load_dataset(DATASET)[2]["case02"]
    uncapped = trajectory(row, 0, KIND, oracle, result, None)
    assert uncapped.output_cap is None
    assert uncapped.capped_calls is None
    assert uncapped.reasoning_cap_exhausted is None
    assert uncapped.dominant_call is not None
    assert uncapped.thought_share is not None
    missing = trajectory(row, 0, KIND, oracle, None, None, output_cap=CAP)
    assert missing.output_cap == CAP
    assert (missing.capped_calls, missing.reasoning_cap_exhausted) == (None, None)
    assert (missing.dominant_call, missing.thought_tokens, missing.thought_share) == (
        None,
        None,
        None,
    )


def test_the_largest_call_wins_and_the_first_one_wins_a_tie():
    calls = [(500, 400, 1.0), (CAP, CAP, 140.0), (CAP, 100, 150.0)]
    result = _result("tie", "case02", calls, detail=True)
    row = _report()[0]["rows"][3]
    oracle = load_dataset(DATASET)[2]["case02"]
    scored = trajectory(row, 0, KIND, oracle, result, None, output_cap=CAP)
    assert scored.capped_calls == 2
    assert scored.reasoning_cap_exhausted is True
    dominant = scored.dominant_call
    assert dominant is not None
    assert (dominant.position, dominant.index, dominant.seconds) == (2, 1, 140.0)


def test_groups_and_scorecard_count_capped_episodes_and_mean_thought_share():
    trajectories, card = _score("cand")
    python = card.languages["python"]
    kind = card.kinds[KIND]
    assert python.capped_call_episodes == kind.capped_call_episodes == 2
    assert python.reasoning_cap_exhausted == kind.reasoning_cap_exhausted == 1
    by_case: dict[str, list[float]] = {}
    for item in trajectories:
        if item.thought_share is not None:
            by_case.setdefault(item.case_id, []).append(item.thought_share)
    expected = sum(sum(shares) / len(shares) for shares in by_case.values()) / len(by_case)
    assert python.mean_thought_share == pytest.approx(expected)
    assert card.macro_thought_share == pytest.approx(expected)
    assert card.capped_call_episodes == 2
    assert card.reasoning_cap_exhausted == 1


def test_a_group_without_any_cap_reports_unknown_capped_counts():
    rows = [
        Trajectory(
            run_id="r",
            case_id="a",
            repeat=0,
            kind="ruby.k/1",
            language="ruby",
            status="pass",
            passed=True,
            verified=True,
            false_label=False,
            usage_known=True,
            effective_tokens=10.0,
            seconds=1.0,
            reward_verdict=1.0,
            reward=1.0,
        )
    ]
    card = build_scorecard(
        rows, run=RunContext(run_id="r"), dataset_digest="d" * 64, cases={"a": "ruby.k/1"}
    )
    ruby = card.languages["ruby"]
    assert (ruby.capped_call_episodes, ruby.reasoning_cap_exhausted) == (None, None)
    assert ruby.mean_thought_share is None
    assert (card.capped_call_episodes, card.reasoning_cap_exhausted) == (None, None)
    assert card.macro_thought_share is None
