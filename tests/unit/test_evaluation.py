import json

import pytest

from corsair.contracts import Disposition, ExecutionStatus, InvestigationResult, Oracle, digest
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.scoring import save_report, score, summarize


def result(label=Disposition.INCONCLUSIVE):
    return InvestigationResult(
        run_id="run01",
        case_id="case01",
        disposition=label,
        execution_status=ExecutionStatus.COMPLETED,
        reason="budget",
    )


def test_oracle_without_verdict_expectation_ignores_the_verdict():
    row = score(result(), Oracle(acceptable=[Disposition.INCONCLUSIVE]))
    assert row["status"] == "pass"
    assert row["verdict_allowed"] is True
    assert row["verdict"] is None


def test_oracle_scores_the_canonical_verdict_label():
    from corsair.contracts import Verdict

    oracle = Oracle(
        acceptable=[Disposition.INCONCLUSIVE], acceptable_verdicts=[Verdict.INCONCLUSIVE]
    )
    mislabelled = result().model_copy(update={"verdict": Verdict.EXPLOIT_NOT_DEMONSTRATED})
    row = score(mislabelled, oracle)
    assert row["status"] == "fail"
    assert row["verdict_allowed"] is False
    assert row["verdict"] == "EXPLOIT_NOT_DEMONSTRATED"

    aligned = result().model_copy(update={"verdict": Verdict.INCONCLUSIVE})
    assert score(aligned, oracle)["status"] == "pass"


def test_forbidden_verdict_blocks_a_pass():
    from corsair.contracts import Verdict

    base = result().model_copy(update={"verdict": Verdict.EXPLOIT_NOT_DEMONSTRATED})
    oracle = Oracle(
        acceptable=[Disposition.INCONCLUSIVE],
        forbidden_verdicts=[Verdict.EXPLOIT_NOT_DEMONSTRATED],
    )
    row = score(base, oracle)
    assert row["status"] == "fail"
    assert row["verdict_allowed"] is False


def test_correct_label_without_evidence_does_not_pass():
    row = score(result(Disposition.SUPPORTED), Oracle(acceptable=[Disposition.SUPPORTED]))
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


def test_negative_abstention_is_not_counted_as_resolution():
    row = score(result(), Oracle(acceptable=[Disposition.INCONCLUSIVE]))
    assert row["status"] == "pass"
    assert row["correctly_resolved"] is False
    assert row["input_tokens"] is None


def test_a_decisive_label_with_no_validated_evidence_is_never_a_resolution():
    """Resolution follows the code-decided label, but a decisive label with no
    validated evidence must NOT pass: an empty result (no manifest, no receipts)
    carrying any decisive verdict fails validation rather than being credited as a
    resolution. This closes the bypass where a negative label skipped validation."""
    from corsair.contracts import Verdict

    # SUPPORTED disposition but no final label recorded -> not resolved.
    supported_oracle = Oracle(acceptable=[Disposition.SUPPORTED])
    no_verdict_row = score(result(Disposition.SUPPORTED), supported_oracle)
    assert no_verdict_row["correctly_resolved"] is False

    for verdict in (
        Verdict.EXPLOIT_DEMONSTRATED,
        Verdict.COMPONENT_EXPLOIT_DEMONSTRATED,
        Verdict.EXPLOIT_NOT_DEMONSTRATED,
    ):
        resolved = result().model_copy(update={"verdict": verdict})
        row = score(
            resolved,
            Oracle(acceptable=[Disposition.INCONCLUSIVE], acceptable_verdicts=[verdict]),
        )
        assert row["status"] == "fail"
        assert row["evidence_valid"] is False
        assert row["correctly_resolved"] is False

    for verdict in (Verdict.INCONCLUSIVE, Verdict.UNABLE_TO_RUN, Verdict.ERROR):
        row = score(
            result().model_copy(update={"verdict": verdict}),
            Oracle(acceptable=[Disposition.INCONCLUSIVE], acceptable_verdicts=[verdict]),
        )
        assert row["correctly_resolved"] is False


def test_a_positive_disposition_can_never_aggregate_to_a_negative_label():
    """A SUPPORTED/CONDITIONAL disposition paired with EXPLOIT_NOT_DEMONSTRATED is a
    combination the kernel can never produce; evidence validation rejects it."""
    from corsair.contracts import Verdict
    from corsair.evaluation.scoring import valid_evidence

    inconsistent = result(Disposition.SUPPORTED).model_copy(
        update={"verdict": Verdict.EXPLOIT_NOT_DEMONSTRATED}
    )
    assert valid_evidence(inconsistent, None) is False


