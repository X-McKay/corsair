"""Pure intake admission: model interpretation is never execution authority."""

from corsair.contracts.intake import (
    ImageInventory,
    IntakeDecision,
    IntakeProposal,
    ReasonCode,
    Requirement,
)


def validate_proposal(proposal: IntakeProposal, inventory: ImageInventory) -> None:
    if proposal.suggested_image is not None and proposal.suggested_image not in {
        image.reference for image in inventory.images
    }:
        raise ValueError("suggested image is outside supplied inventory")


def classify_intake(proposal: IntakeProposal, inventory: ImageInventory) -> IntakeDecision:
    validate_proposal(proposal, inventory)
    reasons: set[ReasonCode] = set(proposal.reason_codes)
    if proposal.scope == "unknown" or reasons & {
        "INSUFFICIENT_ISSUE_INFORMATION",
        "MULTIPLE_ISSUES",
        "SOURCE_LOCATION_UNRESOLVED",
    }:
        return IntakeDecision(status="needs_input", reason_codes=sorted(reasons))
    if proposal.scope == "out_of_scope":
        return IntakeDecision(
            status="completed", classification="out_of_scope", reason_codes=["OUTSIDE_SCOPE_POLICY"]
        )
    if "OUTSIDE_SCOPE_POLICY" in reasons:
        raise ValueError("in-scope proposal contradicts scope reason")
    image = next(
        (image for image in inventory.images if image.reference == proposal.suggested_image), None
    )
    if image is None:
        reasons.add(
            "IMAGE_UNDETERMINED" if "IMAGE_UNDETERMINED" in reasons else "NO_COMPATIBLE_IMAGE"
        )
    else:
        if image.language != proposal.language:
            reasons.add("LANGUAGE_UNSUPPORTED")
        if image.execution_mode != proposal.execution_mode:
            reasons.add("EXECUTION_MODE_UNSUPPORTED")
        requirement_reasons: dict[Requirement, ReasonCode] = {
            "dependency_install": "TARGET_DEPENDENCIES_UNSUPPORTED",
            "build": "BUILD_UNSUPPORTED",
            "service_start": "SERVICES_UNSUPPORTED",
            "external_service": "SERVICES_UNSUPPORTED",
            "network_access": "NETWORK_NOT_PERMITTED",
            "privileged_execution": "PRIVILEGES_NOT_PERMITTED",
        }
        for requirement in set(proposal.requirements) - set(image.requirements):
            reasons.add(requirement_reasons.get(requirement, "REQUIREMENT_UNSUPPORTED"))
    if (
        proposal.language in {"unknown", "other", "multiple"}
        or proposal.execution_mode == "unknown"
        or set(proposal.requirements) & {"unknown", "other"}
    ):
        reasons.add("REQUIREMENTS_UNRESOLVED")
    if "network_access" in proposal.requirements:
        reasons.add("NETWORK_NOT_PERMITTED")
    if "privileged_execution" in proposal.requirements:
        reasons.add("PRIVILEGES_NOT_PERMITTED")
    if not proposal.locations:
        return IntakeDecision(status="needs_input", reason_codes=["SOURCE_LOCATION_UNRESOLVED"])
    return IntakeDecision(
        status="completed",
        classification="in_scope_not_supported" if reasons else "in_scope_supported",
        reason_codes=sorted(reasons),
        image_check="blocked" if reasons else "accepted",
        image_id=None if reasons or image is None else image.image_id,
    )
