"""Evaluator-side gate ledger over synthetic InvestigationResult objects."""

import inspect
import json

from corsair.adapters.inference import adk
from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    Disposition,
    ExecutionStatus,
    Feedback,
    InvestigationResult,
    NoGroundedCandidate,
    Observation,
    ProducerDecision,
    ProducerOutput,
    ProducerProposal,
    RoleOutcome,
    RoundResult,
    Verdict,
)
from corsair.entrypoints.cli import execute, parser
from corsair.evaluation import ledger
from corsair.evaluation.ledger import gate_ledger, ledger_counts
from corsair.evaluation.scoring import Oracle, save_report, score, summarize
from corsair.workflows import investigation
from tests.unit.test_evidence import _audit, _prepared, _submission
from tests.unit.test_verdicts import _HELD, _VIOLATION, _clean_negative, _observation, _role


def _proposal() -> ProducerOutput:
    return ProducerOutput(
        decision=ProducerDecision(root=ProducerProposal(submission=_submission()))
    )


def _invalid(reason: str, gate: str = "producer_invalid", operational: bool = False):
    return ProducerOutput(feedback=Feedback(gate=gate, reason=reason, operational=operational))


def _round(
    producer: ProducerOutput,
    observation: Observation | None = None,
    audit: AuditOutput | None = None,
    *,
    index: int = 1,
    session: int = 1,
) -> RoundResult:
    return RoundResult(
        index=index, session=session, producer=producer, observation=observation, audit=audit
    )


def _result(
    rounds: list[RoundResult],
    *,
    reason: str = "no reproducible secret-disclosure demonstration was observed",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    verdict: Verdict = Verdict.INCONCLUSIVE,
) -> InvestigationResult:
    return InvestigationResult(
        run_id="ledger",
        case_id=_prepared().case_id,
        disposition=Disposition.INCONCLUSIVE,
        verdict=verdict,
        execution_status=status,
        reason=reason,
        manifest=_prepared().manifest,
        rounds=rounds,
    )


def _gates(entries: list[dict]) -> list[tuple[str, str]]:
    return [(entry["stage"], entry["gate"]) for entry in entries]


def _verified(*keys: tuple[int, int]):
    return {key: _prepared() for key in keys}


def test_budget_exhaustion_is_a_policy_stop_after_the_producer_rounds():
    reason = "producer exhausted its LLM-call budget before structured completion"
    result = _result(
        [_round(_invalid(reason)), _round(_invalid(reason), index=2)],
        reason="Investigation budget exhausted.",
    )
    entries = gate_ledger(result)
    assert _gates(entries) == [
        ("producer", "producer_invalid:llm_budget"),
        ("producer", "producer_invalid:llm_budget"),
        ("policy", "budget_exhausted"),
    ]
    assert entries[0] == {
        "session": 1,
        "round": 1,
        "stage": "producer",
        "gate": "producer_invalid:llm_budget",
        "reason": reason,
    }
    assert entries[-1]["round"] is None


def test_producer_invalid_output_and_abstention_are_distinguished():
    abstained = ProducerOutput(
        decision=ProducerDecision(root=NoGroundedCandidate(reason="no grounded seam"))
    )
    result = _result(
        [
            _round(_invalid("producer returned malformed ProducerDecision output")),
            _round(_invalid("plan revision must equal the current round index"), index=2),
            _round(_invalid("unforeseen adapter reason"), index=3),
            _round(abstained, index=4),
        ]
    )
    assert [entry["gate"] for entry in gate_ledger(result)] == [
        "producer_invalid:malformed",
        "producer_invalid:plan_revision",
        "producer_invalid",
        "producer_abstained",
    ]


def test_operational_provider_failure_is_not_repeated_as_a_policy_stop():
    result = _result(
        [_round(_invalid("MAX_TOKENS", gate="provider_permanent", operational=True))],
        reason="MAX_TOKENS",
        status=ExecutionStatus.ERROR,
        verdict=Verdict.ERROR,
    )
    assert _gates(gate_ledger(result)) == [("producer", "provider_permanent")]