def _clean_round(session: int, index: int = 1, *, run_id: str = "neg", exploit=None, op=None):
    """One round carrying a genuine clean-negative observation (control and exploit both
    hold, target line covered in both runs, audit accepted). By default its operation id
    is the one the workflow assigns to (run, session, index) and its exploit payload is
    distinct per session; ``exploit`` and ``op`` override them."""
    from corsair.contracts import (
        AuditDecision,
        AuditOutput,
        AuditResult,
        AuditRule,
        ProducerDecision,
        ProducerOutput,
        RoundResult,
    )
    from corsair.policies.operations import round_operation_id
    from tests.unit.test_evidence import _submission
    from tests.unit.test_verdicts import _clean_negative

    submission = _submission().model_copy(
        update={"exploit_payload": exploit if exploit is not None else f"../s{session}/secret"}
    )
    observation = _clean_negative().model_copy(
        update={"operation_id": op or round_operation_id(run_id, session, index)}
    )
    return RoundResult(
        index=index,
        session=session,
        producer=ProducerOutput(decision=ProducerDecision(kind="proposal", submission=submission)),
        observation=observation,
        audit=AuditOutput(
            review=AuditResult(decision=AuditDecision.ACCEPT, rule=AuditRule.ALL, reason="clean")
        ),
    )


def _negative_result(sessions, *, run_id: str = "neg", rounds=None):
    """An EXPLOIT_NOT_DEMONSTRATED result with one clean round per entry of
    ``sessions`` (that entry's session number), or the given ``rounds``. The receipt
    verification that ``validate_saved`` performs is tested in test_evidence; tests
    that stub it isolate the session, candidate and operation-binding logic in
    valid_negative_evidence."""
    from corsair.contracts import Verdict
    from tests.unit.test_evidence import _prepared

    return InvestigationResult(
        run_id=run_id,
        case_id=_prepared().case_id,
        disposition=Disposition.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        reason="independent clean negatives",
        verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
        manifest=_prepared().manifest,
        rounds=rounds if rounds is not None else [_clean_round(s, run_id=run_id) for s in sessions],
    )


def _negative_oracle():
    from corsair.contracts import Verdict

    return Oracle(
        acceptable=[Disposition.INCONCLUSIVE],
        acceptable_verdicts=[Verdict.EXPLOIT_NOT_DEMONSTRATED],
    )


def _accept_saved_receipts(monkeypatch):
    """Stub validate_saved to accept the receipts (returning the fixture prepared
    case); the clean-negative determination still runs the real session_verdict."""
    from corsair.steps.verification import EvidenceVerifier
    from tests.unit.test_evidence import _prepared

    monkeypatch.setattr(
        EvidenceVerifier, "validate_saved", lambda self, obs, sub, man, **k: _prepared()
    )


