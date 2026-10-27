"""Gym run identity and operational-stop visibility: observations, never a decision input."""

import json

import pytest

from corsair.contracts import (
    Disposition,
    GateDecision,
    GateReason,
    InvestigationResult,
    OperationalReason,
    Oracle,
    RoleOutcome,
    RoundSummary,
    RunContext,
    RunIdentity,
    RunManifest,
    Scorecard,
    Trajectory,
    Verdict,
)
from corsair.evaluation.gym.gate import gate, identity_changes
from corsair.evaluation.gym.render import render_gate, render_scorecard
from corsair.evaluation.gym.scoring import build_scorecard, operational_stop, trajectory
from tests.unit.evaluation.test_gym_gate import BASELINE as BASELINE_CLI

KIND = "java.xxe/1"
ORACLE = Oracle(
    acceptable=[Disposition.SUPPORTED, Disposition.INCONCLUSIVE],
    expected_verdict=Verdict.EXPLOIT_DEMONSTRATED,
)
HEARTBEAT = [
    {
        "session": 1,
        "round": 1,
        "stage": "evidence",
        "gate": "evidence_not_run",
        "reason": "no observation was recorded",
    },
    {
        "session": 1,
        "round": None,
        "stage": "policy",
        "gate": "execution_error",
        "reason": "evidence: activity Heartbeat timeout",
    },
]
PAYLOAD_ERROR = [
    {
        "session": 1,
        "round": 1,
        "stage": "kernel",
        "gate": "evidence_unverified",
        "reason": "the round's persisted receipts did not validate",
    },
    {
        "session": 1,
        "round": None,
        "stage": "policy",
        "gate": "execution_error",
        "reason": "trusted probe execution errored",
    },
]


def _entry(gate: str, reason: str = "x", stage: str = "producer", round_index=1) -> dict:
    return {"session": 1, "round": round_index, "stage": stage, "gate": gate, "reason": reason}


def _failed(ledger: list[dict], **update) -> dict:
    row = {
        "run_id": "run-1",
        "case_id": "java-xxe-b",
        "status": "fail",
        "verdict": "ERROR",
        "disposition": "INCONCLUSIVE",
        "execution_status": "ERROR",
        "input_tokens": 1000,
        "output_tokens": 100,
        "agent_seconds": 10.0,
        "gate_ledger": ledger,
    }
    row.update(update)
    return row


def _round(**update) -> RoundSummary:
    return RoundSummary(session=1, index=1, **update)


# The operational-reason rule


@pytest.mark.parametrize(
    ("ledger", "reason"),
    [
        (HEARTBEAT, OperationalReason.HEARTBEAT_TIMEOUT),
        (
            [HEARTBEAT[0], {**HEARTBEAT[1], "reason": "evidence: activity StartToClose timeout"}],
            OperationalReason.ACTIVITY_TIMEOUT,
        ),
        ([_entry("episode_timeout")], OperationalReason.EPISODE_TIMEOUT),
        ([_entry("provider_temporary", stage="audit")], OperationalReason.PROVIDER_TEMPORARY),
        (
            [_entry("operation-reconciliation", stage="evidence")],
            OperationalReason.OPERATION_RECONCILIATION,
        ),
        (
            [_entry("clean_negative", stage="kernel"), _entry("provider_temporary", round_index=2)]
            + [_entry("negative_threshold_unmet", stage="policy", round_index=None)],
            OperationalReason.PROVIDER_TEMPORARY,
        ),
        (
            [_entry("execution_cancelled", "Run cancelled.", "policy", None)],
            OperationalReason.EXECUTION_CANCELLED,
        ),
        (
            [HEARTBEAT[0], {**HEARTBEAT[1], "reason": "evidence: worker raised"}],
            OperationalReason.EVIDENCE_NOT_RUN,
        ),
    ],
)
def test_code_owned_operational_stops_are_named(ledger, reason):
    assert operational_stop(_failed(ledger), []) is reason


