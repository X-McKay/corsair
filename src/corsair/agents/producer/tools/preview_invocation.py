"""Preview declared arguments only; never import or execute the target."""

from __future__ import annotations

import json
from collections.abc import Callable

from google.adk.tools.tool_context import ToolContext
from pydantic import JsonValue, TypeAdapter, ValidationError

from corsair.contracts import JavaRecipe, ProducerInput, PythonRecipe
from corsair.contracts.agents import JsonPayload

_JSON_VALUE = TypeAdapter(JsonValue)


def create_preview_invocation(producer_input: ProducerInput) -> Callable[..., object]:
    """Bind a native ADK data-only helper to the operator-owned recipe."""

    recipe = producer_input.prepared.recipe.model_copy(deep=True)
    byte_limit = producer_input.budget.tool_output_bytes

    async def preview_invocation(
        payload: JsonPayload, tool_context: ToolContext
    ) -> dict[str, JsonValue]:
        """Preview one payload's exact declared arguments, not target behavior.

        Fixed arguments cannot be replaced. Java requires a String payload. This
        in-memory check neither proves callable compatibility nor runs a control.
        """
        del tool_context
        error: dict[str, JsonValue] = {
            "error": "payload must be finite JSON within the invocation preview byte limit",
            "target_executed": False,
        }
        try:
            value = _JSON_VALUE.validate_python(payload, strict=True)
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
            return error
        if len(encoded) > min(32768, byte_limit):
            return error
        if isinstance(recipe, JavaRecipe) and not isinstance(value, str):
            return {"error": "the Java payload must be a String", "target_executed": False}
        result: dict[str, JsonValue] = {
            "recipe_kind": recipe.kind,
            "module_file": recipe.module_file,
            "function": recipe.function,
            "scope": "mechanical_only",
            "target_executed": False,
        }
        if isinstance(recipe, PythonRecipe):
            result["keyword_arguments"] = {**recipe.fixed_kwargs, recipe.payload_parameter: value}
        else:
            args = list(recipe.fixed_args)
            args.insert(recipe.payload_index, value)
            result["positional_arguments"] = args
            if isinstance(recipe, JavaRecipe):
                result["class_name"] = recipe.class_name
        try:
            rendered = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return error
        if len(rendered) > byte_limit:
            return error
        # Return detached JSON data, never mutable references to the bound recipe.
        return json.loads(rendered)

    return preview_invocation
