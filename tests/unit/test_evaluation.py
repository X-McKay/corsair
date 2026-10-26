import json

import pytest

from corsair.contracts import Disposition, ExecutionStatus, InvestigationResult, digest
from corsair.evaluation.scoring import Oracle, load_dataset, save_report, score, summarize


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


def _negative_result(sessions):
    """Build an EXPLOIT_NOT_DEMONSTRATED result whose rounds carry genuine
    clean-negative observations (control and exploit both hold, target line covered
    in both runs, audit accepted), one round per entry of ``sessions`` carrying that
    entry's session number. The receipt verification that ``validate_saved`` performs
    is tested in test_evidence; these tests stub it to isolate the new session
    grouping and admitted-threshold logic in valid_negative_evidence."""
    from corsair.contracts import (
        AuditDecision,
        AuditOutput,
        AuditResult,
        ProducerDecision,
        ProducerOutput,
        RoundResult,
        Verdict,
    )
    from tests.unit.test_evidence import _prepared, _submission
    from tests.unit.test_verdicts import _clean_negative

    rounds = [
        RoundResult(
            index=1,
            session=session,
            producer=ProducerOutput(
                decision=ProducerDecision(kind="proposal", submission=_submission())
            ),
            observation=_clean_negative(),
            audit=AuditOutput(
                review=AuditResult(decision=AuditDecision.ACCEPT, rule="ok", reason="clean")
            ),
        )
        for session in sessions
    ]
    return InvestigationResult(
        run_id="neg",
        case_id=_prepared().case_id,
        disposition=Disposition.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        reason="independent clean negatives",
        verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
        manifest=_prepared().manifest,
        rounds=rounds,
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
    # Two clean-negative rounds, but both labelled session 1: one independent
    # session, so it cannot reach the admitted threshold of two.
    row = score(_negative_result([1, 1]), _negative_oracle(), store)
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


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
                            decision=AuditDecision.ACCEPT, rule="fabricated", reason="fabricated"
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

    from corsair.evaluation.scoring import Dataset, DatasetEntry

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
