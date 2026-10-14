"""Small deterministic gate over frozen review and actual native observations."""
from __future__ import annotations

from corsair.v2.contracts import (
    InvestigationPlan,
    RevisionExecution,
    ValidityReview,
    Verdict,
)


def _stop(reason: str, summary: str, *, status="inconclusive") -> Verdict:
    return Verdict(status=status, reason=reason, rule_id="V2-STOP-01", summary=summary)


def _admit(revision: RevisionExecution, plan: InvestigationPlan, pair_sha256: str) -> str | None:
    if revision.pair_sha256 != pair_sha256:
        return "frozen_pair_mismatch"
    if revision.execution_status != "completed":
        return "unknown_effect" if revision.execution_status == "unknown" else revision.execution_status
    if not revision.discovery_ok:
        return "discovery_incomplete"
    if revision.report_ref is None or not revision.commands:
        return "native_evidence_missing"
    if any(c.status != "completed" or c.sandbox_id != revision.sandbox_id for c in revision.commands):
        return "native_receipt_incomplete"
    ids = [o.test_id for o in revision.observations]
    expected = {plan.control.test_id, plan.security.test_id}
    if len(ids) != 2 or len(set(ids)) != 2 or set(ids) != expected:
        return "probe_identity_mismatch"
    outcomes = {o.test_id: o for o in revision.observations}
    if outcomes[plan.control.test_id].outcome != "passed":
        return "control_not_passed"
    security = outcomes[plan.security.test_id]
    if security.outcome in ("error", "skipped"):
        return "security_probe_incomplete"
    if security.outcome == "failed" and security.failure_type != "assertion":
        return "security_failure_not_assertion"
    return None


def decide(plan: InvestigationPlan | None, review: ValidityReview | None,
           baseline: RevisionExecution | None, candidate: RevisionExecution | None,
           *, pair_sha256: str, qualified: bool) -> Verdict:
    """Classification is scoped to these source-reviewed probes and this environment.

    Cleanup is recorded independently; it does not erase completed evidence.
    Native reports are workload claims corroborated by the pre-execution review,
    not a proof against a malicious target forging its own semantic outcomes.
    """
    if plan is None:
        return _stop("plan_missing", "No admitted investigation plan was produced.")
    if plan.status != "planned":
        return _stop("plan_" + plan.status, plan.summary, status=plan.status)
    if review is None or not review.valid:
        return _stop("probe_validity_not_established", "The frozen source-only review did not establish both probes' relevance.")
    if baseline is None:
        return _stop("baseline_missing", "No baseline execution was retained.")
    problem = _admit(baseline, plan, pair_sha256)
    if problem:
        return _stop(problem, "Baseline evidence is incomplete: " + problem + ".")
    if candidate is not None:
        problem = _admit(candidate, plan, pair_sha256)
        if problem:
            return _stop(problem, "Candidate evidence is incomplete: " + problem + ".")
        if (candidate.image, candidate.policy_sha256) != (baseline.image, baseline.policy_sha256):
            return _stop("environment_mismatch", "Baseline and candidate environments differ.")
    if not qualified:
        return _stop("sandbox_profile_unqualified", "The execution is retained, but its profile is not qualified for a conclusive disposition.", status="unqualified")
    base_security = next(o for o in baseline.observations if o.test_id == plan.security.test_id)
    if base_security.outcome == "passed":
        return Verdict(status="unknown_absence", reason="not_reproduced_in_scope", rule_id="V2-NOT-REPRODUCED-01",
                       summary="The reported condition was not reproduced by the reviewed unit probe.",
                       limitations=("Oracle silence is not proof that the application is safe or externally unreachable.",))
    if candidate is not None:
        fix_security = next(o for o in candidate.observations if o.test_id == plan.security.test_id)
        if fix_security.outcome == "passed":
            if candidate.regression_passed is not True:
                return _stop("regression_not_passed", "The candidate's prescribed correctness checks did not pass.")
            return Verdict(status="verified_repair", reason="paired_probe_flip", rule_id="V2-REPAIR-01",
                           summary="The baseline reproduces the scoped condition; the clean candidate passes both probes and prescribed correctness checks.",
                           limitations=("Verification covers the declared unit seam and prescribed checks, not all behavior or vulnerabilities.",))
    return Verdict(status="confirmed_finding", reason="reviewed_security_assertion_failed", rule_id="V2-FINDING-01",
                   summary="The benign control passed and the reviewed adversarial safety assertion failed on the baseline.",
                   limitations=("This is unit-probe evidence, not a production reachability or exploit-chain claim.",))