def test_a_negative_label_needs_the_admitted_threshold_of_clean_sessions(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    row = score(_negative_result([1, 2]), _negative_oracle(), store)
    assert row["status"] == "pass"
    assert row["evidence_valid"] is True
    assert row["correctly_resolved"] is True


def test_a_single_clean_session_cannot_clear_a_negative_label(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    row = score(_negative_result([1]), _negative_oracle(), store)
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


def test_duplicate_session_identity_is_not_counted_as_two_clean_sessions(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    # Two clean-negative rounds, but both labelled session 1 round 1: one independent
    # session, so it cannot reach the admitted threshold of two.
    row = score(_negative_result([1, 1]), _negative_oracle(), store)
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


def test_a_repeated_candidate_is_not_a_second_clean_session(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    repeated = [_clean_round(1, exploit="../x"), _clean_round(2, exploit="../x")]
    row = score(_negative_result([], rounds=repeated), _negative_oracle(), store)
    assert row["evidence_valid"] is False
    # The exact-digest floor: a near-duplicate spelling is a distinct candidate.
    near = [_clean_round(1, exploit="../x"), _clean_round(2, exploit="./../x")]
    assert score(_negative_result([], rounds=near), _negative_oracle(), store)["evidence_valid"]


def test_a_receipt_is_counted_only_under_its_own_run_session_and_round(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    # Session 2 carries a receipt named for session 1's operation.
    relabelled = [_clean_round(1), _clean_round(2, op="neg.r1")]
    assert not score(_negative_result([], rounds=relabelled), _negative_oracle(), store)[
        "evidence_valid"
    ]
    # Receipts named for other runs of the same case.
    spliced = [_clean_round(1, op="runA.r1"), _clean_round(2, op="runB.s2.r1")]
    assert not score(_negative_result([], rounds=spliced), _negative_oracle(), store)[
        "evidence_valid"
    ]
    # A round index that does not match the operation's round.
    shifted = [_clean_round(1), _clean_round(2, index=2, op="neg.s2.r1")]
    assert not score(_negative_result([], rounds=shifted), _negative_oracle(), store)[
        "evidence_valid"
    ]


def test_a_session_is_clean_only_by_its_terminal_round(tmp_path, monkeypatch):
    """A clean earlier round does not make a session clean when its terminal round
    was not: the workflow decides each session by its last evaluated round."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import AuditDecision
    from tests.unit.test_evidence import _audit

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    rejected = _clean_round(1, index=2).model_copy(update={"audit": _audit(AuditDecision.REJECT)})
    rounds = [_clean_round(1, index=1), rejected, _clean_round(2)]
    row = score(_negative_result([], rounds=rounds), _negative_oracle(), store)
    assert row["evidence_valid"] is False


def _genuine_receipt(store, verifier, operation_id: str, exploit: str):
    """Run the trusted evidence path against the fake sandbox and return the committed
    observation and its submission (control held, exploit held unless it violates)."""
    from corsair.contracts import Budget, EvidenceInput
    from tests.unit.test_evidence import _prepared, _submission

    prepared = _prepared().model_copy(
        update={"source": store.put(b"admitted source", "application/x-tar")}
    )
    submission = _submission().model_copy(update={"exploit_payload": exploit})
    evidence = EvidenceInput(
        run_id="run",
        operation_id=operation_id,
        prepared=prepared,
        submission=submission,
        budget=Budget(probe_timeout_seconds=5),
    )
    return verifier.evaluate(evidence), submission


def _genuine_round(store, verifier, session: int, operation_id: str, exploit: str):
    from corsair.contracts import ProducerDecision, ProducerOutput, RoundResult
    from tests.unit.test_evidence import _audit

    observation, submission = _genuine_receipt(store, verifier, operation_id, exploit)
    return RoundResult(
        index=1,
        session=session,
        producer=ProducerOutput(decision=ProducerDecision(kind="proposal", submission=submission)),
        observation=observation,
        audit=_audit(),
    )


def test_genuine_receipts_cannot_be_relabelled_spliced_or_repeated(tmp_path):
    """The external reviewer's reproductions with committed receipts: one receipt as
    two sessions (E1), single-session receipts of two runs spliced into a third (E2),
    and one candidate repeated in a fresh session (D) never clear a negative label,
    while two distinct candidates under their own operation ids do."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.settings import Settings
    from corsair.steps.verification import EvidenceVerifier
    from tests.unit.test_evidence import _FakeSandbox

    store = ArtifactStore(tmp_path / "artifacts")
    verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store, adversarial_violates=False))
    a1 = _genuine_round(store, verifier, 1, "runA.r1", "../a")
    a2_repeat = _genuine_round(store, verifier, 2, "runA.s2.r1", "../a")
    b1 = _genuine_round(store, verifier, 1, "runB.r1", "../b")
    d2 = _genuine_round(store, verifier, 2, "runD.s2.r1", "../d")
    d1 = _genuine_round(store, verifier, 1, "runD.r1", "../a")

    def valid(run_id, rounds):
        return score(_negative_result([], run_id=run_id, rounds=rounds), _negative_oracle(), store)[
            "evidence_valid"
        ]

    assert not valid("runA", [a1, a1.model_copy(update={"session": 2})])
    assert not valid("runC", [a1, b1.model_copy(update={"session": 2})])
    assert not valid("runA", [a1, a2_repeat])
    assert valid("runD", [d1, d2])


def test_unavailable_cases_remain_in_denominator():
    report = summarize(
        [
            score(result(), Oracle(acceptable=[Disposition.INCONCLUSIVE])),
            {"status": "unavailable", "reason": "lost host"},
        ]
    )
    assert report["attempts"] == 2
    assert report["pass_rate"] == 0.5
    assert report["failed"] == 1
    assert report["unavailable_results"] == 1
    assert report["input_tokens"] is None
    assert report["cost_usd"] is None


def test_save_report_returns_the_single_complete_write(tmp_path, monkeypatch):
    destination = tmp_path / "report.json"
    dataset_digest = digest({"dataset": "frozen"})
    writes = 0
    original_write = type(destination).write_text

    def record_write(path, content):
        nonlocal writes
        writes += 1
        return original_write(path, content)

    monkeypatch.setattr(type(destination), "write_text", record_write)
    report = save_report(destination, [{"status": "pass"}], dataset_digest=dataset_digest)

    assert writes == 1
    assert json.loads(destination.read_text()) == report
    assert report["dataset_digest"] == dataset_digest


def test_frozen_oracle_refuses_changes(tmp_path):
    request = tmp_path / "request.json"
    oracle = tmp_path / "oracle.json"
    request.write_text(
        json.dumps(
            {
                "case": {
                    "case_id": "case01",
                    "finding": {"title": "claim", "description": "claim", "file": "x.py"},
                    "source": {"path": "."},
                    "recipe": {"module_file": "x.py", "function": "f", "payload_parameter": "p"},
                }
            }
        )
    )
    oracle.write_text('{"acceptable": ["INCONCLUSIVE"]}')
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "case_id": "case01",
                        "family": "family01",
                        "split": "dev",
                        "request": "request.json",
                        "oracle": "oracle.json",
                        "request_digest": digest(request.read_bytes()),
                        "oracle_digest": digest(oracle.read_bytes()),
                    }
                ]
            }
        )
    )
    _, requests, oracles = load_dataset(dataset)
    assert len(requests) == 1 and oracles["case01"].acceptable == [Disposition.INCONCLUSIVE]
    assert "acceptable" not in requests[0].model_dump_json()
    oracle.write_text('{"acceptable": ["SUPPORTED"]}')
    with pytest.raises(ValueError, match="oracle digest"):
        load_dataset(dataset)