@pytest.mark.parametrize(
    "ledger",
    [
        [_entry("provider_max_tokens")],
        [_entry("producer_abstained", "model-authored prose mentioning a Heartbeat timeout")],
        [_entry("audit_reject", stage="audit")],
        [_entry("coverage", stage="kernel")],
        [_entry("packet_too_large")],
        [_entry("provider_permanent")],
        [_entry("producer_invalid:llm_budget")],
        # A missing observation is operational only when the workflow recorded a stop.
        [HEARTBEAT[0], _entry("budget_exhausted", stage="policy", round_index=None)],
        # An earlier operational round does not explain a later behavioural stop.
        [_entry("provider_temporary"), _entry("audit_reject", stage="audit", round_index=2)],
        [],
    ],
)
def test_behavioural_stops_stay_behavioural(ledger):
    assert operational_stop(_failed(ledger), []) is None


def test_a_payload_level_execution_error_with_a_role_error_is_behavioural():
    errored = _round(control_outcome=RoleOutcome.HELD, adversarial_outcome=RoleOutcome.ERROR)
    assert operational_stop(_failed(PAYLOAD_ERROR), [errored]) is None
    # Even a timeout reason does not override a recorded role error.
    assert operational_stop(_failed(HEARTBEAT), [errored]) is None


def test_passed_rows_are_never_operational_and_unavailable_rows_always_are():
    assert operational_stop(_failed(HEARTBEAT, status="pass"), []) is None
    unavailable = {"run_id": "r", "case_id": "c", "status": "unavailable", "reason": "lost"}
    assert operational_stop(unavailable, []) is OperationalReason.RESULT_UNAVAILABLE


def test_an_operational_episode_keeps_its_error_reward():
    scored = trajectory(_failed(HEARTBEAT), 1, KIND, ORACLE, None, None)
    plain = trajectory(_failed(PAYLOAD_ERROR), 1, KIND, ORACLE, None, None)
    assert (scored.operational, scored.operational_reason) == (
        True,
        OperationalReason.HEARTBEAT_TIMEOUT,
    )
    assert (plain.operational, plain.operational_reason) == (False, None)
    assert scored.reward_verdict == plain.reward_verdict == -0.5
    assert scored.reward == plain.reward
    assert scored.failure_stop == plain.failure_stop == "execution_error"


def test_a_trajectory_reason_and_flag_must_agree():
    with pytest.raises(ValueError, match="operational"):
        Trajectory(
            run_id="r",
            case_id="c",
            repeat=0,
            kind=KIND,
            language="java",
            status="fail",
            passed=False,
            verified=False,
            false_label=False,
            usage_known=False,
            reward_verdict=-0.5,
            reward=-0.5,
            operational=True,
        )


# Run identity read from the stored result


def _manifest(**update) -> RunManifest:
    def role(name: str, prompt: str) -> dict:
        return {
            "spec_digest": f"{name}-spec",
            "instruction_digest": prompt,
            "output_schema_digest": f"{name}-schema",
            "runtime_skills_digest": f"{name}-skills",
            "risk_assessment_digest": "risk",
            "budget_policy_digest": "budget",
            "execution_class": "durable",
            "governance_tier": "review",
            "tools": [],
        }

    fields = {
        "package_version": "0.1.0",
        "request_digest": "1" * 64,
        "config_digest": "2" * 64,
        "producer_prompt_digest": "3" * 64,
        "auditor_prompt_digest": "4" * 64,
        "image_id": "sha256:java",
        "models": {"producer": "model-p", "auditor": "model-a"},
        "capabilities": {
            "producer": role("producer", "3" * 64),
            "auditor": role("auditor", "4" * 64),
        },
    }
    fields.update(update)
    return RunManifest.model_validate(fields)


def _result(manifest: RunManifest) -> InvestigationResult:
    return InvestigationResult(
        run_id="run-1",
        case_id="java-xxe-b",
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.ERROR,
        execution_status="ERROR",
        reason="evidence: activity Heartbeat timeout",
        manifest=manifest,
    )


