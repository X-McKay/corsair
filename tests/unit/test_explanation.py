"""Plain-language verdict explanation over synthetic results and their gate ledgers."""

from __future__ import annotations

import inspect
import json

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditOutput,
    AuditResult,
    AuditRule,
    Budget,
    Disposition,
    EvidenceInput,
    ExecutionStatus,
    Feedback,
    FixStatus,
    InvestigationResult,
    ProducerDecision,
    ProducerOutput,
    RoleOutcome,
    RoundResult,
    Scope,
    Verdict,
)
from corsair.entrypoints.cli import execute, parser
from corsair.evaluation.ledger import gate_ledger
from corsair.policies import explanation
from corsair.policies.explanation import explain_result
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.unit.test_evidence import _FakeSandbox, _prepared, _submission
from tests.unit.test_gate_ledger import _invalid, _proposal, _result, _round, _verified
from tests.unit.test_runs import PRIVATE, _settings_for
from tests.unit.test_verdicts import _HELD, _VIOLATION, _clean_negative, _observation, _role

# Model-authored or free-text fields that must never appear in an explanation.
AUDIT_REASON = "auditor-private-reason-7f3"
ABSTENTION = "producer-private-abstention-7f3"
FEEDBACK = "adapter-private-feedback-7f3"
RESULT_REASON = "result-private-reason-7f3"
MARKERS = (AUDIT_REASON, ABSTENTION, FEEDBACK, RESULT_REASON, *PRIVATE)


def _audit(decision: AuditDecision = AuditDecision.ACCEPT) -> AuditOutput:
    # The rule is a closed rubric id bound to the decision, so it carries no model text.
    rule = AuditRule.ALL if decision is AuditDecision.ACCEPT else AuditRule.R1
    return AuditOutput(review=AuditResult(decision=decision, rule=rule, reason=AUDIT_REASON))


def _explain(result: InvestigationResult, *keys: tuple[int, int]) -> list[dict]:
    return explain_result(result, gate_ledger(result, _verified(*keys)))


def _kinds(statements: list[dict]) -> list[str]:
    return [statement["kind"] for statement in statements]


def _texts(statements: list[dict], kind: str) -> list[str]:
    return [statement["text"] for statement in statements if statement["kind"] == kind]


def _assert_private(statements: list[dict]) -> None:
    rendered = json.dumps(statements)
    for marker in MARKERS:
        assert marker not in rendered, marker


def _distinct_proposal() -> ProducerOutput:
    """A second candidate on a different exploit payload: only distinct candidates count."""
    submission = _submission().model_copy(update={"exploit_payload": "../other/secret.txt"})
    return ProducerOutput(decision=ProducerDecision(kind="proposal", submission=submission))


def test_exploit_demonstrated_names_the_rule_and_the_only_thing_that_withholds_it():
    result = _result(
        [_round(_proposal(), _observation(_HELD, _VIOLATION), _audit())],
        reason=RESULT_REASON,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
    )
    statements = _explain(result, (1, 1))

    assert _kinds(statements) == [
        "verdict",
        "rule",
        "session",
        "session",
        "policy",
        "policy",
        "fix",
        "change",
        "change",
    ]
    assert statements[0]["text"].startswith("Verdict EXPLOIT_DEMONSTRATED: execution COMPLETED")
    assert "control held and the exploit violated" in statements[1]["text"]
    facts = _texts(statements, "session")
    assert facts[0] == (
        "Session 1: 1 round(s), stopped at demonstrated. Last evaluated round 1: control held,"
        " exploit violated, target line covered in both runs: yes, audit ACCEPT."
    )
    assert "differential on the vulnerable revision" in facts[1]
    changes = _texts(statements, "change")
    assert "NOT_BLOCKED" in changes[0] and "INCONCLUSIVE" in changes[0]
    assert "optional confirmation" in changes[1]
    _assert_private(statements)


