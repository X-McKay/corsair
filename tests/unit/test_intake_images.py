"""Image comparison informs agent choice without granting execution permissions."""

import pytest

from corsair.contracts.intake_agent import ImageInventory


def inventory():
    return ImageInventory(
        images=[
            {
                "reference": "python-local:callable",
                "image_id": "sha256:" + "1" * 64,
                "language": "python",
                "execution_mode": "callable",
                "requirements": [],
            },
            {
                "reference": "python-local:service",
                "image_id": "sha256:" + "2" * 64,
                "language": "python",
                "execution_mode": "http_service",
                "requirements": ["service_start", "http_client", "network_access"],
            },
        ]
    )


async def compare(images, language="python", mode="callable", requirements=None, limit=32768):
    from corsair.agents.intake.tools.compare_images import create_compare_images

    tool = create_compare_images(images, limit)
    return await tool(
        language=language,
        execution_mode=mode,
        requirements=[] if requirements is None else requirements,
        tool_context=None,
    )


async def test_image_comparison_exposes_matches_and_missing_capabilities():
    result = await compare(inventory())
    assert result["target_executed"] is False
    assert [row["reference"] for row in result["images"] if row["compatible"]] == [
        "python-local:callable"
    ]
    result = await compare(inventory(), mode="http_service", requirements=["service_start"])
    assert result["images"][1]["compatible"] is True
    assert result["images"][0]["missing_requirements"] == ["service_start"]
    result = await compare(inventory(), requirements=["dependency_install"])
    assert all(not row["compatible"] for row in result["images"])
    assert result["images"][0]["missing_requirements"] == ["dependency_install"]


@pytest.mark.parametrize(
    "language,mode,requirements",
    [("unknown", "callable", []), ("python", "unknown", []), ("python", "callable", ["unknown"])],
)
async def test_uncertain_profiles_never_claim_compatible_images(language, mode, requirements):
    result = await compare(inventory(), language, mode, requirements)
    assert result["uncertain_profile"] is True
    assert all(not row["compatible"] for row in result["images"])


async def test_reviewed_image_metadata_cannot_grant_network_or_privileges():
    result = await compare(inventory(), mode="http_service", requirements=["network_access"])
    assert result["blocked_requirements"] == ["network_access"]
    assert all(not row["compatible"] for row in result["images"])
    result = await compare(inventory(), requirements=["privileged_execution"])
    assert result["blocked_requirements"] == ["privileged_execution"]
    assert all(not row["compatible"] for row in result["images"])


async def test_empty_inventory_stays_empty_and_large_response_is_explicit():
    assert (await compare(ImageInventory()))["images"] == []
    result = await compare(inventory(), limit=128)
    assert result["error"] == "image_comparison_exceeds_output_limit"
    assert "images" not in result


@pytest.mark.parametrize("requirements", [["invented"], ["build", "build"], ["build"] * 12])
async def test_invalid_or_duplicate_categories_fail_without_echoing_input(requirements):
    result = await compare(inventory(), requirements=requirements)
    assert result == {"error": "invalid_requirement_profile", "target_executed": False}


async def test_comparison_is_bound_to_detached_episode_inventory():
    from corsair.agents.intake.tools.compare_images import create_compare_images

    images = inventory()
    tool = create_compare_images(images, 32768)
    images.images.clear()
    first = await tool(
        language="python", execution_mode="callable", requirements=[], tool_context=None
    )
    first["images"].clear()
    second = await tool(
        language="python", execution_mode="callable", requirements=[], tool_context=None
    )
    assert len(second["images"]) == 2
