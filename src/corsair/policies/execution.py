"""Pure capability admission for the current recipe-free investigation path."""

from corsair.contracts.execution import ExecutionRequest
from corsair.contracts.intake import ImageInventory


def admit_execution_image(request: ExecutionRequest, inventory: ImageInventory) -> None:
    if request.image not in inventory.images:
        raise ValueError("selected image is not currently available with admitted metadata")
    if any(
        requirement in request.image.requirements
        for requirement in ("network_access", "privileged_execution")
    ):
        raise ValueError("image metadata cannot grant denied permissions")


def plan_fits_result(result, plan) -> bool:
    """Reserve headroom for bounded native receipts beneath Temporal's payload ceiling."""
    used = sum(
        len(item.plan.model_dump_json().encode()) for item in result.rounds if item.plan is not None
    )
    return used + len(plan.model_dump_json().encode()) <= 750_000