def test_component_exploit_demonstrated_points_at_the_claimed_scope():
    application = _prepared().model_copy(
        update={
            "finding": _prepared().finding.model_copy(update={"claim_scope": Scope.APPLICATION})
        }
    )
    result = _result(
        [_round(_proposal(), _observation(_HELD, _VIOLATION), _audit())],
        verdict=Verdict.COMPONENT_EXPLOIT_DEMONSTRATED,
    ).model_copy(update={"scope": Scope.APPLICATION})
    statements = explain_result(result, gate_ledger(result, {(1, 1): application}))

    assert "claimed scope application" in statements[0]["text"]
    assert "component seam" in _texts(statements, "rule")[0]
    assert "at component scope" in _texts(statements, "session")[1]
    changes = _texts(statements, "change")
    assert "claims component scope" in changes[0]
    assert changes[1].startswith("Developer next step: harden the component")
    assert "NOT_BLOCKED" in changes[2]


def test_exploit_not_demonstrated_counts_clean_negatives_against_the_threshold():
    result = _result(
        [
            _round(_proposal(), _clean_negative(), _audit()),
            _round(_distinct_proposal(), _clean_negative(), _audit(), session=2),
        ],
        verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
    )
    statements = _explain(result, (1, 1), (2, 1))

    assert _texts(statements, "session")[1] == "Session 1 ended in a clean negative."
    assert _texts(statements, "session")[3] == "Session 2 ended in a clean negative."
    assert _texts(statements, "policy")[0] == (
        "Evidence policy: 2 independent clean negatives required for EXPLOIT_NOT_DEMONSTRATED,"
        " at most 2 session(s). 2 session(s) ran and 2 clean negative(s) were reached."
    )
    changes = _texts(statements, "change")
    assert "would make it EXPLOIT_DEMONSTRATED" in changes[0]
    assert "not a refutation" in changes[1]
    assert "shortfall" not in _kinds(statements)


def test_exploit_not_demonstrated_rule_states_the_component_seam_whatever_the_claim():
    for scope in (Scope.COMPONENT, Scope.APPLICATION):
        result = _result(
            [
                _round(_proposal(), _clean_negative(), _audit()),
                _round(_proposal(), _clean_negative(), _audit(), session=2),
            ],
            verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
        ).model_copy(update={"scope": scope})
        [rule] = _texts(_explain(result, (1, 1), (2, 1)), "rule")

        assert (
            "at the component seam only, for the exercised payloads, revision and runtime" in rule
        )


def test_inconclusive_names_the_single_fact_that_fell_short_per_session():
    uncovered = _observation(_HELD, _role(RoleOutcome.VIOLATION, [], 1))
    result = _result(
        [
            _round(_proposal(), uncovered, _audit()),
            _round(
                _proposal(), _observation(_HELD, _VIOLATION), _audit(AuditDecision.REJECT), index=2
            ),
        ],
        reason=RESULT_REASON,
    )
    statements = _explain(result, (1, 1), (1, 2))

    facts = _texts(statements, "session")[0]
    assert "stopped at coverage, audit_reject" in facts
    assert "Last evaluated round 2: control held, exploit violated" in facts
    assert "covered in both runs: yes, audit REJECT" in facts
    shortfall = [item for item in statements if item["kind"] == "shortfall"]
    assert shortfall == [
        {
            "kind": "shortfall",
            "session": 1,
            "gate": "audit_reject",
            "text": "Session 1 fell short at audit_reject: the blind audit rejected the pair.",
        }
    ]
    changes = _texts(statements, "change")
    assert changes[0] == "Session 1 needed a blind audit that accepts the pair."
    assert changes[-1] == explanation._SESSION_REQUIREMENT
    _assert_private(statements)


def test_inconclusive_coverage_miss_reports_the_uncovered_line_fact():
    uncovered = _observation(_HELD, _role(RoleOutcome.VIOLATION, [], 1))
    result = _result([_round(_proposal(), uncovered, _audit())])
    statements = _explain(result, (1, 1))

    assert "covered in both runs: no" in _texts(statements, "session")[0]
    assert (
        "did not execute in both the control and the exploit run"
        in (_texts(statements, "shortfall")[0])
    )


