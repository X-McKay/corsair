"""Intake admission must not confuse a model recommendation with execution authority."""

import pytest
from pydantic import ValidationError

from corsair.contracts.intake import ImageInventory, IntakeProposal, Issue
from corsair.policies.intake import classify_intake, validate_proposal


def proposal(**changes):
    return IntakeProposal.model_validate(
        {
            "issue": {"title": "Traversal", "description": "Private file disclosure"},
            "scope": "in_scope",
            "surface": "function",
            "language": "python",
            "execution_mode": "callable",
            "requirements": [],
            "suggested_image": None,
            "reason_codes": ["NO_COMPATIBLE_IMAGE"],
            "locations": [{"path": "reader.py"}],
            **changes,
        }
    )


def test_missing_image_is_unsupported_not_supported():
    decision = classify_intake(proposal(), ImageInventory())
    assert decision.classification == "in_scope_not_supported"
    assert "NO_COMPATIBLE_IMAGE" in decision.reason_codes


def test_invented_image_is_invalid_even_for_unsupported_issue():
    with pytest.raises(ValueError, match="inventory"):
        validate_proposal(proposal(suggested_image="python:imagined"), ImageInventory())


def test_unknown_scope_does_not_become_out_of_scope():
    decision = classify_intake(proposal(scope="unknown"), ImageInventory())
    assert decision.status == "needs_input"
    assert decision.classification is None


def test_supported_depends_on_available_image_capabilities_without_a_recipe():
    inventory = ImageInventory(
        images=[
            {
                "reference": "python-local:reviewed",
                "image_id": "sha256:" + "1" * 64,
                "language": "python",
                "execution_mode": "callable",
                "requirements": [],
            }
        ]
    )
    candidate = proposal(suggested_image="python-local:reviewed", reason_codes=[])
    assert classify_intake(candidate, inventory).classification == "in_scope_supported"


def test_service_requirement_cannot_fit_callable_image():
    inventory = ImageInventory(
        images=[
            {
                "reference": "corsair-python:0.1",
                "image_id": "sha256:" + "1" * 64,
                "language": "python",
                "execution_mode": "callable",
                "requirements": [],
            }
        ]
    )
    decision = classify_intake(
        proposal(
            suggested_image="corsair-python:0.1",
            execution_mode="http_service",
            requirements=["service_start"],
            reason_codes=[],
        ),
        inventory,
    )
    assert decision.classification == "in_scope_not_supported"
    assert "SERVICES_UNSUPPORTED" in decision.reason_codes


def test_missing_issue_fields_are_not_fabricated():
    assert Issue().title is None
    with pytest.raises(ValidationError):
        Issue(locations=[{"path": "../private"}])


def test_image_capabilities_cannot_grant_network_or_privileged_permissions():
    inventory = ImageInventory(
        images=[
            {
                "reference": "python-local:reviewed",
                "image_id": "sha256:" + "1" * 64,
                "language": "python",
                "execution_mode": "callable",
                "requirements": ["network_access", "privileged_execution"],
            }
        ]
    )
    decision = classify_intake(
        proposal(
            suggested_image="python-local:reviewed",
            requirements=["network_access", "privileged_execution"],
            reason_codes=[],
        ),
        inventory,
    )
    assert decision.classification == "in_scope_not_supported"
    assert set(decision.reason_codes) == {"NETWORK_NOT_PERMITTED", "PRIVILEGES_NOT_PERMITTED"}
