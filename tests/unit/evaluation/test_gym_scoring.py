"""Gym scoring: reward table, efficiency bonus, shaping and majority-of-repeats aggregation."""

import json
import math
from pathlib import Path

import pytest

from corsair.contracts import (
    Disposition,
    InvestigationResult,
    KindBudget,
    Oracle,
    ProducerDecision,
    ProducerOutput,
    RoundResult,
    RunContext,
    Trajectory,
    Verdict,
    digest,
)
from corsair.contracts.gym import Budgets
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.scoring import (
    build_scorecard,
    effective_tokens,
    read_trajectories,
    score_report,
    trajectory,
    write_trajectories,
)
from tests.unit.test_evidence import _submission

ROOT = Path(__file__).resolve().parents[3]
KIND = "python.secret_disclosure/1"
DECISIVE = Oracle(
    acceptable=[Disposition.SUPPORTED, Disposition.INCONCLUSIVE],
    expected_verdict=Verdict.EXPLOIT_DEMONSTRATED,
)
ABSTAIN = Oracle(
    acceptable=[Disposition.INCONCLUSIVE],
    acceptable_verdicts=[Verdict.INCONCLUSIVE, Verdict.EXPLOIT_NOT_DEMONSTRATED],
    forbidden_verdicts=[Verdict.EXPLOIT_DEMONSTRATED],
)
BUDGETS = Budgets({KIND: KindBudget(effective_tokens=10_000, seconds=100)})


def _row(**update) -> dict:
    row = {
        "run_id": "run-1",
        "case_id": "case01",
        "status": "pass",
        "disposition": "SUPPORTED",
        "verdict": "EXPLOIT_DEMONSTRATED",
        "execution_status": "COMPLETED",
        "evidence_valid": True,
        "fix_correct": True,
        "verdict_allowed": True,
        "forbidden_label": False,
        "correctly_resolved": True,
        "llm_calls": 3,
        "tool_calls": 2,
        "input_tokens": 1000,
        "output_tokens": 100,
        "agent_seconds": 50.0,
        "config_digest": "2" * 64,
        "reason": "demonstrated",
        "gate_ledger": [
            {"session": 1, "round": 1, "stage": "kernel", "gate": "demonstrated", "reason": "x"}
        ],
    }
    row.update(update)
    return row


def _score(row: dict, oracle: Oracle = DECISIVE, result=None, budgets=BUDGETS) -> Trajectory:
    return trajectory(row, 0, KIND, oracle, result, budgets, git_commit="abc1234")


def test_correct_but_inconclusive_on_a_decisive_expected_case_scores_zero():
    row = _row(
        status="fail",
        verdict="INCONCLUSIVE",
        disposition="INCONCLUSIVE",
        verdict_allowed=False,
        correctly_resolved=False,
    )
    scored = _score(row)
    assert scored.passed is False
    assert scored.verified is False
    assert scored.false_label is False
    assert scored.reward_verdict == 0.0
    assert scored.reward == 0.0


def test_a_passed_abstention_the_oracle_accepts_scores_as_verified():
    row = _row(verdict="INCONCLUSIVE", disposition="INCONCLUSIVE", correctly_resolved=False)
    scored = _score(row, ABSTAIN)
    assert scored.passed is True
    assert scored.verified is True
    assert scored.reward_verdict == 1.0


def test_unknown_usage_earns_no_efficiency_bonus():
    scored = _score(_row(input_tokens=None, agent_seconds=None))
    assert scored.usage_known is False
    assert scored.effective_tokens is None
    assert scored.seconds is None
    assert (scored.phi_tokens, scored.phi_time) == (0.0, 0.0)
    assert scored.reward == 1.0


def test_known_usage_adds_the_clamped_efficiency_bonus():
    scored = _score(_row())
    expected_tokens = 1000 + 4 * 100
    phi_tok = 1 - math.log1p(expected_tokens) / math.log1p(10_000)
    phi_time = 1 - 50.0 / 100
    assert scored.usage_known is True
    assert scored.effective_tokens == expected_tokens
    assert scored.phi_tokens == pytest.approx(phi_tok)
    assert scored.phi_time == pytest.approx(min(0.5, phi_time))
    assert scored.reward == pytest.approx(1.0 + 0.25 * phi_tok + 0.25 * min(0.5, phi_time))


def test_the_bonus_is_clamped_and_absent_without_a_budget_for_the_kind():
    slow = _score(_row(agent_seconds=1000.0))
    assert slow.phi_time == -0.5
    unbudgeted = _score(_row(), budgets=None)
    assert (unbudgeted.phi_tokens, unbudgeted.phi_time) == (0.0, 0.0)
    assert unbudgeted.usage_known is True


