"""Gate ledger entries for isolated agent rows, their summaries, comparison and rendering."""

import argparse
import json
import re
from pathlib import Path

import pytest

from corsair.adapters.inference import adk
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    AuditResult,
    Feedback,
    MatchKind,
    ProducerDecision,
    ProducerOutput,
)
from corsair.entrypoints.cli import execute, parser
from corsair.evaluation import agents
from corsair.evaluation.agents import fixture_score_row
from corsair.evaluation.comparison import compare_reports
from corsair.evaluation.ledger import agent_row_ledger, row_ledger
from corsair.evaluation.scoring import summarize
from corsair.settings import Settings
from tests.unit.adk import ScriptedLlm, text_response
from tests.unit.test_agent_evaluator import _producer_output

DATASETS = Path(__file__).resolve().parents[2] / "evals" / "datasets"
PRODUCER_ORACLE = {"control_payload": "control", "candidate_payloads": ["candidate"]}


def _row(agent: str, match_kind: str, feedback: dict | None = None, **fields) -> dict:
    return {
        "case_id": "case01",
        "repeat": 0,
        "status": "pass" if match_kind == "exact_match" else "fail",
        "agent": agent,
        "match_kind": match_kind,
        "feedback": feedback,
        **fields,
    }


def _gate(row: dict) -> tuple[str, str]:
    (entry,) = agent_row_ledger(row)
    assert set(entry) == {"session", "round", "stage", "gate", "reason"}
    assert entry["session"] is None and entry["round"] is None
    return entry["stage"], entry["gate"]


def _invalid(gate: str, reason: str, operational: bool = False) -> dict:
    return {"gate": gate, "reason": reason, "operational": operational}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_row("producer", "exact_match"), ("oracle", "exact_match")),
        (_row("producer", "control_mismatch"), ("oracle", "control_mismatch")),
        (_row("producer", "candidate_exact_mismatch"), ("oracle", "candidate_exact_mismatch")),
        (
            _row(
                "producer",
                "no_valid_output",
                _invalid(
                    "producer_invalid",
                    "producer exhausted its LLM-call budget before structured completion",
                ),
            ),
            ("producer", "producer_invalid:llm_budget"),
        ),
        (
            _row(
                "producer",
                "no_valid_output",
                _invalid(
                    "producer_invalid",
                    "producer exhausted its tool-call budget before structured completion",
                ),
            ),
            ("producer", "producer_invalid:tool_budget"),
        ),
        (
            _row(
                "producer",
                "no_valid_output",
                _invalid("producer_invalid", "plan revision must equal the current round index"),
            ),
            ("producer", "producer_invalid:plan_revision"),
        ),
        (_row("producer", "no_valid_output"), ("producer", "producer_abstained")),
        (
            _row(
                "producer",
                "operational_failure",
                _invalid("provider_max_tokens", "stopped at the cap", operational=True),
            ),
            ("producer", "provider_max_tokens"),
        ),
        (
            _row(
                "auditor",
                "no_valid_output",
                _invalid("audit_invalid", "auditor returned malformed AuditResult output"),
            ),
            ("audit", "audit_invalid:malformed"),
        ),
        (
            _row(
                "auditor",
                "no_valid_output",
                _invalid("audit_invalid", "auditor has no remaining model-call budget"),
            ),
            ("audit", "audit_invalid:llm_budget"),
        ),
        (
            _row(
                "auditor",
                "no_valid_output",
                _invalid("audit_invalid", "auditor returned no structured output"),
            ),
            ("audit", "audit_invalid:no_output"),
        ),
        (_row("auditor", "no_valid_output"), ("audit", "audit_missing")),
        (
            _row(
                "auditor",
                "operational_failure",
                _invalid("provider_permanent", "FinishReason.MAX_TOKENS", operational=True),
            ),
            ("audit", "provider_permanent"),
        ),
        (
            _row("auditor", "exact_match", audit_decision="REJECT", audit_rule="R2"),
            ("oracle", "exact_match"),
        ),
        (
            _row("auditor", "candidate_exact_mismatch", audit_decision="REJECT", audit_rule="R1"),
            ("oracle", "candidate_exact_mismatch:reject:R1"),
        ),
        (
            _row("auditor", "candidate_exact_mismatch", audit_decision="ACCEPT", audit_rule="ALL"),
            ("oracle", "candidate_exact_mismatch:accept:ALL"),
        ),
        (
            # A model-chosen rule outside the fixed rubric never becomes a gate name.
            _row(
                "auditor",
                "candidate_exact_mismatch",
                audit_decision="INSUFFICIENT_CONTEXT",
                audit_rule="the source excerpt is too short",
            ),
            ("oracle", "candidate_exact_mismatch:insufficient_context"),
        ),
        (
            # Reports saved before rows carried the auditor's decision stay unqualified.
            _row("auditor", "candidate_exact_mismatch"),
            ("oracle", "candidate_exact_mismatch"),
        ),
        (_row("unknown-role", "no_valid_output"), ("agent", "no_valid_output")),
    ],
)
def test_each_match_kind_and_gate_has_one_named_entry(row, expected):
    assert _gate(row) == expected


