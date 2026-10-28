"""A target-side exception episode scores 0; a harness or sandbox fault keeps -0.5.

The kernel's ``ERROR`` verdict is unchanged. The gym reads the terminal round's stored raw
receipts and names an episode ``target_exception`` only when every role the kernel
admitted as ``ERROR`` completed natively (driver record, junit ``ERROR``,
``observation_kind=execution_error``), covered the bound finding line, had its cleanup
confirmed and recorded no ``error`` or ``driver_error``.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Disposition,
    Finding,
    InvestigationResult,
    Observation,
    OperationalEpisode,
    OperationalReason,
    Oracle,
    PreparedCase,
    ProducerOutput,
    PythonRecipe,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    RunContext,
    RunManifest,
    Scope,
    Scorecard,
    TargetExceptionEpisode,
    Trajectory,
    Verdict,
    digest,
)
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.gate import gate
from corsair.evaluation.gym.render import render_gate, render_scorecard
from corsair.evaluation.gym.scoring import (
    REWARD_OPERATIONAL,
    REWARD_TARGET_EXCEPTION,
    StoredResults,
    load_results,
    sandbox_fault,
    score_report,
    target_exception,
    trajectory,
)

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "evals/datasets/dev.json"
KIND = "python.secret_disclosure/1"
ORACLE = Oracle(
    acceptable=[Disposition.SUPPORTED, Disposition.INCONCLUSIVE],
    expected_verdict=Verdict.EXPLOIT_DEMONSTRATED,
)
OPERATION = "run-1.s1.r1"
LINE = 4
MODULE = "reader.py"
PAYLOAD_ERROR = [
    {"session": 1, "round": 1, "stage": "kernel", "gate": "evidence_unverified", "reason": ""},
    {
        "session": 1,
        "round": None,
        "stage": "policy",
        "gate": "execution_error",
        "reason": "trusted probe execution errored",
    },
]


def _prepared(store: ArtifactStore) -> PreparedCase:
    return PreparedCase(
        case_id="case01",
        finding=Finding(
            title="secret path",
            description="component finding",
            file=MODULE,
            line=LINE,
            claim_scope=Scope.COMPONENT,
        ),
        recipe=PythonRecipe(
            module_file=MODULE,
            function="read_file",
            payload_parameter="path",
            fixed_kwargs={"root": "/fixtures/allowed"},
        ),
        source=store.put(b"source", "application/x-tar"),
        source_excerpt="4: return read(path)",
        manifest=RunManifest(
            package_version="0.1",
            request_digest="1" * 64,
            config_digest="2" * 64,
            producer_prompt_digest="3" * 64,
            auditor_prompt_digest="4" * 64,
            image_id="sha256:trusted",
            models={"producer": "test", "auditor": "test"},
        ),
    )


def _driver(role: str, kind: str | None, status: str, outcome: str) -> dict[str, Any]:
    failed = outcome != "PROPERTY_HELD"
    return {
        "schema_version": "corsair.driver/1",
        "operation_id": OPERATION,
        "role": role,
        "source_digest": "a" * 64,
        "submission_digest": "b" * 64,
        "native_exit_code": 1 if failed else 0,
        "junit": {
            "status": status,
            "tests": 1,
            "failures": 1 if failed else 0,
            "errors": 0,
            "skipped": 0,
        },
        "outcome": outcome,
        "observation_kind": kind,
        "target_executed": not failed,
        "covered_lines": [1, 3, LINE],
        "coverage_file": MODULE,
    }


def _receipt(role: str, **update: Any) -> dict[str, Any]:
    """A completed target-side exception: what the adversarial role recorded in tier1."""
    driver = _driver(role, "execution_error", "ERROR", "ERROR")
    driver.update(update.pop("driver", {}))
    raw = {
        "schema_version": "corsair.raw-evidence/1",
        "operation_id": OPERATION,
        "role": role,
        "container_id": f"id-{role}",
        "labels": {},
        "image_id": "sha256:trusted",
        "docker_exit_code": 1,
        "driver": driver,
        "cleanup_confirmed": True,
        "host_usec": 1000,
    }
    raw.update(update)
    return raw


HELD: dict[str, Any] = {
    "schema_version": "corsair.raw-evidence/1",
    "operation_id": OPERATION,
    "role": "control",
    "cleanup_confirmed": True,
    "driver": _driver("control", "held", "PASS", "PROPERTY_HELD"),
}
# The sandbox adapter's record when no driver record came back (``_raw_error``).
SANDBOX_FAULT: dict[str, Any] = {
    "schema_version": "corsair.raw-evidence/1",
    "operation_id": OPERATION,
    "container_id": "id",
    "labels": {},
    "image_id": "sha256:trusted",
    "docker_exit_code": 2,
    "driver": None,
    "cleanup_confirmed": True,
    "error": "SandboxExecutionError",
}

_ROLE_ERROR = RoleObservation(outcome=RoleOutcome.ERROR, target_executed=False)
_ROLE_HELD = RoleObservation(
    outcome=RoleOutcome.HELD, target_executed=True, covered_lines=[1, 3, LINE]
)


def _stored(
    store: ArtifactStore,
    receipts: Mapping[str, dict[str, Any] | None],
    *,
    outcomes: dict[str, RoleObservation] | None = None,
    verdict: Verdict = Verdict.ERROR,
    run_id: str = "run-1",
) -> InvestigationResult:
    """A stored result whose last round's evidence bundle names ``receipts``."""
    roles = {
        role: None if raw is None else store.put_json(raw).model_dump(mode="json")
        for role, raw in receipts.items()
    }
    bundle = store.put_json(
        {
            "schema_version": "corsair.evidence/1",
            "operation_id": OPERATION,
            "source_digest": "a" * 64,
            "submission_digest": "b" * 64,
            "prepared": store.put_json(_prepared(store)).model_dump(mode="json"),
            "fixed": False,
            "roles": roles,
        }
    )
    outcomes = outcomes or {"control": _ROLE_HELD, "adversarial": _ROLE_ERROR}
    observation = Observation(
        operation_id=OPERATION,
        source_digest="a" * 64,
        submission_digest="b" * 64,
        control=outcomes["control"],
        adversarial=outcomes["adversarial"],
        artifact=bundle,
        cleanup_confirmed=True,
    )
    result = InvestigationResult(
        run_id=run_id,
        case_id="case01",
        disposition=Disposition.INCONCLUSIVE,
        verdict=verdict,
        execution_status="ERROR",
        reason="trusted probe execution errored",
        rounds=[RoundResult(index=1, producer=ProducerOutput(), observation=observation)],
    )
    if store.reconcile(f"result.{run_id}") is None:
        store.commit(f"result.{run_id}", store.put_json(result))
    return result


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "store")