def test_lone_clean_negative_says_how_many_more_sessions_and_why_none_ran():
    result = _result(
        [_round(_proposal(), _clean_negative(), _audit())],
        reason="Investigation budget exhausted.",
    )
    statements = _explain(result, (1, 1))

    assert "1 session(s) ran and 1 clean negative(s)" in _texts(statements, "policy")[0]
    assert any(item["gate"] == "budget_exhausted" for item in statements)
    threshold = next(item for item in statements if item["gate"] == "negative_threshold_unmet")
    assert threshold["kind"] == "change"
    assert threshold["text"].startswith(
        "1 more independent clean-negative session(s) would make it EXPLOIT_NOT_DEMONSTRATED;"
    )
    assert "budget ran out before another session" in threshold["text"]


def test_lone_clean_negative_flags_a_session_cap_below_the_threshold():
    manifest = _prepared().manifest.model_copy(update={"negative_threshold": 3, "max_sessions": 1})
    result = _result([_round(_proposal(), _clean_negative(), _audit())]).model_copy(
        update={"manifest": manifest}
    )
    statements = _explain(result, (1, 1))

    threshold = next(item for item in statements if item["gate"] == "negative_threshold_unmet")
    assert threshold["text"].startswith("2 more independent clean-negative session(s)")
    assert "can never reach EXPLOIT_NOT_DEMONSTRATED" in threshold["text"]


def test_fixed_revision_not_blocked_withholds_the_demonstration():
    result = _result(
        [_round(_proposal(), _observation(_HELD, _VIOLATION), _audit())],
    ).model_copy(update={"fix_status": FixStatus.NOT_BLOCKED})
    statements = _explain(result, (1, 1))

    assert "fix NOT_BLOCKED" in statements[0]["text"]
    assert "exploit still violated" in _texts(statements, "fix")[0]
    withheld = next(item for item in statements if item["gate"] == "fix_not_blocked")
    assert withheld["kind"] == "change"
    assert "DEMONSTRATION_BLOCKED" in withheld["text"]
    assert withheld["text"].endswith("would let it stand as EXPLOIT_DEMONSTRATED.")


def test_unable_to_run_names_the_blocking_gate():
    result = _result(
        [],
        reason=RESULT_REASON,
        status=ExecutionStatus.BLOCKED,
        verdict=Verdict.UNABLE_TO_RUN,
    )
    statements = _explain(result)

    assert _texts(statements, "shortfall") == [
        "No round ran: an operational gate blocked the run (for example target binding, source "
        "admission or build replay)."
    ]
    assert "0 session(s) ran" in _texts(statements, "policy")[0]
    change = next(item for item in statements if item["kind"] == "change")
    assert change["gate"] == "execution_blocked"
    assert "Rerunning the same request reproduces the stop" in change["text"]
    _assert_private(statements)


def test_error_names_the_operational_evidence_stop():
    blocked = _observation(
        None,
        None,
        cleanup=False,
        feedback=Feedback(gate="sandbox", reason=FEEDBACK, operational=True),
    )
    result = _result(
        [_round(_proposal(), blocked)],
        reason=FEEDBACK,
        status=ExecutionStatus.ERROR,
        verdict=Verdict.ERROR,
    )
    statements = _explain(result)

    assert _texts(statements, "shortfall") == [
        "Session 1 fell short at sandbox: the evidence stage stopped at gate sandbox."
    ]
    change = _texts(statements, "change")[0]
    assert "no security signal" in change and "at sandbox" in change
    _assert_private(statements)


def test_producer_stops_are_explained_without_their_reasons():
    abstained = ProducerOutput(
        decision=ProducerDecision(kind="no_grounded_candidate", reason=ABSTENTION)
    )
    result = _result(
        [
            _round(_invalid(f"producer exhausted its LLM-call budget {FEEDBACK}")),
            _round(abstained, index=2),
        ],
        reason=f"Producer abstained: {ABSTENTION}",
    )
    statements = _explain(result)

    assert (
        "stopped at producer_invalid:llm_budget, producer_abstained"
        in (_texts(statements, "session")[0])
    )
    assert "No round reached both evidence and audit" in _texts(statements, "session")[0]
    assert _texts(statements, "shortfall") == [
        "Session 1 fell short at producer_abstained: the producer abstained instead of "
        "proposing a payload pair."
    ]
    _assert_private(statements)


