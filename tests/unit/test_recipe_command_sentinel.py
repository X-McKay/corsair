"""Contract and discriminated-union behavior for the command-sentinel recipe."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from corsair.contracts import (
    Case,
    PythonCommandSentinel,
    PythonRecipe,
    Recipe,
)

_RECIPE = TypeAdapter(Recipe)


def _case(recipe: dict) -> Case:
    return Case.model_validate(
        {
            "case_id": "c",
            "finding": {"title": "t", "description": "d", "file": "app.py"},
            "source": {"path": "source"},
            "recipe": recipe,
        }
    )


def test_tagless_recipe_remains_the_initial_disclosure_recipe() -> None:
    # A frozen request written before the union omits ``kind`` entirely.
    case = _case({"module_file": "app.py", "function": "f", "payload_parameter": "p"})
    assert isinstance(case.recipe, PythonRecipe)
    assert case.recipe.kind == "python.secret_disclosure/1"


def test_command_sentinel_recipe_selected_by_tag() -> None:
    case = _case(
        {
            "kind": "python.command_sentinel/1",
            "module_file": "app.py",
            "function": "run",
            "payload_parameter": "cmd",
        }
    )
    assert isinstance(case.recipe, PythonCommandSentinel)
    assert case.recipe.sentinel_path == "/work/corsair-sentinel"


def test_unknown_recipe_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _RECIPE.validate_python({"kind": "python.unknown/9", "module_file": "a.py"})


def test_recipe_binds_to_the_finding_file() -> None:
    with pytest.raises(ValidationError, match="bind to the original finding"):
        Case.model_validate(
            {
                "case_id": "c",
                "finding": {"title": "t", "description": "d", "file": "other.py"},
                "source": {"path": "s"},
                "recipe": {
                    "kind": "python.command_sentinel/1",
                    "module_file": "app.py",
                    "function": "f",
                    "payload_parameter": "p",
                },
            }
        )


@pytest.mark.parametrize(
    "path",
    [
        "/fixtures/private/x",  # read-only mount
        "/source/x",  # read-only mount
        "/work/../etc/passwd",  # traversal
        "relative/path",  # not absolute
        "/work/",  # empty final component
    ],
)
def test_sentinel_path_must_be_writable_and_non_traversing(path: str) -> None:
    with pytest.raises(ValidationError):
        PythonCommandSentinel(
            module_file="app.py", function="f", payload_parameter="p", sentinel_path=path
        )


def test_payload_parameter_may_not_override_fixed_argument() -> None:
    with pytest.raises(ValidationError, match="may not override"):
        PythonCommandSentinel(
            module_file="app.py",
            function="f",
            payload_parameter="p",
            fixed_kwargs={"p": 1},
        )


def test_private_identifiers_and_non_python_modules_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PythonCommandSentinel(module_file="app.py", function="_private", payload_parameter="p")
    with pytest.raises(ValidationError):
        PythonCommandSentinel(module_file="app.txt", function="f", payload_parameter="p")


def test_recipe_round_trips_through_json_preserving_the_tag() -> None:
    recipe = PythonCommandSentinel(module_file="app.py", function="run", payload_parameter="cmd")
    restored = _RECIPE.validate_json(recipe.model_dump_json())
    assert isinstance(restored, PythonCommandSentinel)
    assert restored == recipe
