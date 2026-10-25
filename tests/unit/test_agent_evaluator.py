import json
from pathlib import Path

from corsair.contracts import AuditDecision, AuditOutput, AuditResult, Feedback, Usage, digest
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings
from evals.evaluators.agents import fixture_matches_oracle, fixture_score_row, load_frozen_fixture


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