def test_a_failed_row_never_earns_an_efficiency_bonus():
    row = _row(status="fail", verdict_allowed=False, verdict="INCONCLUSIVE")
    scored = _score(row)
    assert (scored.phi_tokens, scored.phi_time) == (0.0, 0.0)


def test_cached_tokens_are_discounted_only_when_reported():
    assert effective_tokens(1000, 100, None) == 1400
    assert effective_tokens(1000, 100, 800) == pytest.approx(200 + 80 + 400)
    assert effective_tokens(None, 100, None) is None


@pytest.mark.parametrize(
    ("update", "reward"),
    [
        ({"status": "fail", "verdict": "ERROR", "execution_status": "ERROR"}, -0.5),
        ({"status": "fail", "verdict": "UNABLE_TO_RUN", "execution_status": "BLOCKED"}, -0.5),
        ({"status": "fail", "forbidden_label": True}, -1.0),
        (
            {
                "status": "fail",
                "verdict": "EXPLOIT_NOT_DEMONSTRATED",
                "disposition": "REFUTED",
                "verdict_allowed": False,
            },
            -1.0,
        ),
    ],
)
def test_operational_and_false_labels_are_penalised(update, reward):
    scored = _score(_row(**update))
    assert scored.reward_verdict == reward
    assert scored.false_label is (reward == -1.0)


def test_an_unavailable_result_is_an_operational_failure():
    row = {"run_id": "run-1", "case_id": "case01", "status": "unavailable", "reason": "missing"}
    scored = _score(row)
    assert scored.status == "unavailable"
    assert scored.reward_verdict == -0.5
    assert scored.usage_known is False


def _proposal(exploit: str) -> ProducerOutput:
    submission = _submission().model_copy(update={"exploit_payload": exploit})
    return ProducerOutput(decision=ProducerDecision(kind="proposal", submission=submission))


def test_shaping_charges_repeated_candidates_and_oversized_or_truncated_requests():
    result = InvestigationResult(
        run_id="run-1",
        case_id="case01",
        disposition=Disposition.SUPPORTED,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
        execution_status="COMPLETED",
        reason="demonstrated",
        rounds=[
            RoundResult(index=1, producer=_proposal("../a")),
            RoundResult(index=2, producer=_proposal("../a")),
            RoundResult(index=3, producer=_proposal("../b")),
        ],
    )
    ledger = [
        {"session": 1, "round": 1, "stage": "producer", "gate": "packet_too_large", "reason": ""},
        {"session": 1, "round": 2, "stage": "audit", "gate": "provider_max_tokens", "reason": ""},
        {"session": 1, "round": 3, "stage": "kernel", "gate": "demonstrated", "reason": ""},
    ]
    scored = _score(_row(gate_ledger=ledger), result=result, budgets=None)
    assert scored.shaping == pytest.approx(-0.15)
    assert scored.reward == pytest.approx(0.85)
    assert [item.stop for item in scored.rounds] == [
        "packet_too_large",
        "provider_max_tokens",
        "demonstrated",
    ]
    assert scored.rounds[0].payload_identity == scored.rounds[1].payload_identity
    assert scored.rounds[2].exploit_payload == "../b"


def test_a_stored_unverified_stop_is_named_by_its_recorded_failing_role():
    """A report saved before qualified labels re-scores under the role's recorded cause;
    rewards, shaping and every other stop are unchanged."""
    from tests.unit.test_gate_ledger import _UNCOVERED
    from tests.unit.test_verdicts import _VIOLATION, _observation

    uncovered = _observation(_UNCOVERED, _VIOLATION)
    result = InvestigationResult(
        run_id="run-1",
        case_id="case01",
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.INCONCLUSIVE,
        execution_status="COMPLETED",
        reason="probe evidence was invalid",
        rounds=[
            RoundResult(index=1, producer=_proposal("../a"), observation=uncovered),
            RoundResult(index=2, producer=_proposal("../b"), observation=uncovered),
        ],
    )
    ledger = [
        {"session": 1, "round": 1, "stage": "kernel", "gate": "evidence_unverified", "reason": ""},
        {"session": 1, "round": 2, "stage": "kernel", "gate": "evidence_unverified", "reason": ""},
    ]
    row = _row(
        status="fail",
        verdict="INCONCLUSIVE",
        disposition="INCONCLUSIVE",
        verdict_allowed=False,
        correctly_resolved=False,
        gate_ledger=ledger,
    )
    scored = _score(row, result=result)
    unscored = _score(row)
    assert scored.failure_stop == "evidence_unverified:coverage_control"
    assert [item.stop for item in scored.rounds] == ["evidence_unverified:coverage_control"] * 2
    # Without a stored result nothing is re-derived: the stored label stands.
    assert unscored.failure_stop == "evidence_unverified"
    assert (scored.reward_verdict, scored.shaping, scored.reward) == (0.0, 0.0, 0.0)
    assert row["gate_ledger"] == ledger
    card = build_scorecard(
        [scored], run=_context(), dataset_digest="d" * 64, cases={"case01": KIND}
    )
    assert card.languages["python"].failure_stops == {"evidence_unverified:coverage_control": 1}
    assert card.kinds[KIND].failure_stops == {"evidence_unverified:coverage_control": 1}