def test_a_trajectory_carries_the_full_manifest_identity():
    scored = trajectory(_failed(HEARTBEAT), 0, KIND, ORACLE, _result(_manifest()), None)
    assert scored.run_identity == RunIdentity(
        package_version="0.1.0",
        config="2" * 64,
        producer_prompt="3" * 64,
        auditor_prompt="4" * 64,
        producer_spec="producer-spec",
        auditor_spec="auditor-spec",
        producer_output_schema="producer-schema",
        auditor_output_schema="auditor-schema",
        producer_skills="producer-skills",
        auditor_skills="auditor-skills",
        risk_assessment="risk",
        budget_policy="budget",
        image="sha256:java",
        producer_model="model-p",
        auditor_model="model-a",
    )
    # The existing per-trajectory identity map is unchanged.
    assert scored.identity == {
        "config": "2" * 64,
        "request": "1" * 64,
        "producer_prompt": "3" * 64,
        "auditor_prompt": "4" * 64,
    }


def test_a_manifest_without_capabilities_leaves_role_digests_unknown():
    scored = trajectory(
        _failed(HEARTBEAT), 0, KIND, ORACLE, _result(_manifest(capabilities={})), None
    )
    assert scored.run_identity is not None
    assert scored.run_identity.producer_skills is None
    assert scored.run_identity.config == "2" * 64
    assert trajectory(_failed(HEARTBEAT), 0, KIND, ORACLE, None, None).run_identity is None


# Scorecard aggregates

CASES = {"py-a": "python.k/1", "jv-a": "java.k/1", "pl-a": "perl.k/1"}


def _episode(
    case: str,
    repeat: int,
    outcome: str,
    identity: RunIdentity | None = None,
) -> Trajectory:
    """``outcome`` is ``pass``, ``fail`` (behavioural) or ``op`` (heartbeat timeout)."""
    passed = outcome == "pass"
    operational = outcome == "op"
    kind = CASES[case]
    return Trajectory(
        run_id=f"{case}-{repeat}",
        case_id=case,
        repeat=repeat,
        kind=kind,
        language=kind.split(".")[0],
        status="pass" if passed else "fail",
        passed=passed,
        verified=passed,
        false_label=False,
        failure_stop=None if passed else ("execution_error" if operational else "audit_reject"),
        usage_known=True,
        effective_tokens=100.0,
        seconds=10.0,
        reward_verdict=1.0 if passed else (-0.5 if operational else 0.0),
        reward=1.0 if passed else (-0.5 if operational else 0.0),
        operational=operational,
        operational_reason=OperationalReason.HEARTBEAT_TIMEOUT if operational else None,
        run_identity=identity,
    )


def _card(outcomes: dict[str, list[str]], run_id: str, identity=None) -> Scorecard:
    rows = [
        _episode(case, repeat, outcome, identity(case) if identity else None)
        for case, items in outcomes.items()
        for repeat, outcome in enumerate(items)
    ]
    return build_scorecard(
        rows, run=RunContext(run_id=run_id), dataset_digest="d" * 64, cases=CASES
    )


ALL = ["pass", "pass", "pass"]
BASELINE = {"py-a": ALL, "jv-a": ALL, "pl-a": ALL}


def test_scorecard_counts_and_lists_operational_episodes_per_language():
    card = _card({"py-a": ALL, "jv-a": ["op", "op", "op"], "pl-a": ["op", "fail", "pass"]}, "c")
    assert card.languages["java"].operational_episodes == 3
    assert card.languages["perl"].operational_episodes == 1
    assert card.languages["python"].operational_episodes == 0
    assert card.kinds["java.k/1"].operational_episodes == 3
    assert card.operational_episodes == 4
    assert [(item.case_id, item.repeat, item.reason) for item in card.operational_stops] == [
        ("jv-a", 0, OperationalReason.HEARTBEAT_TIMEOUT),
        ("jv-a", 1, OperationalReason.HEARTBEAT_TIMEOUT),
        ("jv-a", 2, OperationalReason.HEARTBEAT_TIMEOUT),
        ("pl-a", 0, OperationalReason.HEARTBEAT_TIMEOUT),
    ]
    # Verified accuracy and reward are unchanged; the counterfactual is beside them.
    assert card.languages["java"].verified_accuracy == 0.0
    assert card.languages["java"].mean_reward == -0.5
    assert card.languages["java"].verified_accuracy_without_operational_failures == 1.0
    assert card.languages["perl"].verified_accuracy == 0.0
    assert card.languages["perl"].verified_accuracy_without_operational_failures == 1.0