# The receipt rule


def test_a_completed_target_exception_on_the_bound_line_is_named(store):
    result = _stored(store, {"control": HELD, "adversarial": _receipt("adversarial")})
    assert target_exception(store, result) is True


@pytest.mark.parametrize(
    "receipt",
    [
        pytest.param(None, id="missing-receipt"),
        pytest.param({**SANDBOX_FAULT, "role": "adversarial"}, id="sandbox-execution-error"),
        pytest.param(_receipt("adversarial", error="SandboxExecutionError"), id="raw-error"),
        pytest.param(
            _receipt("adversarial", driver={"driver_error": "invalid job"}), id="driver-error"
        ),
        pytest.param(_receipt("adversarial", cleanup_confirmed=False), id="cleanup-unconfirmed"),
        pytest.param(
            _receipt("adversarial", driver={"covered_lines": [1, 3]}), id="bound-line-uncovered"
        ),
        pytest.param(_receipt("adversarial", driver={"covered_lines": None}), id="no-coverage"),
        pytest.param(
            _receipt("adversarial", driver={"coverage_file": "other.py"}), id="other-file"
        ),
        pytest.param(
            _receipt("adversarial", driver={"observation_kind": None}), id="no-observation-kind"
        ),
        pytest.param(
            _receipt("adversarial", driver={"junit": {"status": "INVALID"}}), id="junit-invalid"
        ),
        pytest.param(_receipt("adversarial", driver={"outcome": "INVALID"}), id="driver-invalid"),
        pytest.param(_receipt("adversarial", driver={"role": "control"}), id="driver-role"),
        pytest.param(_receipt("adversarial", operation_id="run-2.s1.r1"), id="stale-receipt"),
        pytest.param(_receipt("control"), id="receipt-of-the-other-role"),
    ],
)
def test_a_harness_or_sandbox_fault_is_not_a_target_exception(store, receipt):
    result = _stored(store, {"control": HELD, "adversarial": receipt})
    assert target_exception(store, result) is False