def _trajectory(case: str, language: str, verified: bool, *, reward=None, tokens=100.0):
    return Trajectory(
        run_id=f"run-{case}",
        case_id=case,
        repeat=0,
        kind=f"{language}.kind/1",
        language=language,
        status="pass" if verified else "fail",
        passed=verified,
        verified=verified,
        false_label=False,
        failure_stop=None if verified else "coverage",
        usage_known=True,
        effective_tokens=tokens,
        seconds=10.0,
        reward_verdict=1.0 if verified else 0.0,
        reward=(1.0 if verified else 0.0) if reward is None else reward,
    )


def _context() -> RunContext:
    return RunContext(run_id="gym-run")


def test_majority_of_three_repeats_absorbs_one_flaky_repeat():
    repeats = [_trajectory("a", "python", flag) for flag in (True, False, True)]
    card = build_scorecard(
        repeats, run=_context(), dataset_digest="d" * 64, cases={"a": "python.kind/1"}
    )
    assert card.languages["python"].verified_accuracy == 1.0
    assert card.languages["python"].raw_accuracy == pytest.approx(2 / 3)
    assert card.languages["python"].mean_reward == pytest.approx(2 / 3)
    assert card.languages["python"].failure_stops == {"coverage": 1}
    assert card.repeats == 3
    two_failed = [_trajectory("a", "python", flag) for flag in (True, False, False)]
    card = build_scorecard(
        two_failed, run=_context(), dataset_digest="d" * 64, cases={"a": "python.kind/1"}
    )
    assert card.languages["python"].verified_accuracy == 0.0


def test_objective_combines_macro_reward_and_the_worst_language():
    rows = [
        _trajectory("a", "python", True),
        _trajectory("b", "python", True),
        _trajectory("c", "ruby", False),
        _trajectory("d", "ruby", True),
    ]
    cases = {"a": "python.kind/1", "b": "python.kind/1", "c": "ruby.kind/1", "d": "ruby.kind/1"}
    card = build_scorecard(rows, run=_context(), dataset_digest="d" * 64, cases=cases)
    assert card.macro_verified_accuracy == pytest.approx(0.75)
    assert card.worst_language_verified_accuracy == pytest.approx(0.5)
    assert card.macro_reward == pytest.approx(0.75)
    assert card.objective_j == pytest.approx(0.75 + 0.5 * 0.5)
    assert card.macro_effective_tokens == pytest.approx(100.0)
    assert card.sliced is False


def test_a_report_missing_dataset_cases_is_sliced():
    card = build_scorecard(
        [_trajectory("a", "python", True)],
        run=_context(),
        dataset_digest="d" * 64,
        cases={"a": "python.kind/1", "b": "python.kind/1"},
    )
    assert card.sliced is True
    assert card.repeats == 0


def _cpu(case: str, language: str, cpu: float | None, repeat: int = 0) -> Trajectory:
    item = _trajectory(case, language, True)
    return item.model_copy(update={"repeat": repeat, "sandbox_cpu_seconds": cpu})


def _cpu_card(figures: dict[tuple[str, str], list[float | None]]):
    rows = [
        _cpu(case, language, cpu, repeat)
        for (case, language), values in figures.items()
        for repeat, cpu in enumerate(values)
    ]
    cases = {case: f"{language}.kind/1" for case, language in figures}
    return build_scorecard(rows, run=_context(), dataset_digest="d" * 64, cases=cases)


def test_macro_sandbox_cpu_seconds_is_the_macro_of_per_case_means():
    card = _cpu_card(
        {
            ("a", "python"): [1.0, 2.0, 3.0],
            ("b", "python"): [4.0, 4.0, 4.0],
            ("c", "ruby"): [6.0, 6.0, 6.0],
        }
    )
    # python: case means 2 and 4, so 3; ruby 6; the macro over languages 4.5.
    assert card.languages["python"].mean_sandbox_cpu_seconds == pytest.approx(3.0)
    assert card.languages["ruby"].mean_sandbox_cpu_seconds == pytest.approx(6.0)
    assert card.macro_sandbox_cpu_seconds == pytest.approx(4.5)
    assert card.languages["python"].sandbox_cpu_unknown == 0
    assert card.sandbox_cpu_unknown == 0
    # Information only: J and its terms do not read it.
    keys = [("a", "python"), ("b", "python"), ("c", "ruby")]
    unknown = _cpu_card({key: [None] * 3 for key in keys})
    assert (card.objective_j, card.macro_reward) == (unknown.objective_j, unknown.macro_reward)