@pytest.mark.parametrize("artifact_exists", [False, True])
def test_synthetic_positive_with_plausible_roles_cannot_pass(artifact_exists, tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import (
        ArtifactRef,
        AuditDecision,
        AuditOutput,
        AuditResult,
        AuditRule,
        Observation,
        ProducerDecision,
        ProducerOutput,
        RoleObservation,
        RoleOutcome,
        RoundResult,
    )
    from tests.unit.test_evidence import _prepared, _submission

    store = ArtifactStore(tmp_path)
    reference = (
        store.put_json({"fake": "not native evidence"})
        if artifact_exists
        else ArtifactRef(sha256="1" * 64, size=1, media_type="application/json")
    )
    submission = _submission()
    observation = Observation(
        operation_id="forged",
        source_digest=_prepared().source.sha256,
        submission_digest=digest(submission),
        artifact=reference,
        cleanup_confirmed=True,
        control=RoleObservation(
            outcome=RoleOutcome.HELD,
            target_executed=True,
            native_exit_code=0,
            covered_lines=[4],
            reason="forged",
        ),
        adversarial=RoleObservation(
            outcome=RoleOutcome.VIOLATION,
            target_executed=True,
            native_exit_code=1,
            covered_lines=[4],
            reason="forged",
        ),
    )
    store.commit("forged", store.put_json(observation))
    fabricated = result(Disposition.SUPPORTED).model_copy(
        update={
            "manifest": _prepared().manifest,
            "rounds": [
                RoundResult(
                    index=1,
                    producer=ProducerOutput(
                        decision=ProducerDecision(kind="proposal", submission=submission)
                    ),
                    observation=observation,
                    audit=AuditOutput(
                        review=AuditResult(
                            decision=AuditDecision.ACCEPT, rule=AuditRule.ALL, reason="fabricated"
                        )
                    ),
                )
            ],
        }
    )
    scored = score(fabricated, Oracle(acceptable=[Disposition.SUPPORTED]), store)
    assert scored["status"] == "fail"
    assert scored["evidence_valid"] is False


def test_missing_call_usage_is_unknown_not_zero():
    summary = summarize(
        [
            {"status": "pass", "llm_calls": 2, "tool_calls": 3},
            {"status": "unavailable"},
        ]
    )
    assert summary["llm_calls"] is None
    assert summary["tool_calls"] is None


def test_lost_episode_usage_stays_unknown():
    interrupted = result().model_copy(update={"usage_complete": False})
    scored = score(interrupted, Oracle(acceptable=[Disposition.INCONCLUSIVE]))
    assert scored["llm_calls"] is None
    assert scored["tool_calls"] is None
    assert scored["agent_seconds"] is None


def test_dataset_parses_only_the_bytes_it_verified(tmp_path, monkeypatch):
    from collections import Counter
    from pathlib import Path

    from corsair.contracts import Dataset, DatasetEntry

    request = tmp_path / "request.json"
    oracle = tmp_path / "oracle.json"
    request.write_text(
        json.dumps(
            {
                "case": {
                    "case_id": "case01",
                    "finding": {"title": "claim", "description": "claim", "file": "x.py"},
                    "source": {"path": "."},
                    "recipe": {"module_file": "x.py", "function": "f", "payload_parameter": "p"},
                }
            }
        )
    )
    oracle.write_text('{"acceptable": ["INCONCLUSIVE"]}')
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        Dataset(
            entries=[
                DatasetEntry(
                    case_id="case01",
                    family="family01",
                    split="dev",
                    request="request.json",
                    oracle="oracle.json",
                    request_digest=digest(request.read_bytes()),
                    oracle_digest=digest(oracle.read_bytes()),
                )
            ]
        ).model_dump_json()
    )
    reads: Counter[Path] = Counter()
    original_read = Path.read_bytes

    def read_and_replace(path: Path) -> bytes:
        reads[path] += 1
        content = original_read(path)
        if path == oracle:
            oracle.write_text('{"acceptable": ["SUPPORTED"]}')
        return content

    monkeypatch.setattr(Path, "read_bytes", read_and_replace)
    _, _, oracles = load_dataset(dataset)
    assert oracles["case01"].acceptable == [Disposition.INCONCLUSIVE]
    assert reads[request] == reads[oracle] == 1