def test_every_errored_role_must_be_a_target_exception(store):
    both = {"control": _ROLE_ERROR, "adversarial": _ROLE_ERROR}
    fault = {**SANDBOX_FAULT, "role": "control"}
    receipts = {"control": fault, "adversarial": _receipt("adversarial")}
    mixed = _stored(store, receipts, outcomes=both)
    assert target_exception(store, mixed) is False
    pair = {"control": _receipt("control"), "adversarial": _receipt("adversarial")}
    assert target_exception(store, _stored(store, pair, outcomes=both)) is True


def test_only_a_terminal_error_with_an_errored_role_is_considered(store):
    receipts = {"control": HELD, "adversarial": _receipt("adversarial")}
    inconclusive = _stored(store, receipts, verdict=Verdict.INCONCLUSIVE)
    assert target_exception(store, inconclusive) is False
    held = {"control": _ROLE_HELD, "adversarial": _ROLE_HELD}
    assert target_exception(store, _stored(store, receipts, outcomes=held)) is False
    assert target_exception(store, None) is False
    unobserved = _stored(store, receipts).model_copy(
        update={"rounds": [RoundResult(index=1, producer=ProducerOutput())]}
    )
    assert target_exception(store, unobserved) is False


def test_the_rule_reads_the_raw_receipt_not_the_admitted_observation(store):
    # Coverage kept on the admitted observation (after the verifier fix) or discarded
    # (before it) does not change the answer; only the raw receipt decides.
    kept = RoleObservation(outcome=RoleOutcome.ERROR, target_executed=True, covered_lines=[LINE])
    receipts = {"control": HELD, "adversarial": _receipt("adversarial")}
    for adversarial in (_ROLE_ERROR, kept):
        outcomes = {"control": _ROLE_HELD, "adversarial": adversarial}
        assert target_exception(store, _stored(store, receipts, outcomes=outcomes)) is True


def test_load_results_carries_the_target_exception_runs(store):
    _stored(store, {"control": HELD, "adversarial": _receipt("adversarial")}, run_id="run-1")
    _stored(store, {"control": HELD, "adversarial": None}, run_id="run-2")
    loaded = load_results(store, ["run-1", "run-2", "run-3"])
    assert isinstance(loaded, StoredResults)
    assert loaded.target_exceptions == frozenset({"run-1"})
    assert loaded["run-3"] is None
    assert loaded["run-1"] is not None and loaded["run-1"].verdict is Verdict.ERROR


# The sandbox-fault rule: a role ERROR the sandbox, not the payload or target, produced


@pytest.mark.parametrize(
    "receipt",
    [
        pytest.param({**SANDBOX_FAULT, "role": "adversarial"}, id="sandbox-execution-error"),
        pytest.param(None, id="missing-receipt"),
        pytest.param(_receipt("adversarial", operation_id="run-2.s1.r1"), id="stale-receipt"),
        pytest.param(_receipt("control"), id="receipt-of-the-other-role"),
        pytest.param(_receipt("adversarial", driver={"schema_version": "x"}), id="no-driver"),
    ],
)
def test_a_role_error_without_a_driver_record_is_a_sandbox_fault(store, receipt):
    result = _stored(store, {"control": HELD, "adversarial": receipt})
    assert sandbox_fault(store, result) is True
    assert target_exception(store, result) is False


@pytest.mark.parametrize(
    "receipt",
    [
        pytest.param(_receipt("adversarial"), id="target-exception"),
        # A payload-level ERROR: the driver ran and recorded no observation kind.
        pytest.param(
            _receipt("adversarial", driver={"observation_kind": None}), id="payload-error"
        ),
        pytest.param(
            _receipt("adversarial", driver={"driver_error": "invalid job"}), id="driver-error"
        ),
    ],
)
def test_a_role_error_with_a_driver_record_is_not_a_sandbox_fault(store, receipt):
    result = _stored(store, {"control": HELD, "adversarial": receipt})
    assert sandbox_fault(store, result) is False


def test_a_missing_bundle_or_one_faulted_role_is_a_sandbox_fault(store):
    receipts = {"control": HELD, "adversarial": _receipt("adversarial")}
    unbundled = _stored(store, receipts)
    observation = unbundled.rounds[0].observation
    assert observation is not None
    bare = observation.model_copy(update={"artifact": None})
    unbundled = unbundled.model_copy(
        update={"rounds": [unbundled.rounds[0].model_copy(update={"observation": bare})]}
    )
    assert sandbox_fault(store, unbundled) is True
    both = {"control": _ROLE_ERROR, "adversarial": _ROLE_ERROR}
    mixed = {
        "control": {**SANDBOX_FAULT, "role": "control"},
        "adversarial": _receipt("adversarial"),
    }
    assert sandbox_fault(store, _stored(store, mixed, outcomes=both)) is True


