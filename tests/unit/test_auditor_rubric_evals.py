"""The auditor-rubric cohort: one frozen fixture per rubric outcome, scored on decision and rule.

No provider is called: the scripted rows drive the real auditor factory and ADK runner
through ``ScriptedLlm``, which proves the evaluator mechanics, never model quality.
"""

import argparse
import json
from pathlib import Path

import pytest

from corsair.adapters.inference import adk
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditInput,
    AuditOutput,
    AuditResult,
    MatchKind,
    PythonRecipe,
)
from corsair.evaluation import agents
from corsair.evaluation.agents import fixture_score_row
from corsair.evaluation.datasets import load_frozen_fixture
from corsair.evaluation.ledger import agent_row_ledger
from corsair.settings import Settings
from tests.unit.adk import ScriptedLlm, text_response

ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = ROOT / "evals"
RUBRIC = EVALS_ROOT / "datasets" / "auditor-rubric.json"

# The cohort's design, pinned here so an oracle edit is a visible, deliberate change.
EXPECTED = {
    "audit05": ("REJECT", "R1"),
    "audit06": ("REJECT", "R2"),
    "audit07": ("REJECT", "R3"),
    "audit08": ("REJECT", "R4"),
    "audit09": ("INSUFFICIENT_CONTEXT", "R1"),
    "audit10": ("ACCEPT", "ALL"),
    "audit11": ("ACCEPT", "ALL"),
}


def _entries() -> list[dict]:
    document = json.loads(RUBRIC.read_bytes())
    assert document["schema_version"] == "corsair.agent-dataset/1"
    return document["entries"]


def _row(output: AuditOutput, oracle: dict, tmp_path: Path) -> dict:
    return fixture_score_row(
        output,
        oracle,
        identity="run1",
        case_id="audit06",
        repeat=0,
        agent="auditor",
        settings=Settings(),
        store=ArtifactStore(tmp_path),
    )


def _review(decision: str, rule: str) -> AuditOutput:
    return AuditOutput(
        review=AuditResult(decision=AuditDecision(decision), rule=rule, reason="scripted")
    )


@pytest.mark.parametrize(
    ("returned", "oracle", "status", "kind", "gate"),
    [
        # The oracle names the rule: it must match as well as the decision.
        (("REJECT", "R2"), {"decision": "REJECT", "rule": "R2"}, "pass", "exact_match", None),
        (
            ("REJECT", "R1"),
            {"decision": "REJECT", "rule": "R2"},
            "fail",
            "rule_mismatch",
            "rule_mismatch:reject:R1",
        ),
        (
            ("ACCEPT", "ALL"),
            {"decision": "REJECT", "rule": "R2"},
            "fail",
            "candidate_exact_mismatch",
            "candidate_exact_mismatch:accept:ALL",
        ),
        # No rule in the oracle (the dev and expanded cohorts): the decision alone decides.
        (("REJECT", "R4"), {"decision": "REJECT"}, "pass", "exact_match", None),
        (
            ("ACCEPT", "ALL"),
            {"decision": "REJECT"},
            "fail",
            "candidate_exact_mismatch",
            "candidate_exact_mismatch:accept:ALL",
        ),
    ],
)
def test_an_oracle_rule_is_scored_only_when_the_oracle_names_one(
    returned: tuple[str, str], oracle: dict, status: str, kind: str, gate: str | None, tmp_path
):
    row = _row(_review(*returned), oracle, tmp_path)

    assert (row["status"], row["match_kind"]) == (status, kind)
    assert (row["audit_decision"], row["audit_rule"]) == returned
    (entry,) = agent_row_ledger(row)
    assert entry["stage"] == "oracle"
    assert entry["gate"] == (gate or "exact_match")
    # The ledger reason is fixed evaluator text plus the auditor's own output; the
    # expected rule from the oracle never appears in it.
    if kind == "rule_mismatch":
        assert "R2" not in entry["reason"]


def test_a_missing_review_never_reaches_rule_scoring(tmp_path):
    row = _row(AuditOutput(), {"decision": "REJECT", "rule": "R2"}, tmp_path)

    assert (row["status"], row["match_kind"]) == ("fail", MatchKind.NO_VALID_OUTPUT)


