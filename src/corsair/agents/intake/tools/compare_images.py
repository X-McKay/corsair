"""Episode-bound inventory comparison; no image discovery or execution."""

import json
from collections.abc import Awaitable, Callable

from google.adk.tools.tool_context import ToolContext
from pydantic import ValidationError

from corsair.contracts.intake import (
    ExecutionMode,
    ImageCandidate,
    ImageInventory,
    Language,
    Requirement,
)


def create_compare_images(
    inventory: ImageInventory, byte_limit: int
) -> Callable[..., Awaitable[dict]]:
    images = inventory.model_copy(deep=True)

    async def compare_images(
        language: Language,
        execution_mode: ExecutionMode,
        requirements: list[Requirement],
        tool_context: ToolContext,
    ) -> dict:
        """Compare inspected issue requirements with currently available reviewed images.

        Returns candidate capabilities and missing requirements, not a final issue decision.
        Unknown requirements need source inspection. Image metadata never grants network or
        privileged execution. No image is pulled, built, inspected dynamically or executed.
        """
        del tool_context
        try:
            profile = ImageCandidate(
                reference="comparison",
                language=language,
                execution_mode=execution_mode,
                requirements=requirements,
            )
            if len(set(profile.requirements)) != len(profile.requirements):
                raise ValueError("duplicate categories")
        except (ValidationError, ValueError, TypeError):
            return {"error": "invalid_requirement_profile", "target_executed": False}
        uncertain = (
            profile.language in {"unknown", "other", "multiple"}
            or profile.execution_mode == "unknown"
            or bool(set(profile.requirements) & {"unknown", "other"})
        )
        blocked = sorted(set(profile.requirements) & {"network_access", "privileged_execution"})
        candidates = []
        for image in images.images:
            missing = sorted(set(profile.requirements) - set(image.requirements))
            language_matches = profile.language == image.language
            mode_matches = profile.execution_mode == image.execution_mode
            candidates.append(
                {
                    "reference": image.reference,
                    "language": image.language,
                    "execution_mode": image.execution_mode,
                    "requirements": list(image.requirements),
                    "language_matches": language_matches,
                    "mode_matches": mode_matches,
                    "missing_requirements": missing,
                    "compatible": bool(
                        language_matches
                        and mode_matches
                        and not missing
                        and not uncertain
                        and not blocked
                    ),
                }
            )
        result = {
            "scope": "inventory_comparison_only",
            "target_executed": False,
            "uncertain_profile": uncertain,
            "blocked_requirements": blocked,
            "images": candidates,
        }
        if len(json.dumps(result, ensure_ascii=False).encode()) > byte_limit:
            return {"error": "image_comparison_exceeds_output_limit", "target_executed": False}
        return result

    return compare_images