def test_only_a_recorded_role_error_is_considered_for_a_sandbox_fault(store):
    held = {"control": _ROLE_HELD, "adversarial": _ROLE_HELD}
    fault = {"control": HELD, "adversarial": {**SANDBOX_FAULT, "role": "adversarial"}}
    assert sandbox_fault(store, _stored(store, fault, outcomes=held)) is False
    assert sandbox_fault(store, None) is False
    unobserved = _stored(store, fault).model_copy(
        update={"rounds": [RoundResult(index=1, producer=ProducerOutput())]}
    )
    assert sandbox_fault(store, unobserved) is False


def test_load_results_carries_the_sandbox_fault_runs(store):
    _stored(store, {"control": HELD, "adversarial": _receipt("adversarial")}, run_id="run-1")
    fault = {"control": HELD, "adversarial": {**SANDBOX_FAULT, "role": "adversarial"}}
    _stored(store, fault, run_id="run-2")
    loaded = load_results(store, ["run-1", "run-2", "run-3"])
    assert loaded.sandbox_faults == frozenset({"run-2"})
    assert loaded.target_exceptions == frozenset({"run-1"})


# The reward


def _row(**update: Any) -> dict[str, Any]:
    row = {
        "run_id": "run-1",
        "case_id": "case01",
        "status": "fail",
        "verdict": "ERROR",
        "disposition": "INCONCLUSIVE",
        "execution_status": "ERROR",
        "input_tokens": 1000,
        "output_tokens": 100,
        "agent_seconds": 10.0,
        "gate_ledger": PAYLOAD_ERROR,
    }
    row.update(update)
    return row


def test_a_target_exception_episode_scores_zero_and_is_not_operational():
    scored = trajectory(_row(), 0, KIND, ORACLE, None, None, target_exception=True)
    assert scored.target_exception is True
    assert scored.reward_verdict == REWARD_TARGET_EXCEPTION == 0.0
    assert scored.reward == 0.0
    assert (scored.operational, scored.operational_reason) == (False, None)
    assert scored.failure_stop == "target_exception"
    assert scored.verdict is Verdict.ERROR
    assert (scored.passed, scored.verified, scored.false_label) == (False, False, False)


def test_a_harness_fault_keeps_its_error_reward():
    fault = trajectory(_row(), 0, KIND, ORACLE, None, None)
    assert fault.target_exception is False
    assert fault.reward_verdict == fault.reward == REWARD_OPERATIONAL == -0.5
    assert fault.failure_stop == "execution_error"


def test_the_flag_never_moves_a_non_error_episode():
    for row in (
        _row(status="pass", verdict="EXPLOIT_DEMONSTRATED", execution_status="COMPLETED"),
        _row(verdict="INCONCLUSIVE", execution_status="COMPLETED"),
        _row(status="unavailable", verdict=None),
    ):
        plain = trajectory(row, 0, KIND, ORACLE, None, None)
        flagged = trajectory(row, 0, KIND, ORACLE, None, None, target_exception=True)
        assert flagged == plain


def test_a_false_label_outranks_a_target_exception():
    forbidden = Oracle(acceptable=[Disposition.SUPPORTED], forbidden_verdicts=[Verdict.ERROR])
    scored = trajectory(_row(), 0, KIND, forbidden, None, None, target_exception=True)
    assert scored.reward_verdict == -1.0


def test_a_trajectory_cannot_be_both_operational_and_a_target_exception():
    with pytest.raises(ValueError, match="target-side exception"):
        Trajectory(
            run_id="r",
            case_id="c",
            repeat=0,
            kind=KIND,
            language="python",
            status="fail",
            passed=False,
            verified=False,
            false_label=False,
            usage_known=False,
            reward_verdict=0.0,
            reward=0.0,
            operational=True,
            operational_reason="heartbeat_timeout",
            target_exception=True,
        )


# The scored report: one episode reclassified, every other trajectory byte-identical