def test_rubric_cohort_round_trips_with_one_case_per_rubric_outcome():
    entries = _entries()
    assert [entry["case_id"] for entry in entries] == list(EXPECTED)

    outcomes = set()
    for entry in entries:
        _, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, entry)
        packet = AuditInput.model_validate_json(raw_input)
        document = json.loads(raw_input)
        # Labels stay in the oracle; the packet carries no decision or rule.
        assert not {"decision", "rule", "expected_rule"} & set(document)
        assert "ACCEPT" not in raw_input.decode() and "R1" not in raw_input.decode()
        assert oracle == dict(zip(("decision", "rule"), EXPECTED[entry["case_id"]], strict=True))
        AuditDecision(oracle["decision"])
        assert (oracle["decision"] == "ACCEPT") == (oracle["rule"] == "ALL")
        # Each packet cites the configured function and the fixed root the payload varies under.
        assert isinstance(packet.recipe, PythonRecipe)
        assert f"def {packet.recipe.function}(" in packet.source_excerpt
        assert isinstance(packet.recipe, PythonRecipe)
        assert packet.recipe.payload_parameter not in packet.recipe.fixed_kwargs
        assert packet.finding.file == packet.recipe.module_file
        outcomes.add((oracle["decision"], oracle["rule"]))

    assert outcomes == {
        ("REJECT", "R1"),
        ("REJECT", "R2"),
        ("REJECT", "R3"),
        ("REJECT", "R4"),
        ("INSUFFICIENT_CONTEXT", "R1"),
        ("ACCEPT", "ALL"),
    }


def test_rubric_cohort_leaves_the_dev_and_expanded_cohorts_frozen():
    rubric_ids = {entry["case_id"] for entry in _entries()}
    for name in ("auditor-dev.json", "auditor-expanded.json"):
        document = json.loads((EVALS_ROOT / "datasets" / name).read_bytes())
        assert not rubric_ids & {entry["case_id"] for entry in document["entries"]}
        for entry in document["entries"]:
            _, _, oracle = load_frozen_fixture(EVALS_ROOT, entry)
            assert set(oracle) == {"decision"}


def _scripted_auditor(responses: list[str]):
    pending = list(responses)

    async def scripted_run_auditor(audit_input, settings):
        model = ScriptedLlm(model="scripted-auditor", responses=[text_response(pending.pop(0))])
        return await adk.run_auditor(audit_input, settings, model)

    return scripted_run_auditor, pending


def _evaluate_args(tmp_path: Path) -> argparse.Namespace:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"artifact_root": str(tmp_path / "artifacts")}))
    return argparse.Namespace(
        agent="auditor",
        dataset=str(RUBRIC),
        settings=str(settings),
        repeats=1,
        output=str(tmp_path / "auditor-rubric.json"),
    )


def _answer(decision: str, rule: str) -> str:
    return json.dumps({"decision": decision, "rule": rule, "reason": "scripted review"})


@pytest.mark.asyncio
async def test_scripted_auditor_returning_each_expected_outcome_passes_the_cohort(
    tmp_path, monkeypatch, capsys
):
    scripted, pending = _scripted_auditor([_answer(*expected) for expected in EXPECTED.values()])
    monkeypatch.setattr(agents, "run_auditor", scripted)
    args = _evaluate_args(tmp_path)

    assert await agents.evaluate(args) == 0
    assert pending == []
    capsys.readouterr()
    report = json.loads(Path(args.output).read_text())
    rows = report["rows"]
    assert [row["case_id"] for row in rows] == list(EXPECTED)
    assert [(row["audit_decision"], row["audit_rule"]) for row in rows] == list(EXPECTED.values())
    assert {row["status"] for row in rows} == {"pass"}
    assert all(row["llm_calls"] == 1 and row["tool_calls"] == 0 for row in rows)
    assert report["summary"]["gate_ledger"] == {"exact_match": len(EXPECTED)}


@pytest.mark.asyncio
async def test_scripted_auditor_fails_each_rule_case_separately(tmp_path, monkeypatch, capsys):
    # Right decision, wrong rule on the four rejections; a missed rule on the
    # insufficient-context case; an over-acceptance; and one correct acceptance.
    answers = [
        _answer("REJECT", "R2"),
        _answer("REJECT", "R1"),
        _answer("REJECT", "R1"),
        _answer("REJECT", "R1"),
        _answer("INSUFFICIENT_CONTEXT", "R3"),
        _answer("REJECT", "R1"),
        _answer("ACCEPT", "ALL"),
    ]
    scripted, pending = _scripted_auditor(answers)
    monkeypatch.setattr(agents, "run_auditor", scripted)
    args = _evaluate_args(tmp_path)

    assert await agents.evaluate(args) == 1
    assert pending == []
    capsys.readouterr()
    report = json.loads(Path(args.output).read_text())
    assert [row["gate_ledger"][0]["gate"] for row in report["rows"]] == [
        "rule_mismatch:reject:R2",
        "rule_mismatch:reject:R1",
        "rule_mismatch:reject:R1",
        "rule_mismatch:reject:R1",
        "rule_mismatch:insufficient_context:R3",
        "candidate_exact_mismatch:reject:R1",
        "exact_match",
    ]
    assert (report["summary"]["passed"], report["summary"]["failed"]) == (1, 6)
