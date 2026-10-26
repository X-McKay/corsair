"""Workflow-boundary regression tests: the outcome-blind retry feedback and the
canonical verdict's handling of a later terminal operational failure."""

from __future__ import annotations

from corsair.contracts import (
    AuditDecision,
    ExecutionStatus,
    FixStatus,
    InvestigationResult,
    RoundResult,
    Verdict,
    validate_root_identity,
)
from corsair.workflows.investigation import (
    _BLIND_RETRY_REASON,
    _aggregate_case_verdict,
    _operation_prefix,
    _retry_feedback,
    _session_outcome,
)
from tests.unit.test_evidence import _audit, _prepared
from tests.unit.test_verdicts import _clean_negative, _demonstrated

_DECISION_OUTCOME_REASON = "no reproducible secret-disclosure demonstration was observed"


def _result(**updates) -> InvestigationResult:
    base = InvestigationResult(
        run_id="run",
        case_id="case",
        disposition="INCONCLUSIVE",
        execution_status=ExecutionStatus.COMPLETED,
        reason="completed",
    )
    return base.model_copy(update=updates)


# --- finding 1: the producer never learns the exploit outcome on retry --------


def test_retry_feedback_never_forwards_the_run_outcome_when_audit_accepts():
    """A completed round the auditor accepted leaves nothing the producer may see:
    the retry carries a fixed, outcome-free instruction, never decide()'s reason."""
    feedback = _retry_feedback(_audit(AuditDecision.ACCEPT))
    assert feedback.reason == _BLIND_RETRY_REASON
    assert "disclosure" not in feedback.reason
    assert _DECISION_OUTCOME_REASON not in feedback.reason


def test_retry_feedback_forwards_only_the_structural_audit_rejection():
    """A rejecting auditor formed its reason without any run result, so that
    structural/semantic reason is the one corrective signal a retry may carry."""
    feedback = _retry_feedback(_audit(AuditDecision.REJECT))
    assert feedback.gate == "audit"
    assert feedback.reason == "reviewed"


def test_retry_feedback_depends_on_the_audit_alone():
    """ADR 0005: no run fact may reach the producer on retry, not even a control-role
    one, because a healthy-control signal reveals the exploit outcome by elimination.
    The function therefore accepts only the audit output."""
    import inspect

    from corsair.contracts import AuditOutput

    parameters = list(inspect.signature(_retry_feedback).parameters.values())
    assert [(p.name, p.annotation) for p in parameters] == [("audit", AuditOutput)]


# --- finding 2: a later terminal failure is not masked by an earlier round -----


def _round(index: int, observation, audit) -> RoundResult:
    from corsair.contracts import ProducerDecision, ProducerOutput
    from tests.unit.test_evidence import _submission

    producer = ProducerOutput(decision=ProducerDecision(kind="proposal", submission=_submission()))
    return RoundResult(index=index, producer=producer, observation=observation, audit=audit)


def test_later_operational_failure_overrides_an_earlier_clean_negative():
    """Round 1 is a covered clean negative; round 2 fails operationally. The
    canonical verdict must carry the operational error, not the earlier round."""
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="provider unavailable")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.ERROR


def test_a_confirmed_demonstration_survives_a_later_failure():
    """A positively demonstrated exploit is a fact; a later failure does not erase it."""
    rounds = [_round(1, _demonstrated(), _audit())]
    result = _result(
        execution_status=ExecutionStatus.ERROR,
        reason="later fault",
        fix_status=FixStatus.DEMONSTRATION_BLOCKED,
    )
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_a_component_demonstration_survives_a_later_failure():
    from corsair.contracts import Scope

    prepared = _prepared().model_copy(
        update={
            "finding": _prepared().finding.model_copy(update={"claim_scope": Scope.APPLICATION})
        }
    )
    rounds = [_round(1, _demonstrated(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="later fault")
    verdict = _aggregate_case_verdict(prepared, rounds, result)
    assert verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED


def test_completed_clean_negative_alone_is_inconclusive_at_threshold_two():
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.COMPLETED, reason="completed")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result)
    assert verdict is Verdict.INCONCLUSIVE