def test_audit_reject_stops_an_otherwise_decisive_differential():
    rejected = _audit(AuditDecision.REJECT)
    result = _result([_round(_proposal(), _observation(_HELD, _VIOLATION), rejected)])
    entries = gate_ledger(result, _verified((1, 1)))
    assert _gates(entries) == [("audit", "audit_reject")]
    assert entries[0]["reason"] == "reviewed"


def test_audit_invalid_and_insufficient_context_are_named():
    invalid = AuditOutput(
        feedback=Feedback(
            gate="audit_invalid", reason="auditor returned no structured output", operational=False
        )
    )
    insufficient = _audit(AuditDecision.INSUFFICIENT)
    result = _result(
        [
            _round(_proposal(), _clean_negative(), invalid),
            _round(_proposal(), _clean_negative(), insufficient, index=2),
        ]
    )
    assert [entry["gate"] for entry in gate_ledger(result, _verified((1, 1), (1, 2)))] == [
        "audit_invalid:no_output",
        "audit_insufficient_context",
    ]


def test_operational_evidence_feedback_is_the_evidence_stop():
    blocked = _observation(
        None,
        None,
        cleanup=False,
        feedback=Feedback(gate="sandbox", reason="trusted image check failed", operational=True),
    )
    result = _result(
        [_round(_proposal(), blocked)],
        reason="trusted image check failed",
        status=ExecutionStatus.ERROR,
        verdict=Verdict.ERROR,
    )
    assert _gates(gate_ledger(result)) == [("evidence", "sandbox")]


def test_coverage_gate_miss_is_named_before_the_differential():
    uncovered = _observation(_HELD, _role(RoleOutcome.VIOLATION, [], 1))
    result = _result([_round(_proposal(), uncovered, _audit())])
    entries = gate_ledger(result, _verified((1, 1)))
    assert _gates(entries) == [("kernel", "coverage")]
    assert entries[0]["reason"] == "declared target line not covered in both runs"


def test_invalid_probe_and_missing_differential_are_distinguished():
    invalid = _observation(_HELD, _role(RoleOutcome.INVALID, [4], 0))
    control_failed = _observation(_role(RoleOutcome.VIOLATION, [4], 1), _VIOLATION)
    result = _result(
        [
            _round(_proposal(), invalid, _audit()),
            _round(_proposal(), control_failed, _audit(), index=2),
        ]
    )
    assert _gates(gate_ledger(result, _verified((1, 1), (1, 2)))) == [
        ("evidence", "probe_invalid"),
        ("kernel", "no_differential"),
    ]


def test_demonstration_is_recorded_as_the_final_kernel_gate():
    result = _result(
        [_round(_proposal(), _observation(_HELD, _VIOLATION), _audit())],
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
    )
    assert _gates(gate_ledger(result, _verified((1, 1)))) == [("kernel", "demonstrated")]


def test_unverified_receipts_never_reach_kernel_gates():
    result = _result([_round(_proposal(), _observation(_HELD, _VIOLATION), _audit())])
    assert _gates(gate_ledger(result)) == [("kernel", "evidence_unverified")]


def test_a_lone_clean_negative_names_the_unmet_session_threshold():
    one = _result([_round(_proposal(), _clean_negative(), _audit())])
    entries = gate_ledger(one, _verified((1, 1)))
    assert _gates(entries) == [("kernel", "clean_negative"), ("policy", "negative_threshold_unmet")]
    assert entries[-1]["reason"] == "1 of 2 required independent clean negatives"

    two = _result(
        [
            _round(_proposal(), _clean_negative(), _audit()),
            _round(_proposal(), _clean_negative(), _audit(), session=2),
        ],
        verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
    )
    entries = gate_ledger(two, _verified((1, 1), (2, 1)))
    assert [(entry["session"], entry["gate"]) for entry in entries] == [
        (1, "clean_negative"),
        (2, "clean_negative"),
    ]

    later_demonstration = _result(
        [
            _round(_proposal(), _clean_negative(), _audit()),
            _round(_proposal(), _observation(_HELD, _VIOLATION), _audit(), session=2),
        ],
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
    )
    assert [
        entry["gate"] for entry in gate_ledger(later_demonstration, _verified((1, 1), (2, 1)))
    ] == [
        "clean_negative",
        "demonstrated",
    ]