def _report(store: ArtifactStore) -> dict[str, Any]:
    dataset, _, _ = load_dataset(DATASET)
    base = {
        "disposition": "SUPPORTED",
        "verdict_allowed": True,
        "forbidden_label": False,
        "llm_calls": 2,
        "tool_calls": 0,
        "input_tokens": 2000,
        "output_tokens": 300,
        "agent_seconds": 30.0,
        "reason": "recorded",
    }
    rows = []
    for ordinal, case in enumerate(["case01", "case02", "case03"] * 3):
        run_id = f"run-{ordinal}"
        passed = ordinal not in {0, 1}
        rows.append(
            {
                **base,
                "run_id": run_id,
                "case_id": case,
                "status": "pass" if passed else "fail",
                "verdict": "EXPLOIT_DEMONSTRATED" if passed else "ERROR",
                "execution_status": "COMPLETED" if passed else "ERROR",
                "gate_ledger": PAYLOAD_ERROR
                if not passed
                else [{"session": 1, "round": 1, "stage": "kernel", "gate": "demonstrated"}],
            }
        )
    # run-0 is a target-side exception; run-1 a sandbox fault with no driver record.
    _stored(store, {"control": HELD, "adversarial": _receipt("adversarial")}, run_id="run-0")
    fault = {"control": HELD, "adversarial": {**SANDBOX_FAULT, "role": "adversarial"}}
    _stored(store, fault, run_id="run-1")
    return {"rows": rows, "summary": {}, "dataset_digest": digest(dataset)}


def _score(report: dict[str, Any], results) -> tuple[list[Trajectory], Scorecard]:
    return score_report(report, DATASET, results, run=RunContext(run_id="r"))


def test_scoring_reclassifies_only_the_target_exception_episode(store):
    report = _report(store)
    run_ids = [row["run_id"] for row in report["rows"]]
    loaded = load_results(store, run_ids)
    before, old = _score(report, dict(loaded))
    after, new = _score(report, loaded)
    assert [item.target_exception for item in after] == [True] + [False] * 8
    assert (after[0].reward, before[0].reward) == (0.0, -0.5)
    assert after[1].reward == before[1].reward == -0.5
    assert after[1].failure_stop == "execution_error"
    for old_item, new_item in zip(before[2:], after[2:], strict=True):
        assert new_item.model_dump_json() == old_item.model_dump_json()
    reclassified = {"operational": True, "operational_reason": OperationalReason.SANDBOX_FAULT}
    assert after[1] == before[1].model_copy(update=reclassified)
    assert new.target_exception_episodes == 1
    assert old.target_exception_episodes == 0
    assert new.target_exceptions == [
        TargetExceptionEpisode(case_id="case01", repeat=0, language="python")
    ]
    assert new.languages["python"].target_exception_episodes == 1
    # run-1's sandbox fault is now visible as operational; its reward is unchanged.
    assert old.operational_episodes == 0
    assert new.operational_episodes == 1
    assert new.operational_stops == [
        OperationalEpisode(
            case_id="case02", repeat=0, language="python", reason=OperationalReason.SANDBOX_FAULT
        )
    ]
    assert (after[1].operational, before[1].operational) == (True, False)
    # One of nine python episodes moves from -0.5 to 0: the case mean by 0.5/3, J by 0.5/9.
    assert new.objective_j - old.objective_j == pytest.approx(0.5 / 9)


def test_views_show_target_exception_episodes(store):
    report = _report(store)
    loaded = load_results(store, [row["run_id"] for row in report["rows"]])
    _, old = _score(report, dict(loaded))
    _, new = _score(report, loaded)
    text = render_scorecard(new)
    assert "- Target-exception episodes: 1" in text
    assert "Target-exception eps" in text
    assert "- `case01` repeat 0" in text
    view = render_gate(gate(old, new, min_repeats=1), old, new)
    assert "Baseline target-exception eps" in view
    assert "| 0 | 1 | +1 |" in view


def test_a_scorecard_written_before_the_fields_reads_them_as_unknown(store):
    report = _report(store)
    _, card = _score(report, load_results(store, [row["run_id"] for row in report["rows"]]))
    data = card.model_dump(mode="json")
    data.pop("target_exception_episodes")
    data.pop("target_exceptions")
    for group in (*data["languages"].values(), *data["kinds"].values()):
        group.pop("target_exception_episodes")
    old = Scorecard.model_validate(data)
    assert old.target_exception_episodes is None
    assert old.languages["python"].target_exception_episodes is None
    assert "- Target-exception episodes: unknown" in render_scorecard(old)
    saved = _score(report, {})[0][0].model_dump(mode="json")
    saved.pop("target_exception")
    assert Trajectory.model_validate(saved).target_exception is False
