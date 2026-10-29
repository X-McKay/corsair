"""Code-owned explanations for intake workflow stops; no model prose."""

from corsair.contracts.intake_pipeline import IntakeInvestigationResult, StopReason

_STOPS: dict[StopReason, tuple[str, str]] = {
    "OUT_OF_SCOPE": (
        "The reported issue is outside the supported security scope.",
        "Review the finding's scope before submitting a different issue.",
    ),
    "UNSUPPORTED": (
        "The issue is in scope, but current execution requirements are unsupported.",
        "Review intake reason codes and the configured local image inventory.",
    ),
    "NEEDS_INPUT": (
        "Intake needs more information to classify this issue.",
        "Provide one finding with a clear source location and security claim.",
    ),
    "INTAKE_ERROR": (
        "Intake could not complete inspection or model processing.",
        "Check the intake error code and run corsair doctor --model.",
    ),
    "TARGET_BINDING_REQUIRED": (
        "Intake accepted the issue, but no trusted Case binding was supplied.",
        "Supply a Case request to corsair investigate BINDING --json ISSUE --wait.",
    ),
    "HANDOFF_INVALID": (
        "The intake result does not match the trusted investigation binding.",
        "Check the binding's source, target path and configuration against the intake result.",
    ),
    "BUDGET_EXHAUSTED": (
        "The workflow exhausted its remaining investigation budget.",
        "Review recorded usage before choosing a new run and budget.",
    ),
    "INTAKE_UNCERTAIN": (
        "Intake completion could not be confirmed.",
        "Inspect the parent and intake child before starting another run.",
    ),
    "INVESTIGATION_UNCERTAIN": (
        "Investigation completion could not be confirmed.",
        "Inspect the investigation child and its committed evidence.",
    ),
    "CANCELLED": (
        "The workflow was cancelled.",
        "Inspect any child result and cleanup receipts before starting another run.",
    ),
    "DEADLINE_EXHAUSTED": (
        "The workflow reached its deadline.",
        "Inspect child results and cleanup receipts before choosing a new run and deadline.",
    ),
}


def explain_intake_parent(result: IntakeInvestigationResult) -> dict[str, object]:
    """Explain only recorded state; a stop never implies a security verdict."""
    explanation, next_step = (
        _STOPS[result.stop_reason]
        if result.stop_reason is not None
        else (
            "The intake gate admitted an investigation and its result was recorded.",
            f"Run corsair inspect {result.investigation_run_id} --explain "
            "for the evidence-based verdict.",
        )
    )
    return {
        "intake_explanation": True,
        "run_id": result.run_id,
        "status": result.status,
        "stop_reason": result.stop_reason,
        "classification": result.intake.decision.classification if result.intake else None,
        "investigation_run_id": result.investigation_run_id,
        "investigation_disposition": result.investigation_disposition,
        "investigation_execution_status": result.investigation_execution_status,
        "explanation": explanation,
        "next_step": next_step,
    }