def test_case_level_failures_without_a_round_stop_are_named():
    activity = _result(
        [_round(_invalid("producer returned no structured ProducerDecision output"))],
        reason="producer: activity timed out",
        status=ExecutionStatus.ERROR,
        verdict=Verdict.ERROR,
    )
    assert _gates(gate_ledger(activity))[-1] == ("policy", "execution_error")
    blocked = _result(
        [], reason="prepare: source denied", status=ExecutionStatus.BLOCKED, verdict=Verdict.ERROR
    )
    assert _gates(gate_ledger(blocked)) == [("policy", "execution_blocked")]
    assert _gates(gate_ledger(_result([], reason="No admissible observation was collected."))) == [
        ("policy", "no_rounds")
    ]


def test_case_level_and_adapter_reasons_still_exist_in_their_sources():
    """The ledger names stops by the fixed strings their owners record; fail loudly
    if a source stops emitting one so a gate cannot silently fall out of the ledger."""
    workflow_source = inspect.getsource(investigation)
    for reason in ledger._BUDGET_REASONS:
        assert f'"{reason}"' in workflow_source
    adapter_source = inspect.getsource(adk)
    for marker, _ in ledger._INVALID_QUALIFIERS:
        assert marker in adapter_source


def test_ledger_counts_are_sorted_by_frequency_then_gate():
    counts = ledger_counts([[{"gate": "b"}, {"gate": "a"}], [{"gate": "b"}], []])
    assert list(counts.items()) == [("b", 2), ("a", 1)]


def test_scored_rows_carry_the_ledger_and_the_report_round_trips(tmp_path, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from tests.unit.test_evaluation import _accept_saved_receipts

    _accept_saved_receipts(monkeypatch)
    store = ArtifactStore(tmp_path / "artifacts")
    oracle = Oracle(acceptable=[Disposition.SUPPORTED])
    rejected = _result(
        [_round(_proposal(), _observation(_HELD, _VIOLATION), _audit(AuditDecision.REJECT))]
    )
    exhausted = _result(
        [_round(_invalid("producer exhausted its tool-call budget before structured completion"))],
        reason="Investigation budget exhausted.",
    )
    scored = score(rejected, oracle, store)
    assert [entry["gate"] for entry in scored["gate_ledger"]] == ["audit_reject"]
    rows = [scored, score(exhausted, oracle, store), {"status": "unavailable", "reason": "lost"}]

    destination = tmp_path / "report.json"
    report = save_report(destination, rows)
    assert json.loads(destination.read_text()) == report
    summary = report["summary"]
    assert summary["gate_ledger"] == {
        "audit_reject": 1,
        "budget_exhausted": 1,
        "producer_invalid:tool_budget": 1,
    }
    assert summary["failure_stops"] == {"audit_reject": 1, "budget_exhausted": 1}
    # Existing summary keys are unchanged.
    assert summary["attempts"] == 3 and summary["unavailable_results"] == 1
    assert summarize(rows) == summary


async def test_report_renders_the_ledger_and_keeps_json_mode(tmp_path, capsys):
    report = tmp_path / "report.json"
    summary = {
        "attempts": 2,
        "failed": 2,
        "gate_ledger": {"producer_invalid:llm_budget": 3, "budget_exhausted": 1},
        "failure_stops": {"budget_exhausted": 1},
        "older_empty": {},
    }
    report.write_text(json.dumps({"rows": [], "summary": summary}))

    assert await execute(parser().parse_args(["--format", "json", "report", str(report)])) == 0
    emitted = json.loads(capsys.readouterr().out)
    # `report` emits the summary or, once the report-compare change lands, the whole report.
    assert emitted.get("summary", emitted) == summary

    human = parser().parse_args(["--format", "human", "--no-color", "report", str(report)])
    assert await execute(human) == 0
    output = capsys.readouterr().out
    assert "Gate ledger" in output and "Failure stops" in output
    assert "producer_invalid:llm_budget" in output
    assert "older empty" in output and "none" in output
