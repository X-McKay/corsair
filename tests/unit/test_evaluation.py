import json

import pytest

from corsair.contracts import Disposition, ExecutionStatus, InvestigationResult, digest
from corsair.evaluation.scoring import Oracle, load_dataset, score, summarize


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