def test_rows_without_an_agent_match_kind_have_no_derived_entry():
    assert agent_row_ledger({"case_id": "case01", "status": "unavailable"}) == []
    assert agent_row_ledger({"case_id": "case01", "match_kind": "not-a-kind"}) == []
    recorded = [{"gate": "audit_reject"}]
    # A recorded ledger wins over derivation; composed rows without one have none.
    assert row_ledger(_row("producer", "exact_match", gate_ledger=recorded)) == recorded
    assert row_ledger({"case_id": "case01", "verdict": "INCONCLUSIVE"}) == []
    assert row_ledger(_row("producer", "exact_match"))[0]["gate"] == "exact_match"


def test_operational_feedback_beside_a_valid_output_names_the_operational_gate():
    row = _row(
        "producer",
        "operational_failure",
        _invalid("provider_temporary", "503", operational=True),
        status="pass",
    )
    assert _gate(row) == ("producer", "provider_temporary")


def test_score_rows_carry_the_ledger_and_no_oracle_content(tmp_path):
    store = ArtifactStore(tmp_path)
    secret = {"control_payload": "oracle-control-marker", "candidate_payloads": ["oracle-x"]}

    def score_row(output: ProducerOutput | AuditOutput, oracle: dict, agent: str) -> dict:
        return fixture_score_row(
            output,
            oracle,
            identity="run1",
            case_id="case01",
            repeat=0,
            agent=agent,
            settings=Settings(),
            store=store,
        )

    rows = [
        score_row(_producer_output(), PRODUCER_ORACLE, "producer"),
        score_row(_producer_output(), secret, "producer"),
        score_row(
            ProducerOutput(
                decision=ProducerDecision(kind="no_grounded_candidate", reason="nothing grounded")
            ),
            secret,
            "producer",
        ),
        score_row(
            AuditOutput(
                review=AuditResult(decision=AuditDecision.ACCEPT, rule="ALL", reason="model text")
            ),
            {"decision": "REJECT"},
            "auditor",
        ),
        score_row(
            AuditOutput(feedback=Feedback(gate="episode_timeout", reason="t", operational=True)),
            {"decision": "REJECT"},
            "auditor",
        ),
    ]
    assert [row["gate_ledger"][0]["gate"] for row in rows] == [
        "exact_match",
        "control_mismatch",
        "producer_abstained",
        "candidate_exact_mismatch:accept:ALL",
        "episode_timeout",
    ]
    assert rows[2]["match_kind"] is MatchKind.NO_VALID_OUTPUT
    serialized = json.dumps([row["gate_ledger"] for row in rows])
    assert "oracle-control-marker" not in serialized and "oracle-x" not in serialized
    assert "model text" not in serialized and "nothing grounded" not in serialized

    summary = summarize(rows)
    assert summary["gate_ledger"] == {
        "candidate_exact_mismatch:accept:ALL": 1,
        "control_mismatch": 1,
        "episode_timeout": 1,
        "exact_match": 1,
        "producer_abstained": 1,
    }
    assert summary["failure_stops"] == {
        "candidate_exact_mismatch:accept:ALL": 1,
        "control_mismatch": 1,
        "episode_timeout": 1,
        "producer_abstained": 1,
    }
    # Pass/fail, attempts and totals are unchanged by the ledger.
    assert (summary["attempts"], summary["passed"], summary["failed"]) == (5, 1, 4)


def test_the_adapter_reasons_the_qualifiers_match_still_exist():
    source = Path(adk.__file__).read_text()
    for marker in (
        "exhausted its LLM-call budget",
        "returned malformed",
        "no remaining model-call budget",
    ):
        assert marker in source


def _auditor_script(responses: list[str]):
    """Run the real auditor factory and ADK runner over one scripted model per case."""
    pending = list(responses)

    async def scripted_run_auditor(audit_input, settings):
        model = ScriptedLlm(model="scripted-auditor", responses=[text_response(pending.pop(0))])
        return await adk.run_auditor(audit_input, settings, model)

    return scripted_run_auditor, pending


def _review(decision: str, rule: str) -> str:
    return json.dumps({"decision": decision, "rule": rule, "reason": "scripted review"})