def test_a_scorecard_written_before_the_fields_reads_them_as_unknown():
    card = _card(BASELINE, "old")
    data = card.model_dump(mode="json")
    for name in ("run_identity", "operational_episodes", "operational_stops"):
        data.pop(name)
    for group in (*data["languages"].values(), *data["kinds"].values()):
        group.pop("operational_episodes")
        group.pop("verified_accuracy_without_operational_failures")
    old = Scorecard.model_validate(data)
    assert old.operational_episodes is None
    assert old.languages["java"].operational_episodes is None
    assert old.run_identity == {}
    assert "- Operational episodes: unknown" in render_scorecard(old)


SAME, NEW = "e" * 64, "f" * 64


def _identity(**update) -> RunIdentity:
    fields = dict.fromkeys(RunIdentity.model_fields, SAME)
    fields.update(update)
    return RunIdentity(**fields)


def test_scorecard_aggregates_each_identity_component():
    card = _card(
        BASELINE,
        "c",
        identity=lambda case: _identity(image=f"sha256:{case}", producer_skills="skills-1"),
    )
    assert card.run_identity["image"] == ["sha256:jv-a", "sha256:pl-a", "sha256:py-a"]
    assert card.run_identity["producer_skills"] == ["skills-1"]
    assert card.run_identity["config"] == [SAME]
    # The existing config-digest list is still read from ``identity["config"]`` only.
    assert card.identity_digests == []


# Gate: identity changes and operational confounding never change the decision


def test_identity_changes_are_reported_per_component_without_changing_the_gate():
    before = _card(BASELINE, "base", identity=lambda case: _identity())
    after = _card(
        BASELINE,
        "cand",
        identity=lambda case: _identity(producer_prompt=NEW, producer_skills=NEW),
    )
    verdict = gate(before, after)
    plain = gate(before, _card(BASELINE, "cand", identity=lambda case: _identity()))
    assert verdict.identity_changes["producer_prompt"] is True
    assert verdict.identity_changes["producer_skills"] is True
    assert verdict.identity_changes["config"] is False
    assert set(verdict.identity_changes) == set(RunIdentity.model_fields)
    assert (verdict.decision, verdict.reasons) == (plain.decision, plain.reasons)
    unknown = identity_changes(_card(BASELINE, "old"), after)
    assert set(unknown.values()) == {None}
    text = render_gate(verdict, before, after)
    assert "Identity changes: producer_prompt, producer_skills" in text
    assert "Identity changes: none" in render_gate(plain, before, before)
    old = _card(BASELINE, "o")
    assert "Identity changes: none; unknown: " + ", ".join(RunIdentity.model_fields) in (
        render_gate(gate(old, after), old, after)
    )


def test_a_regression_made_only_of_operational_stops_is_rejected_as_confounded():
    candidate = _card(
        {"py-a": ALL, "jv-a": ["op", "op", "op"], "pl-a": ["op", "fail", "pass"]}, "c"
    )
    verdict = gate(_card(BASELINE, "base"), candidate)
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.exit_code == 1
    assert verdict.regressed_languages == ["java", "perl"]
    assert verdict.operationally_confounded_languages == ["java", "perl"]
    assert verdict.reasons[:2] == [
        GateReason.LANGUAGE_REGRESSED,
        GateReason.OPERATIONALLY_CONFOUNDED,
    ]
    assert verdict.language_deltas["java"] == -1.0
    text = render_gate(verdict, _card(BASELINE, "base"), candidate)
    assert "Operationally confounded: java, perl" in text
    assert "| Baseline operational eps | Candidate operational eps | Operational delta |" in text
    assert (
        "| java | 1.000 | 0.000 | -1.000 | yes | unknown | unknown | unknown | 0 | 3 | +3 "
        "| 0 | 0 | +0 | yes |" in (text)
    )


