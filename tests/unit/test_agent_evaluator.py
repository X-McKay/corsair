import json
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    AuditResult,
    Feedback,
    MatchKind,
    PlanRevision,
    ProducerOutput,
    Submission,
    Usage,
    digest,
)
from corsair.evaluation.agents import (
    fixture_match_kind,
    fixture_matches_oracle,
    fixture_score_row,
    load_frozen_fixture,
)
from corsair.evaluation.scoring import summarize
from corsair.settings import Settings


def _producer_output(
    control_payload: str | None = "control",
    exploit_payload: str | None = "candidate",
    feedback: Feedback | None = None,
) -> ProducerOutput:
    """Build a valid producer output when both exact fixture payloads are supplied."""
    if control_payload is None or exploit_payload is None:
        return ProducerOutput(feedback=feedback)
    return ProducerOutput(
        submission=Submission(
            hypothesis="test",
            plan=PlanRevision(revision=1, objective="test", next_steps=["test"], reason="test"),
            control_payload=control_payload,
            exploit_payload=exploit_payload,
        ),
        feedback=feedback,
    )


def test_frozen_fixture_is_read_once_and_returns_verified_bytes(tmp_path, monkeypatch):
    input_file, oracle_file = tmp_path / "input.json", tmp_path / "oracle.json"
    input_file.write_text('{"untrusted": "fixture"}')
    oracle_file.write_text('{"decision": "ACCEPT"}')
    entry = {
        "input": "input.json",
        "oracle": "oracle.json",
        "input_digest": digest(input_file.read_bytes()),
        "oracle_digest": digest(oracle_file.read_bytes()),
    }
    reads: list[Path] = []
    original = Path.read_bytes

    def read_then_replace(path: Path) -> bytes:
        reads.append(path)
        content = original(path)
        if path == oracle_file:
            oracle_file.write_text('{"decision": "REJECT"}')
        return content

    monkeypatch.setattr(Path, "read_bytes", read_then_replace)
    path, content, oracle = load_frozen_fixture(tmp_path, entry)
    assert path == input_file
    assert json.loads(content)["untrusted"] == "fixture"
    assert oracle["decision"] == "ACCEPT"
    assert reads == [input_file, oracle_file]


def test_auditor_fixture_acceptance_does_not_claim_native_evidence():
    output = AuditOutput(
        review=AuditResult(decision=AuditDecision.ACCEPT, rule="test", reason="test")
    )
    assert fixture_matches_oracle(output, {"decision": "ACCEPT"})
    assert not fixture_matches_oracle(output, {"decision": "REJECT"})
    assert fixture_match_kind(output, {"decision": "ACCEPT"}) is MatchKind.EXACT_MATCH
    assert fixture_match_kind(output, {"decision": "REJECT"}) is MatchKind.CANDIDATE_EXACT_MISMATCH


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (_producer_output(), MatchKind.EXACT_MATCH),
        (_producer_output(exploit_payload="alternate"), MatchKind.CANDIDATE_EXACT_MISMATCH),
        (_producer_output(control_payload="alternate"), MatchKind.CONTROL_MISMATCH),
        (_producer_output(None, None), MatchKind.NO_VALID_OUTPUT),
        (
            _producer_output(
                None,
                None,
                Feedback(gate="provider_policy_block", reason="blocked", operational=True),
            ),
            MatchKind.OPERATIONAL_FAILURE,
        ),
    ],
)
def test_fixture_match_kind_reports_all_exact_output_diagnostics(output, expected):
    oracle = {"control_payload": "control", "candidate_payloads": ["candidate"]}
    assert fixture_match_kind(output, oracle) is expected


def test_operational_fixture_failure_keeps_usage_and_artifact(tmp_path):
    output = AuditOutput(
        feedback=Feedback(gate="provider_policy_block", reason="blocked", operational=True),
        usage=Usage(llm_calls=1),
    )
    row = fixture_score_row(
        output,
        {"decision": "ACCEPT"},
        identity="run1",
        case_id="audit1",
        repeat=0,
        agent="auditor",
        settings=Settings(),
        store=ArtifactStore(tmp_path),
    )
    assert row["status"] == "fail" and row["execution_status"] == "ERROR"
    assert row["llm_calls"] == 1
    assert row["input_tokens"] is None
    assert row["output_artifact"]["sha256"]
    assert row["cohort"] == "live-model-fixture"
    assert row["match_kind"] is MatchKind.OPERATIONAL_FAILURE
    assert json.loads(json.dumps({"rows": [row]}))["rows"][0]["match_kind"] == "operational_failure"


def test_match_kind_does_not_change_exact_pass_rule_or_totals(tmp_path):
    oracle = {"control_payload": "control", "candidate_payloads": ["candidate"]}
    operational = Feedback(gate="provider_policy_block", reason="blocked", operational=True)
    outputs = [
        _producer_output(),
        _producer_output(exploit_payload="alternate"),
        _producer_output(control_payload="alternate"),
        _producer_output(None, None),
        _producer_output(None, None, operational),
        _producer_output(feedback=operational),
    ]
    store = ArtifactStore(tmp_path)
    rows = [
        fixture_score_row(
            output,
            oracle,
            identity=f"run{index}",
            case_id="case01",
            repeat=0,
            agent="producer",
            settings=Settings(),
            store=store,
        )
        for index, output in enumerate(outputs)
    ]

    assert [row["match_kind"] for row in rows] == [
        MatchKind.EXACT_MATCH,
        MatchKind.CANDIDATE_EXACT_MISMATCH,
        MatchKind.CONTROL_MISMATCH,
        MatchKind.NO_VALID_OUTPUT,
        MatchKind.OPERATIONAL_FAILURE,
        MatchKind.OPERATIONAL_FAILURE,
    ]
    assert [row["status"] for row in rows] == ["pass", "fail", "fail", "fail", "fail", "pass"]
    assert summarize(rows)["attempts"] == 6
    assert summarize(rows)["passed"] == 2
    assert summarize(rows)["failed"] == 4
