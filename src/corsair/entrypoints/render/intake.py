"""Allowlisted human intake views; issue prose remains in machine output only."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts.intake_agent import IntakeResult
from corsair.contracts.intake_pipeline import IntakeInvestigationResult
from corsair.entrypoints.render.common import as_text, label_grid, short_digest
from corsair.entrypoints.render.result import print_result
from corsair.policies.intake_explanation import explain_intake_parent


def _add_intake_fields(grid: Table, result: IntakeResult, *, details: bool) -> None:
    decision = result.decision
    grid.add_row("Classification", as_text(decision.classification))
    grid.add_row("Intake status", as_text(decision.status))
    grid.add_row("Reasons", as_text(", ".join(decision.reason_codes) or "none"))
    if decision.error_code:
        grid.add_row("Error", as_text(decision.error_code))
        grid.add_row("Failure category", as_text(result.diagnostics.output_failure))
        grid.add_row("Stage", as_text(result.diagnostics.error_stage))
        grid.add_row("Error type", as_text(result.diagnostics.error_type))
    suggested = result.proposal.suggested_image if result.proposal else None
    image = next(
        (
            item
            for item in result.inventory.images
            if item.image_id == decision.image_id and item.reference == suggested
        ),
        None,
    )
    grid.add_row("Selected image", as_text(image.reference if image else None))
    image_id = decision.image_id
    grid.add_row(
        "Image ID", as_text(image_id if details or image_id is None else short_digest(image_id))
    )
    grid.add_row("Image check", as_text(decision.image_check))


def print_intake_result(console: Console, result: IntakeResult, *, details: bool = False) -> None:
    grid = label_grid()
    grid.add_row("Run", as_text(result.run_id))
    _add_intake_fields(grid, result, details=details)
    console.print(Panel(grid, title="Corsair · Issue intake", border_style="cyan"))
    if result.decision.classification == "out_of_scope":
        console.print("The reported issue is outside the supported security scope.")
    elif result.decision.classification == "in_scope_supported":
        console.print("Supply the trusted Case binding to investigate this issue.")


def print_intake_explanation(console: Console, explanation: dict[str, object]) -> None:
    grid = label_grid()
    for key, label in (
        ("run_id", "Run"),
        ("status", "Status"),
        ("stop_reason", "Stop reason"),
        ("investigation_run_id", "Investigation"),
        ("explanation", "Explanation"),
        ("next_step", "Next step"),
    ):
        value = explanation.get(key)
        grid.add_row(label, as_text("none" if key == "stop_reason" and value is None else value))
    console.print(Panel(grid, title="Corsair · Intake workflow", border_style="cyan"))


def print_intake_parent(
    console: Console,
    result: IntakeInvestigationResult,
    *,
    store: ArtifactStore | None = None,
    details: bool = False,
    settings_path: str | None = None,
) -> None:
    if result.intake is not None:
        grid = label_grid()
        _add_intake_fields(grid, result.intake, details=details)
        grid.add_row("Disposition", as_text(result.investigation_disposition))
        grid.add_row("Execution", as_text(result.investigation_execution_status))
        console.print(Panel(grid, title="Corsair · Intake decision", border_style="cyan"))
    print_intake_explanation(console, explain_intake_parent(result))
    if result.investigation_run_id is not None:
        from corsair.entrypoints.runs import load_parent_investigation

        child = load_parent_investigation(store, result) if store is not None else None
        if child is not None:
            print_result(console, child, store, details=details, settings_path=settings_path)
        else:
            console.print("Investigation receipt unavailable locally; no child verdict displayed.")