def test_a_regression_with_behavioural_failures_is_not_confounded():
    candidate = _card({"py-a": ALL, "jv-a": ["op", "fail", "fail"], "pl-a": ALL}, "c")
    verdict = gate(_card(BASELINE, "base"), candidate)
    assert verdict.decision is GateDecision.REJECTED
    assert verdict.regressed_languages == ["java"]
    assert verdict.operationally_confounded_languages == []
    assert GateReason.OPERATIONALLY_CONFOUNDED not in verdict.reasons


def test_incomparable_gates_name_no_confounding():
    candidate = _card({"py-a": ALL, "jv-a": ["op", "op", "op"], "pl-a": ALL}, "c")
    candidate = candidate.model_copy(update={"sliced": True})
    verdict = gate(_card(BASELINE, "base"), candidate)
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.operationally_confounded_languages == []


def test_scorecard_view_lists_operational_stops():
    card = _card({"py-a": ALL, "jv-a": ["op", "pass", "pass"], "pl-a": ALL}, "c")
    text = render_scorecard(card)
    assert "- Operational episodes: 1" in text
    assert "| Failure stops | Operational eps |" in text
    assert "- `jv-a` repeat 0: heartbeat_timeout" in text
    assert "- Operational episodes: 0" in render_scorecard(_card(BASELINE, "b"))


# Smoke gate: the objective margin is reported but does not decide


def _tokens(card: Scorecard, tokens: float) -> Scorecard:
    return card.model_copy(update={"macro_effective_tokens": tokens})


def test_smoke_mode_passes_a_small_objective_change_without_regression():
    baseline = _card(BASELINE, "base")
    candidate = _card(BASELINE, "cand")
    default = gate(baseline, candidate)
    smoke = gate(baseline, candidate, smoke=True)
    assert default.decision is GateDecision.REJECTED
    assert default.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD]
    assert default.smoke is False
    assert smoke.decision is GateDecision.ACCEPTED
    assert smoke.exit_code == 0
    assert smoke.reasons == [GateReason.OBJECTIVE_BELOW_THRESHOLD]
    assert smoke.smoke is True
    text = render_gate(smoke, baseline, candidate)
    assert text.startswith("## Gate (smoke): ACCEPTED\n")
    assert "not an acceptance" in text
    assert "smoke" not in render_gate(default, baseline, candidate).splitlines()[0]


def test_smoke_mode_still_rejects_a_language_regression_and_a_token_breach():
    baseline = _card(BASELINE, "base")
    regressed = _card({**BASELINE, "jv-a": ["fail", "fail", "pass"]}, "cand")
    verdict = gate(baseline, regressed, smoke=True)
    assert verdict.decision is GateDecision.REJECTED
    assert GateReason.LANGUAGE_REGRESSED in verdict.reasons
    costly = gate(baseline, _tokens(_card(BASELINE, "cand"), 111.0), smoke=True)
    assert costly.decision is GateDecision.REJECTED
    assert costly.reasons == [
        GateReason.OBJECTIVE_BELOW_THRESHOLD,
        GateReason.TOKENS_ABOVE_CEILING,
    ]


def test_smoke_mode_keeps_every_incomparable_condition():
    candidate = _card(BASELINE, "cand").model_copy(update={"sliced": True})
    verdict = gate(_card(BASELINE, "base"), candidate, smoke=True)
    assert verdict.decision is GateDecision.INCOMPARABLE
    assert verdict.exit_code == 2


@pytest.mark.asyncio
async def test_the_gate_command_takes_smoke(tmp_path, capsys):
    from tests.unit.test_gym_cli import _arguments, _run
    from tests.unit.test_gym_cli import _card as _cli_card

    baseline = _cli_card(tmp_path / "base.json", BASELINE_CLI, run_id="base")
    argv = ("gym", "gate", "--baseline", str(baseline), "--candidate", str(baseline))
    assert await _run(_arguments(*argv)) == 1
    capsys.readouterr()
    assert await _run(_arguments(*argv, "--smoke")) == 0
    verdict = json.loads(capsys.readouterr().out)
    assert (verdict["decision"], verdict["smoke"]) == ("ACCEPTED", True)
    assert verdict["reasons"] == ["objective_below_threshold"]
