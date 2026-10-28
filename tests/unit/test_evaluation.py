import json

import pytest

from corsair.contracts import (
    AssessmentOutcome,
    Disposition,
    ExecutionStatus,
    InvestigationResult,
    digest,
    format_terminal_result,
)
from corsair.evaluation.scoring import (
    AssessmentOracle,
    Oracle,
    load_dataset,
    save_report,
    score,
    summarize,
)


def result(label=Disposition.INCONCLUSIVE):
    return InvestigationResult(
        run_id="run01",
        case_id="case01",
        disposition=label,
        execution_status=ExecutionStatus.COMPLETED,
        reason="budget",
    )


def test_correct_label_without_evidence_does_not_pass():
    row = score(result(Disposition.SUPPORTED), Oracle(acceptable=[Disposition.SUPPORTED]))
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


def test_negative_abstention_is_not_counted_as_resolution():
    row = score(result(), Oracle(acceptable=[Disposition.INCONCLUSIVE]))
    assert row["status"] == "pass"
    assert row["correctly_resolved"] is False
    assert row["input_tokens"] is None


def test_retired_refuted_legacy_row_is_never_counted_as_resolution():
    historical = InvestigationResult(
        schema_version="corsair.result/1",
        run_id="legacy",
        case_id="case01",
        disposition=Disposition.REFUTED,
        execution_status=ExecutionStatus.COMPLETED,
        reason="historical row",
    )

    row = score(historical, Oracle(acceptable=[Disposition.REFUTED]))

    assert row["status"] == "pass"
    assert row["correctly_resolved"] is False


def _record_unit_evidence_final_result(store, result: InvestigationResult) -> InvestigationResult:
    """Write a unit-only stand-in for the trusted record activity.

    This helper exercises the scorer's immutable-record boundary with synthetic
    native evidence. It is not a workflow, Docker, Temporal, or production
    qualification path; ``Activities.record`` owns production final recording.
    """
    normalized = format_terminal_result(result.model_copy(update={"result_artifact": None}))
    ref = store.put_json(normalized)
    store.commit(f"result.{normalized.run_id}", ref)
    return format_terminal_result(normalized.model_copy(update={"result_artifact": ref}))


def _assessment_unit_evidence_result(store, outcome: AssessmentOutcome) -> InvestigationResult:
    """Build valid saved native pairs solely for deterministic scorer unit tests."""
    from corsair.contracts import (
        AuditDecision,
        AuditOutput,
        AuditResult,
        PlanRevision,
        ProducerDecision,
        ProducerOutput,
        ProducerProposal,
        RoleOutcome,
        RoundResult,
    )
    from corsair.policies.verdicts import assessment_outcome
    from corsair.settings import Settings
    from corsair.steps.verification import EvidenceVerifier
    from tests.unit.test_evidence import _FakeSandbox, _input, _prepared, _submission

    admitted_source = store.put(b"admitted source", "application/x-tar")
    prepared = _prepared().model_copy(update={"source": admitted_source})
    run_id = (
        "assessment-held" if outcome is AssessmentOutcome.NOT_DEMONSTRATED else "assessment-demo"
    )
    role_outcome = (
        RoleOutcome.HELD if outcome is AssessmentOutcome.NOT_DEMONSTRATED else RoleOutcome.VIOLATION
    )
    rounds = []
    for index in range(1, 4 if outcome is AssessmentOutcome.NOT_DEMONSTRATED else 2):
        base_submission = _submission()
        submission = base_submission.model_copy(
            update={
                "exploit_payload": {"segments": ["..", "private", f"secret-{index}.txt"]},
                "plan": PlanRevision(
                    revision=index,
                    objective=base_submission.plan.objective,
                    next_steps=base_submission.plan.next_steps,
                    reason=base_submission.plan.reason,
                ),
            }
        )
        evidence_input = _input(f"{run_id}.r{index}").model_copy(
            update={"run_id": run_id, "prepared": prepared, "submission": submission}
        )
        observation = EvidenceVerifier(
            Settings(), store, _FakeSandbox(store, adversarial_outcome=role_outcome)
        ).evaluate(evidence_input)
        audit = AuditOutput(
            review=AuditResult(
                decision=AuditDecision.ACCEPT,
                rule="evidence",
                reason="reviewed without execution outcome input",
            )
        )
        assert assessment_outcome(prepared, observation, audit) is outcome
        rounds.append(
            RoundResult(
                index=index,
                producer=ProducerOutput(
                    decision=ProducerDecision(root=ProducerProposal(submission=submission))
                ),
                observation=observation,
                audit=audit,
            )
        )
    return _record_unit_evidence_final_result(
        store,
        InvestigationResult(
            run_id=run_id,
            case_id="case",
            disposition=(
                Disposition.INCONCLUSIVE
                if outcome is AssessmentOutcome.NOT_DEMONSTRATED
                else Disposition.SUPPORTED
            ),
            execution_status=ExecutionStatus.COMPLETED,
            reason="bounded protocol completed",
            assessment_outcome=outcome,
            manifest=prepared.manifest,
            rounds=rounds,
        ),
    )


