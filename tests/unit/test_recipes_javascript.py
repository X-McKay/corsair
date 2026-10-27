"""Offline contract tests for the JavaScript prototype-pollution recipe's export markers.

These validate the canonical contract only; they run no Docker and no Node. How the
trusted driver resolves each ``function`` value is qualified in
tests/integration/test_docker_javascript.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corsair.contracts import JavaScriptRecipe


@pytest.mark.parametrize("function", ["mergePreferences", "default", "module.exports", "$set"])
def test_javascript_recipe_accepts_a_named_property_or_an_export_marker(function: str) -> None:
    recipe = JavaScriptRecipe(module_file="index.js", function=function)
    assert recipe.function == function
    assert JavaScriptRecipe.model_validate(recipe.model_dump(mode="json")) == recipe


@pytest.mark.parametrize(
    "function", ["module.exports.merge", "a.b", "module.Exports", "exports.merge", "1merge", ""]
)
def test_javascript_recipe_rejects_any_other_dotted_or_invalid_function(function: str) -> None:
    with pytest.raises(ValidationError):
        JavaScriptRecipe(module_file="index.js", function=function)