@pytest.mark.parametrize(
    "counts,expected", [([], None), ([None], None), ([0, 0], 0), ([1, 2], 3), ([2, None], None)]
)
def test_summary_counts_preserve_empty_missing_and_zero(counts, expected):
    summary = summarize([{"status": "pass", "input_tokens": value} for value in counts])
    assert summary["input_tokens"] == expected


@pytest.mark.parametrize(
    ("name", "forbidden_verdict"),
    [("safety", "EXPLOIT_NOT_DEMONSTRATED"), ("adversarial", "EXPLOIT_DEMONSTRATED")],
)
def test_safety_and_adversarial_sets_load_frozen_with_conservative_oracles(
    name: str, forbidden_verdict: str
):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    dataset, requests, oracles = load_dataset(root / f"evals/datasets/{name}.json")
    assert len(requests) == len(dataset.entries) >= 2
    for request in requests:
        oracle = oracles[request.case.case_id]
        # A false "not exploitable" is the costliest error: no oracle ever accepts REFUTED,
        # and the canonical forbidden verdict names the error each set is built to catch.
        assert Disposition.REFUTED in oracle.forbidden
        assert Disposition.REFUTED not in oracle.acceptable
        assert forbidden_verdict in oracle.forbidden_verdicts
        assert oracle.acceptable_verdicts is not None
        assert forbidden_verdict not in oracle.acceptable_verdicts
        assert "INCONCLUSIVE" in oracle.acceptable_verdicts


def test_a_positive_receipt_counts_only_under_its_own_run(tmp_path):
    """A genuine demonstration receipt from one run does not validate another run's
    positive label, nor the same run's label under a different round."""
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import Verdict
    from corsair.settings import Settings
    from corsair.steps.verification import EvidenceVerifier
    from tests.unit.test_evidence import _FakeSandbox

    store = ArtifactStore(tmp_path / "artifacts")
    verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store))
    demonstrated = _genuine_round(store, verifier, 1, "runA.r1", "../a")

    def valid(run_id, item):
        positive = _negative_result([], run_id=run_id, rounds=[item]).model_copy(
            update={"disposition": Disposition.SUPPORTED, "verdict": Verdict.EXPLOIT_DEMONSTRATED}
        )
        return score(positive, Oracle(acceptable=[Disposition.SUPPORTED]), store)["evidence_valid"]

    assert valid("runA", demonstrated)
    assert not valid("runB", demonstrated)
    assert not valid("runA", demonstrated.model_copy(update={"index": 2}))