def test_an_episode_lacking_sandbox_cpu_seconds_leaves_its_case_unknown_and_is_counted():
    card = _cpu_card(
        {
            ("a", "python"): [1.0, None, 3.0],
            ("b", "python"): [4.0, 4.0, 4.0],
            ("c", "ruby"): [None, None, None],
        }
    )
    # Case a is unknown, never a mean of its known episodes or a zero: python reads case b.
    assert card.languages["python"].mean_sandbox_cpu_seconds == pytest.approx(4.0)
    assert card.languages["python"].sandbox_cpu_unknown == 1
    # Ruby's only case is unknown, so ruby and the macro over languages are unknown.
    assert card.languages["ruby"].mean_sandbox_cpu_seconds is None
    assert card.languages["ruby"].sandbox_cpu_unknown == 3
    assert card.macro_sandbox_cpu_seconds is None
    assert card.sandbox_cpu_unknown == 4
    assert card.kinds["python.kind/1"].sandbox_cpu_unknown == 1


def test_a_scorecard_stored_before_sandbox_cpu_seconds_decodes_with_them_unknown():
    card = _cpu_card({("a", "python"): [1.0, 1.0, 1.0]})
    record = card.model_dump(mode="json")
    for name in ("macro_sandbox_cpu_seconds", "sandbox_cpu_unknown"):
        record.pop(name)
    for summary in [*record["languages"].values(), *record["kinds"].values()]:
        for name in ("mean_sandbox_cpu_seconds", "sandbox_cpu_unknown"):
            summary.pop(name)
    stored = type(card).model_validate(record)
    assert stored.macro_sandbox_cpu_seconds is None and stored.sandbox_cpu_unknown is None
    assert stored.languages["python"].mean_sandbox_cpu_seconds is None
    assert stored.languages["python"].sandbox_cpu_unknown is None


def test_score_report_reads_the_frozen_manifest_and_refuses_another_dataset(tmp_path):
    dataset_path = ROOT / "evals/datasets/dev.json"
    dataset, _, _ = load_dataset(dataset_path)
    rows = [
        {"run_id": f"r-{case}", "case_id": case, "status": "unavailable", "reason": "missing"}
        for case in ("case01", "case02", "case03")
    ]
    report = {"rows": rows, "summary": {}, "dataset_digest": digest(dataset)}
    trajectories, card = score_report(report, dataset_path, {}, run=_context())
    assert [item.case_id for item in trajectories] == ["case01", "case02", "case03"]
    assert {item.language for item in trajectories} == {"python"}
    assert card.dataset_digest == digest(dataset)
    assert card.repeats == 1
    assert card.budgets_digest is None
    with pytest.raises(ValueError, match="dataset digest"):
        score_report({**report, "dataset_digest": "0" * 64}, dataset_path, {}, run=_context())

    path = tmp_path / "trajectories.jsonl"
    write_trajectories(path, trajectories)
    assert read_trajectories(path) == trajectories
    assert all(json.loads(line)["case_id"] for line in path.read_text().splitlines())


# The batch row scorer shared by ``corsair eval`` and ``corsair gym run``


def test_score_batch_scores_receipts_and_keeps_every_unavailable_row_explicit(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import AuditDecision, BatchItem
    from corsair.evaluation.scoring import score, score_batch
    from tests.unit.evaluation.test_gym_capture import CASE, _evals_root, _oracle, _result

    root, _, _ = _evals_root(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    oracle = _oracle(root)
    result = _result(store, "gym-accepted", AuditDecision.ACCEPT)
    ref = store.reconcile("result.gym-accepted")
    items = [
        BatchItem(case_id=CASE, run_id="gym-accepted", artifact=ref),
        BatchItem(case_id=CASE, run_id="gym-lost", error="worker lost"),
        BatchItem(case_id=CASE, run_id="gym-other", artifact=ref),
        BatchItem(case_id="absent", run_id="gym-accepted", artifact=ref),
    ]

    rows = score_batch(items, store, {CASE: oracle})

    assert rows[0] == score(result, oracle, store)
    assert rows[1:] == [
        {"case_id": CASE, "run_id": "gym-lost", "status": "unavailable", "reason": "worker lost"},
        {
            "case_id": CASE,
            "run_id": "gym-other",
            "status": "unavailable",
            "reason": "Child result identity differs from its batch receipt",
        },
        {
            "case_id": "absent",
            "run_id": "gym-accepted",
            "status": "unavailable",
            "reason": "Child result identity differs from its batch receipt",
        },
    ]
