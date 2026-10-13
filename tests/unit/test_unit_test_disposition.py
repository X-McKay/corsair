"""Unit-property verdicts require independently reviewed, source-bound frozen tests."""

import pytest

from corsair.core.disposition import AssessmentEvidence, TestValidity, Witness, assess
from tests.unit.test_disposition import DENIED, PLAN, PLANNED_FAILURE, codes, digest, run

UNIT_PLAN = PLAN.model_copy(update={"observation_mode": "unit_test", "test_plan_sha256": digest("typed plan")})
SOURCE = digest("saved application source")
VALIDITY = TestValidity(
    artifact_sha256=digest("independent review artifact"), observation_plan_sha256=UNIT_PLAN.review_digest,
    source_sha256=SOURCE, source_linked=True, condition_exercised=True,
    assertions_relevant=True, dependency_scope_valid=True,
)


def unit_run(security="failed", **changes):
    return run(security, witness=None, source_sha256=SOURCE, test_validity=VALIDITY, **changes)


def gate(baseline, candidate=(), plan=UNIT_PLAN):
    return assess(AssessmentEvidence(plan=plan, baseline=baseline, candidate=candidate))


def test_reviewed_unit_tests_can_reproduce_and_verify_without_effect_recorder():
    result = gate((unit_run(),), (unit_run("passed"),))
    assert (result.permitted.finding, result.permitted.fix) == ("reproduced", "verified")
    assert not result.limitations


def test_reviewed_unit_tests_can_establish_safe_baseline_in_scope_without_recorder():
    result = gate((unit_run("passed"),))
    assert result.permitted.finding == "not_reproduced"
    assert result.permitted.fix == "not_applicable"


@pytest.mark.parametrize("change", [
    {"test_validity": None},
    {"test_validity": VALIDITY.model_copy(update={"source_linked": False})},
    {"test_validity": VALIDITY.model_copy(update={"condition_exercised": False})},
    {"test_validity": VALIDITY.model_copy(update={"assertions_relevant": False})},
    {"test_validity": VALIDITY.model_copy(update={"dependency_scope_valid": False})},
    {"test_validity": VALIDITY.model_copy(update={"source_sha256": digest("other source")})},
    {"test_validity": VALIDITY.model_copy(update={"observation_plan_sha256": digest("other plan")})},
    {"source_sha256": None},
    {"patch_sha256": digest("other patch")},
])
def test_invalid_or_unbound_review_cannot_support_unit_verdict(change):
    observed = unit_run().model_copy(update=change)
    result = gate((observed,), (unit_run("passed"),))
    assert result.permitted.finding == "inconclusive"
    assert result.permitted.fix == "not_verified"


def test_review_cannot_be_reused_when_typed_plan_changes():
    altered = UNIT_PLAN.model_copy(update={"test_plan_sha256": digest("changed typed plan")})
    result = gate((unit_run(),), plan=altered)
    assert result.permitted.finding == "inconclusive"
    assert "test_validity_unsupported" in codes(result)


@pytest.mark.parametrize("changes, expected", [
    ({"control": "failed"}, "control_failed"),
    ({"security": "skipped"}, "test_skipped"),
    ({"security": "error"}, "test_error"),
    ({"failure": None}, "unclassified_failure"),
    ({"failure": PLANNED_FAILURE.model_copy(update={"line": 1})}, "unplanned_failure"),
    ({"sandbox_events": DENIED}, "sandbox_attributed"),
    ({"delivery": "unknown"}, "delivery_unknown"),
])
def test_native_execution_and_assertion_failures_still_block_unit_verdict(changes, expected):
    security = changes.get("security", "failed")
    changes = {key: value for key, value in changes.items() if key != "security"}
    result = gate((unit_run(security, **changes),))
    assert result.permitted.finding == "inconclusive"
    assert expected in codes(result)


@pytest.mark.parametrize("security,witness", [
    ("passed", Witness(artifact_sha256=digest("effect"), path_reached=True, effect="observed")),
    ("failed", Witness(artifact_sha256=digest("safe"), path_reached=True, effect="absent", safe_behavior="ValueError")),
])
def test_optional_contradictory_witness_blocks_unit_verdict(security, witness):
    observed = unit_run(security).model_copy(update={"witness": witness})
    result = gate((observed,))
    assert result.permitted.finding == "inconclusive"