def test_every_verdict_has_a_rule_and_every_fix_status_has_text():
    assert set(explanation._RULES) == set(Verdict)
    assert set(explanation._FIX_TEXT) == set(FixStatus)


def test_explanation_never_reads_free_text_fields():
    """Only fixed text, enums, counts and gate names reach a statement."""
    source = inspect.getsource(explanation)
    for field in ('["reason"]', ".reason", ".hypothesis", ".plan", ".rule", "_payload"):
        assert field not in source, field


def _commit_audited_run(store: ArtifactStore, run_id: str) -> InvestigationResult:
    prepared = _prepared().model_copy(update={"source": store.put(b"source", "application/x-tar")})
    submission = _submission()
    observation = EvidenceVerifier(Settings(), store, _FakeSandbox(store)).evaluate(
        EvidenceInput(
            run_id=run_id,
            operation_id=f"{run_id}.r1",
            prepared=prepared,
            submission=submission,
            budget=Budget(probe_timeout_seconds=5),
        )
    )
    result = InvestigationResult(
        run_id=run_id,
        case_id=prepared.case_id,
        disposition=Disposition.SUPPORTED,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
        execution_status=ExecutionStatus.COMPLETED,
        reason=AUDIT_REASON,
        manifest=prepared.manifest,
        rounds=[
            RoundResult(
                index=1,
                producer=ProducerOutput(
                    decision=ProducerDecision(kind="proposal", submission=submission)
                ),
                observation=observation,
                audit=_audit(),
            )
        ],
    )
    store.commit(f"result.{run_id}", store.put_json(result))
    return result


async def test_explain_command_and_inspect_flag_render_json_and_human(
    tmp_path, monkeypatch, capsys
):
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_audited_run(store, "run-x")
    _settings_for(store, monkeypatch)

    assert await execute(parser().parse_args(["--format", "json", "explain", "run-x"])) == 0
    view = json.loads(capsys.readouterr().out)
    assert (view["run_id"], view["verdict"]) == ("run-x", "EXPLOIT_DEMONSTRATED")
    # The saved receipts re-validate, so the kernel gates are named, not evidence_unverified.
    assert "stopped at demonstrated" in view["statements"][2]["text"]
    _assert_private(view["statements"])

    inspect_args = ["--format", "json", "inspect", "run-x", "--explain"]
    assert await execute(parser().parse_args(inspect_args)) == 0
    combined = json.loads(capsys.readouterr().out)
    assert combined["result"]["run_id"] == "run-x"
    assert combined["statements"] == view["statements"]

    for command in (["explain", "run-x"], ["inspect", "run-x", "--explain"]):
        human = parser().parse_args(["--format", "human", "--no-color", *command])
        assert await execute(human) == 0
        output = capsys.readouterr().out
        # inspect prints the existing result panel first; the explanation panel follows it.
        explained = output[output.index("Why EXPLOIT_DEMONSTRATED") :]
        assert "change" in explained
        for marker in MARKERS:
            assert marker not in explained, marker
    assert "Corsair · Investigation" in output


@pytest.mark.parametrize(
    ("flags", "message"),
    [(["--online"], "--explain reads the artifact store"), (["--evidence"], "separate views")],
)
async def test_inspect_explain_rejects_incompatible_views(flags, message):
    with pytest.raises(ValueError, match=message):
        await execute(parser().parse_args(["inspect", "run1", "--explain", *flags]))


async def test_explain_without_a_committed_result_names_the_missing_receipt(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    _settings_for(store, monkeypatch)

    with pytest.raises(ValueError, match="No committed result"):
        await execute(parser().parse_args(["explain", "absent"]))


def test_explain_command_loads_no_temporal_sdk(tmp_path):
    from tests.unit.test_terminal import _loads, _modules_loaded_by_cli

    modules = _modules_loaded_by_cli(tmp_path, "--format", "json", "explain", "absent")

    assert _loads(modules, "corsair.policies.explanation")
    for prefix in ("temporalio", "google.adk", "corsair.workflows"):
        assert not _loads(modules, prefix), prefix