# --- independent sessions: only case_verdict promotes clean negatives ----------


def test_two_independent_clean_negative_sessions_are_exploit_not_demonstrated():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    assert first.clean_negative
    rounds = [_round(1, _clean_negative(), _audit())]
    verdict = _aggregate_case_verdict(_prepared(), rounds, _result(), [first])
    assert verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED


def test_second_session_operational_failure_is_not_a_clean_negative():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    rounds = [_round(1, _clean_negative(), _audit())]
    result = _result(execution_status=ExecutionStatus.ERROR, reason="provider unavailable")
    verdict = _aggregate_case_verdict(_prepared(), rounds, result, [first])
    assert verdict is Verdict.ERROR


def test_second_session_that_never_ran_a_round_stays_inconclusive():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    verdict = _aggregate_case_verdict(_prepared(), [], _result(), [first])
    assert verdict is Verdict.INCONCLUSIVE


def test_a_demonstration_in_the_second_session_is_exploit_demonstrated():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    rounds = [_round(1, _demonstrated(), _audit())]
    verdict = _aggregate_case_verdict(_prepared(), rounds, _result(), [first])
    assert verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_later_sessions_use_disjoint_operation_ids_with_suffix_headroom():
    root = "r" * 60
    assert _operation_prefix(root, 1) == root
    second = _operation_prefix(root, 2)
    assert second != root and second.startswith(f"{root}.")
    validate_root_identity(root)
    from pydantic import TypeAdapter

    from corsair.contracts.common import Identifier

    TypeAdapter(Identifier).validate_python(f"{second}.fix16")


# --- finding 3: the API/CLI boundary reserves operation-suffix headroom --------


def test_root_identity_rejects_lengths_that_leave_no_suffix_headroom():
    import pytest

    validate_root_identity("r" * 60)
    with pytest.raises(ValueError, match="operation suffixes"):
        validate_root_identity("r" * 61)


# --- the admitted session policy is replayed data, not worker Settings ----------


def test_admitted_threshold_three_keeps_two_clean_sessions_non_decisive():
    first = _session_outcome(_prepared(), [_round(1, _clean_negative(), _audit())], _result())
    rounds = [_round(1, _clean_negative(), _audit())]
    verdict = _aggregate_case_verdict(_prepared(), rounds, _result(), [first], 3)
    assert verdict is Verdict.INCONCLUSIVE


def test_manifest_carries_the_admitted_session_policy_readably(tmp_path):
    from pathlib import Path

    from corsair.contracts import InvestigationRequest
    from corsair.settings import Settings
    from corsair.steps.manifest import build_manifest

    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    )
    settings = Settings(artifact_root=str(tmp_path), negative_threshold=3, max_sessions=4)
    manifest = build_manifest(request, settings, "sha256:" + "a" * 64)
    assert (manifest.negative_threshold, manifest.max_sessions) == (3, 4)
    assert build_manifest(request, Settings(), "x").negative_threshold == 2


async def test_prepare_rejects_a_session_cap_beyond_terminal_round_capacity(tmp_path):
    from pathlib import Path

    import pytest
    from temporalio.exceptions import ApplicationError
    from temporalio.testing import ActivityEnvironment

    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import Budget, InvestigationRequest
    from corsair.settings import Settings
    from corsair.steps.activities import Activities

    class Sandbox:
        image_id = "sha256:" + "a" * 64

        def image_id_for(self, recipe_kind: str) -> str:
            del recipe_kind
            return self.image_id

    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    ).model_copy(update={"budget": Budget(max_rounds=16)})
    activities = Activities(
        Settings(artifact_root=str(tmp_path), max_sessions=3),
        store=ArtifactStore(tmp_path / "store"),
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=None,  # ty: ignore[invalid-argument-type]
        sandbox=Sandbox(),  # ty: ignore[invalid-argument-type]
    )
    with pytest.raises(ApplicationError) as rejected:
        await ActivityEnvironment().run(activities.prepare, request)
    assert rejected.value.type == "PREPARE_BLOCKED"
    assert rejected.value.non_retryable
