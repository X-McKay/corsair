import pytest
from pydantic import ValidationError

from corsair.contracts import (
    DIAGNOSTIC_TRUNCATION_MARKER,
    MAX_DIAGNOSTIC_TEXT_CHARS,
    MAX_TERMINAL_ROUNDS,
    ArtifactRef,
    Disposition,
    ExecutionStatus,
    InvestigationResult,
    Observation,
    PlanRevision,
    ProducerDecision,
    ProducerOutput,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    Submission,
    format_terminal_result,
)


def _result() -> InvestigationResult:
    submission = Submission(
        control_payload={"path": "hello.txt"},
        exploit_payload={"path": "../private/secret.txt"},
        hypothesis="The target returns an attacker-controlled payload.",
        plan=PlanRevision(
            revision=1,
            objective="exercise the paired payloads through trusted evidence collection",
            next_steps=["submit one control and one adversarial payload"],
            reason="a paired observation is required for the claim",
        ),
    )
    native_receipt = ArtifactRef(sha256="a" * 64, size=123, media_type="application/json")
    observation = Observation(
        operation_id="run.r1",
        source_digest="b" * 64,
        submission_digest="c" * 64,
        control=RoleObservation(
            outcome=RoleOutcome.HELD,
            target_executed=True,
            covered_lines=[4],
            reason="trusted control observation",
            native_exit_code=0,
        ),
        adversarial=RoleObservation(
            outcome=RoleOutcome.VIOLATION,
            target_executed=True,
            covered_lines=[4],
            reason="trusted adversarial observation",
            native_exit_code=1,
        ),
        artifact=native_receipt,
        cleanup_confirmed=True,
    )
    return InvestigationResult(
        run_id="run",
        case_id="case",
        disposition=Disposition.SUPPORTED,
        execution_status=ExecutionStatus.COMPLETED,
        reason="paired native observation supports the component claim",
        rounds=[
            RoundResult(
                index=1,
                producer=ProducerOutput(
                    decision=ProducerDecision(kind="proposal", submission=submission)
                ),
                observation=observation,
            )
        ],
    )


def test_terminal_formatter_compacts_only_diagnostics_and_preserves_provenance():
    result = _result()
    oversized = result.model_copy(
        update={"reason": "evidence: " + "x" * (MAX_DIAGNOSTIC_TEXT_CHARS * 2)}
    )

    formatted = format_terminal_result(oversized)

    assert formatted.reason.startswith("evidence: ")
    assert formatted.reason.endswith(DIAGNOSTIC_TRUNCATION_MARKER)
    assert len(formatted.reason) == MAX_DIAGNOSTIC_TEXT_CHARS
    assert formatted.rounds == result.rounds
    assert (
        formatted.rounds[0].producer.submission_for_verification()
        == result.rounds[0].producer.submission_for_verification()
    )
    assert formatted.rounds[0].observation is not None
    assert result.rounds[0].observation is not None
    assert formatted.rounds[0].observation.artifact == result.rounds[0].observation.artifact


def test_terminal_formatter_revalidates_model_copy_without_truncating_operation_claims():
    result = _result()
    submission = result.rounds[0].producer.submission_for_verification()
    assert submission is not None
    oversized_submission = submission.model_copy(update={"hypothesis": "x" * 4001})
    oversized_round = result.rounds[0].model_copy(
        update={
            "producer": ProducerOutput(
                decision=ProducerDecision(kind="proposal", submission=oversized_submission)
            )
        }
    )

    with pytest.raises(ValidationError, match="hypothesis"):
        format_terminal_result(result.model_copy(update={"rounds": [oversized_round]}))


def test_terminal_formatter_revalidates_maximum_round_count_after_model_copy():
    result = _result()

    with pytest.raises(ValidationError, match="too_long"):
        format_terminal_result(
            result.model_copy(update={"rounds": result.rounds * (MAX_TERMINAL_ROUNDS + 1)})
        )


async def test_finalization_validation_fails_explicitly_without_recording_invalid_claims():
    from temporalio.exceptions import ApplicationError

    from corsair.workflows.investigation import InvestigationWorkflow

    result = _result().model_copy(update={"rounds": _result().rounds * (MAX_TERMINAL_ROUNDS + 1)})
    with pytest.raises(ApplicationError) as rejected:
        await InvestigationWorkflow()._record_result(result)
    assert rejected.value.type == "TERMINAL_PAYLOAD_INVALID"
    assert rejected.value.non_retryable
    assert rejected.value.__cause__ is None
    assert rejected.value.__suppress_context__


def test_terminal_formatter_preserves_valid_empty_observation_diagnostics():
    result = _result()
    observation = result.rounds[0].observation
    assert observation is not None
    minimal = RoleObservation(outcome=RoleOutcome.HELD, target_executed=True)
    altered = result.model_copy(
        update={
            "rounds": [
                result.rounds[0].model_copy(
                    update={"observation": observation.model_copy(update={"control": minimal})}
                )
            ]
        }
    )
    formatted = format_terminal_result(altered).rounds[0].observation
    assert formatted is not None and formatted.control is not None
    assert formatted.control.reason == ""