async def test_isolated_evaluator_round_trip_records_ledgers_in_rows_and_summary(
    tmp_path, monkeypatch, capsys
):
    # audit01's oracle is ACCEPT and audit02's is REJECT; two repeats, case-major per repeat.
    scripted, pending = _auditor_script(
        [
            _review("ACCEPT", "ALL"),
            _review("ACCEPT", "ALL"),
            "not an AuditResult",
            _review("REJECT", "R2"),
        ]
    )
    monkeypatch.setattr(agents, "run_auditor", scripted)
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"artifact_root": str(tmp_path / "artifacts")}))
    output = tmp_path / "auditor.json"
    args = argparse.Namespace(
        agent="auditor",
        dataset=str(DATASETS / "auditor-dev.json"),
        settings=str(settings),
        repeats=2,
        output=str(output),
    )

    assert await agents.evaluate(args) == 1
    assert pending == []
    printed = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text())
    assert printed["summary"] == report["summary"]
    assert [row["gate_ledger"][0]["gate"] for row in report["rows"]] == [
        "exact_match",
        "candidate_exact_mismatch:accept:ALL",
        "audit_invalid:malformed",
        "exact_match",
    ]
    assert report["summary"]["gate_ledger"] == {
        "exact_match": 2,
        "audit_invalid:malformed": 1,
        "candidate_exact_mismatch:accept:ALL": 1,
    }
    assert report["summary"]["failure_stops"] == {
        "audit_invalid:malformed": 1,
        "candidate_exact_mismatch:accept:ALL": 1,
    }

    # The candidate's gate movement against itself with the ledger stripped (a report
    # saved before rows carried one) is zero: derivation and recording agree.
    legacy = {
        **report,
        "rows": [{k: v for k, v in row.items() if k != "gate_ledger"} for row in report["rows"]],
    }
    diff = compare_reports(legacy, report)
    assert all(entry["delta"] == 0 for entry in diff["gate_delta"]["gate_ledger"])
    assert diff["regression"] is False


def _agent_report(*rows: dict) -> dict:
    return {"dataset_digest": "sha256:frozen-agents", "rows": list(rows), "summary": {}}


def _llm_budget(case_id: str, repeat: int) -> dict:
    return _row(
        "producer",
        "no_valid_output",
        _invalid(
            "producer_invalid",
            "producer exhausted its LLM-call budget before structured completion",
        ),
        case_id=case_id,
        repeat=repeat,
    )


def _exact(case_id: str, repeat: int) -> dict:
    return _row("producer", "exact_match", case_id=case_id, repeat=repeat)


def test_compare_attributes_an_isolated_regression_to_the_gates_that_moved():
    baseline = _agent_report(_exact("case01", 0), _exact("case02", 0), _llm_budget("case03", 0))
    candidate = _agent_report(
        _llm_budget("case01", 0), _llm_budget("case02", 0), _llm_budget("case03", 0)
    )

    diff = compare_reports(baseline, candidate)

    assert diff["regression"] is True
    assert diff["gate_delta"]["gate_ledger"] == [
        {"gate": "exact_match", "baseline": 2, "candidate": 0, "delta": -2},
        {"gate": "producer_invalid:llm_budget", "baseline": 1, "candidate": 3, "delta": 2},
    ]
    assert diff["gate_delta"]["failure_stops"] == [
        {"gate": "producer_invalid:llm_budget", "baseline": 1, "candidate": 3, "delta": 2}
    ]
    first = diff["cases"][0]
    assert (first["baseline_stop"], first["candidate_stop"]) == (
        "exact_match",
        "producer_invalid:llm_budget",
    )
    assert diff["cases"][2]["baseline_stop"] == diff["cases"][2]["candidate_stop"]


async def test_human_compare_and_report_render_agent_gates(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "220")
    baseline, candidate = tmp_path / "baseline.json", tmp_path / "candidate.json"
    baseline.write_text(json.dumps(_agent_report(_exact("case01", 0), _llm_budget("case02", 0))))
    candidate.write_text(
        json.dumps(_agent_report(_llm_budget("case01", 0), _llm_budget("case02", 0)))
    )

    args = parser().parse_args(
        ["--format", "human", "--no-color", "compare", str(baseline), str(candidate)]
    )
    assert await execute(args) == 1
    output = capsys.readouterr().out
    assert "gates moved" in output
    assert "exact_match -1, producer_invalid:llm_budget +1" in output
    assert "Gate ledger Δ" in output and "Failing stops" in output
    assert "exact_match -> producer_invalid:llm_budget" in output

    args = parser().parse_args(["--format", "human", "--no-color", "report", str(candidate)])
    assert await execute(args) == 0
    output = capsys.readouterr().out
    assert "Stop" in output and "producer_invalid:llm_budget" in output

    # JSON mode emits the same structured gate delta; exit codes follow regressions only.
    args = parser().parse_args(["--format", "json", "compare", str(baseline), str(baseline)])
    assert await execute(args) == 0
    same = json.loads(capsys.readouterr().out)
    assert [entry["delta"] for entry in same["gate_delta"]["gate_ledger"]] == [0, 0]
    args = parser().parse_args(["--format", "human", "--no-color", "compare", *[str(baseline)] * 2])
    assert await execute(args) == 0
    assert re.search(r"gates moved\s+none", capsys.readouterr().out)