def test_assessment_oracle_requires_trusted_complete_negative_protocol(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    store = ArtifactStore(tmp_path / "artifacts")
    assessed = _assessment_unit_evidence_result(store, AssessmentOutcome.NOT_DEMONSTRATED)
    oracle = AssessmentOracle(
        schema_version="corsair.assessment-oracle/1",
        acceptable=[AssessmentOutcome.NOT_DEMONSTRATED],
    )
    row = score(assessed, oracle, store)

    assert row["status"] == "pass"
    assert row["evidence_valid"] is True
    assert row["assessment_outcome"] == "NOT_DEMONSTRATED"
    assert row["correctly_resolved"] is True
    summary = summarize([row])
    assert summary["assessment_completed"] == 1
    assert summary["assessment_incomplete"] == 0
    assert summary["not_demonstrated"] == 1

    truncated = assessed.model_copy(update={"rounds": assessed.rounds[:1]})
    rejected = score(truncated, oracle, store)
    assert rejected["status"] == "fail"
    assert rejected["evidence_valid"] is False


def test_assessment_oracle_requires_matching_trusted_final_record(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import AuditOutput

    store = ArtifactStore(tmp_path / "artifacts")
    assessed = _assessment_unit_evidence_result(store, AssessmentOutcome.NOT_DEMONSTRATED)
    oracle = AssessmentOracle(
        schema_version="corsair.assessment-oracle/1",
        acceptable=[AssessmentOutcome.NOT_DEMONSTRATED],
    )
    first = assessed.rounds[0]
    assert first.audit is not None and first.audit.review is not None
    copied_audit = AuditOutput(
        review=first.audit.review.model_copy(update={"reason": "copied accepted audit"})
    )
    copied_round = first.model_copy(update={"audit": copied_audit})
    altered_audit = assessed.model_copy(update={"rounds": [copied_round, *assessed.rounds[1:]]})

    for forged in (
        assessed.model_copy(update={"run_id": "assessment-copy"}),
        altered_audit,
    ):
        row = score(forged, oracle, store)
        assert row["status"] == "fail"
        assert row["evidence_valid"] is False


def test_assessment_oracle_rejects_copied_operation_in_complete_looking_record(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    store = ArtifactStore(tmp_path / "artifacts")
    assessed = _assessment_unit_evidence_result(store, AssessmentOutcome.NOT_DEMONSTRATED)
    copied_operation = _record_unit_evidence_final_result(
        store,
        assessed.model_copy(update={"run_id": "assessment-copy", "result_artifact": None}),
    )
    row = score(
        copied_operation,
        AssessmentOracle(
            schema_version="corsair.assessment-oracle/1",
            acceptable=[AssessmentOutcome.NOT_DEMONSTRATED],
        ),
        store,
    )

    assert row["status"] == "fail"
    assert row["evidence_valid"] is False


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.ERROR, ExecutionStatus.BLOCKED, ExecutionStatus.CANCELLED],
)
def test_assessment_oracle_never_resolves_operational_negative_even_if_bypassed(status, tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    store = ArtifactStore(tmp_path / "artifacts")
    assessed = _assessment_unit_evidence_result(store, AssessmentOutcome.NOT_DEMONSTRATED)
    bypassed_contract = assessed.model_copy(update={"execution_status": status})
    row = score(
        bypassed_contract,
        AssessmentOracle(
            schema_version="corsair.assessment-oracle/1",
            acceptable=[AssessmentOutcome.NOT_DEMONSTRATED],
            expected_execution=status,
        ),
        store,
    )

    assert row["status"] == "fail"
    assert row["evidence_valid"] is False
    assert row["correctly_resolved"] is False


def test_assessment_oracle_accepts_demonstrated_selected_round_in_matching_record(tmp_path):
    from corsair.adapters.storage.filesystem import ArtifactStore

    store = ArtifactStore(tmp_path / "artifacts")
    assessed = _assessment_unit_evidence_result(store, AssessmentOutcome.DEMONSTRATED)
    row = score(
        assessed,
        AssessmentOracle(
            schema_version="corsair.assessment-oracle/1",
            acceptable=[AssessmentOutcome.DEMONSTRATED],
        ),
        store,
    )

    assert row["status"] == "pass"
    assert row["evidence_valid"] is True


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
        ProducerProposal,
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
                        decision=ProducerDecision(root=ProducerProposal(submission=submission))
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
