from __future__ import annotations

import pytest
from pydantic import ValidationError

from corsair.v2.contracts import (
    ArtifactRef, Citation, CommandResult, InvestigationPlan, ProbeObservation, ProbeSpec,
    ProbeValidity, ReportSelector, RevisionExecution, RunSpec, SourceRequest, TestRecipe,
    ValidityReview,
)
from corsair.v2.verdict import decide


@pytest.fixture
def evidence():
    citation = Citation(path="application.py", start_line=1, end_line=8)
    def spec(role):
        path = "tests/test_" + role + ".py"
        return ProbeSpec(role=role, path=path, test_id=path + "::test_" + role,
                         selector=ReportSelector(name="test_" + role, classname="tests.test_" + role),
                         objective="Exercise the actual application seam", input_description="Declared fixture input",
                         expected_safe_behavior="Application respects the boundary", citations=(citation,))
    plan = InvestigationPlan(status="planned", summary="Native pair", target_citations=(citation,),
                             control=spec("control"), security=spec("security"),
                             recipe=TestRecipe(report_format="junit", discovery_command=("pytest", "--collect-only"),
                                               execution_command=("pytest",), report_path="report.xml"))
    validity = ProbeValidity(source_binding=True, reaches_condition=True, relevant_assertion=True,
                             doubles_preserve_production_logic=True, citations=(citation,), rationale="Source reviewed")
    review = ValidityReview(control=validity, security=validity, recipe_valid=True,
                            recipe_rationale="Native discovery and execution select the two real source-bound tests")
    ref = ArtifactRef(sha256="a" * 64, size=100)
    command = CommandResult(operation_id="execution", sandbox_id="native-sandbox-id", status="completed",
                            exit_code=1, duration_seconds=1)
    base = RevisionExecution(revision="baseline", source_manifest=ref, pair_sha256="b" * 64,
                             image="image@sha256:" + "c" * 64, policy_sha256="d" * 64,
                             sandbox_id="native-sandbox-id", discovery_ok=True,
                             observations=(ProbeObservation(test_id=plan.control.test_id, outcome="passed"),
                                           ProbeObservation(test_id=plan.security.test_id, outcome="failed", failure_type="assertion")),
                             execution_status="completed", commands=(command,), report_ref=ref, cleanup="confirmed")
    return plan, review, base


def verdict(evidence, *, baseline=None, candidate=None, review=None, qualified=True):
    plan, valid, base = evidence
    return decide(plan, valid if review is None else review, base if baseline is None else baseline, candidate,
                  pair_sha256="b" * 64, qualified=qualified)


def test_scoped_confirmation_and_cleanup_independence(evidence):
    result = verdict(evidence)
    assert result.status == "confirmed_finding"
    assert "production" in result.limitations[0]
    assert verdict(evidence, baseline=evidence[2].model_copy(update={"cleanup": "unknown"})).status == "confirmed_finding"


@pytest.mark.parametrize("change,reason", [
    ({"discovery_ok": False}, "discovery_incomplete"),
    ({"execution_status": "unknown"}, "unknown_effect"),
    ({"report_ref": None}, "native_evidence_missing"),
    ({"commands": ()}, "native_evidence_missing"),
    ({"pair_sha256": "e" * 64}, "frozen_pair_mismatch"),
])
def test_incomplete_native_evidence_cannot_confirm(evidence, change, reason):
    result = verdict(evidence, baseline=evidence[2].model_copy(update=change))
    assert result.status == "inconclusive"
    assert result.reason == reason


@pytest.mark.parametrize("outcome", ["failed", "error", "skipped"])
def test_control_must_actually_pass(evidence, outcome):
    base = evidence[2]
    observations = (base.observations[0].model_copy(update={"outcome": outcome}), base.observations[1])
    assert verdict(evidence, baseline=base.model_copy(update={"observations": observations})).reason == "control_not_passed"


def test_exception_and_extra_test_are_not_confirmation(evidence):
    base = evidence[2]
    observations = (base.observations[0], base.observations[1].model_copy(update={"failure_type": "ValueError"}))
    assert verdict(evidence, baseline=base.model_copy(update={"observations": observations})).reason == "security_failure_not_assertion"
    observations = (*base.observations, ProbeObservation(test_id="unrequested", outcome="passed"))
    assert verdict(evidence, baseline=base.model_copy(update={"observations": observations})).reason == "probe_identity_mismatch"


def test_profile_and_semantic_review_are_distinct_gates(evidence):
    assert verdict(evidence, qualified=False).status == "unqualified"
    review = evidence[1].model_copy(update={"security": evidence[1].security.model_copy(update={"source_binding": False})})
    assert verdict(evidence, review=review).reason == "probe_validity_not_established"


def test_passed_security_is_not_a_safety_guarantee(evidence):
    base = evidence[2]
    observations = (base.observations[0], base.observations[1].model_copy(update={"outcome": "passed", "failure_type": None}))
    result = verdict(evidence, baseline=base.model_copy(update={"observations": observations}))
    assert result.status == "unknown_absence"
    assert "not proof" in result.limitations[0]


def test_repair_requires_same_environment_and_correctness_checks(evidence):
    base = evidence[2]
    observations = (base.observations[0], base.observations[1].model_copy(update={"outcome": "passed", "failure_type": None}))
    candidate = base.model_copy(update={"revision": "candidate", "observations": observations, "regression_passed": True})
    assert verdict(evidence, candidate=candidate).status == "verified_repair"
    assert verdict(evidence, candidate=candidate.model_copy(update={"regression_passed": None})).reason == "regression_not_passed"
    assert verdict(evidence, candidate=candidate.model_copy(update={"policy_sha256": "0" * 64})).reason == "environment_mismatch"


def test_receipt_for_other_workspace_is_rejected(evidence):
    base = evidence[2]
    command = base.commands[0].model_copy(update={"sandbox_id": "other-sandbox"})
    assert verdict(evidence, baseline=base.model_copy(update={"commands": (command,)})).reason == "native_receipt_incomplete"


def test_confinement_and_repair_authority_are_structural():
    with pytest.raises(ValidationError):
        Citation(path="../../credentials", start_line=1, end_line=2)
    with pytest.raises(ValidationError):
        RunSpec(request_id="r", source=SourceRequest(path="/tmp/source"), concern="Report", generate_repair=True)
    with pytest.raises(ValidationError):
        SourceRequest(path="/tmp/source", commit="main")
    with pytest.raises(ValidationError):
        RunSpec(request_id="r", source=SourceRequest(path="/tmp/source"), concern="Report", unexpected="label")
