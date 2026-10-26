"""Offline contract tests for the C integer-overflow recipe and the recipe union.

These validate the canonical contract and the smart-union routing only; they do not
run Docker or compile anything. Native behaviour is qualified in
tests/integration/test_docker_c.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.contracts import Case, CRecipe, Finding, InvestigationRequest, PythonRecipe, Source


def _case(recipe) -> Case:
    return Case(
        case_id="c-case",
        finding=Finding(title="overflow", description="length overflow", file="dup.c", line=7),
        source=Source(path="source"),
        recipe=recipe,
    )


def test_c_recipe_binds_to_the_finding_file() -> None:
    recipe = CRecipe(module_file="dup.c", function="dup_n", expected_control_length=5)
    case = _case(recipe)
    assert case.recipe.kind == "c.integer_overflow/1"
    assert isinstance(case.recipe, CRecipe)


def test_c_recipe_rejects_a_non_c_module() -> None:
    with pytest.raises(ValidationError):
        CRecipe(module_file="dup.py", function="dup_n")


def test_c_recipe_rejects_a_non_identifier_function() -> None:
    with pytest.raises(ValidationError):
        CRecipe(module_file="dup.c", function="dup-n")


def test_c_recipe_rejects_an_unknown_sanitizer_class() -> None:
    with pytest.raises(ValidationError):
        CRecipe(module_file="dup.c", function="dup_n", sanitizer_class="use-after-free")


def test_c_recipe_rejects_an_out_of_range_fill_byte() -> None:
    with pytest.raises(ValidationError):
        CRecipe(module_file="dup.c", function="dup_n", fill_byte=0)


def test_case_rejects_a_recipe_bound_to_a_different_file() -> None:
    with pytest.raises(ValidationError):
        Case(
            case_id="c-case",
            finding=Finding(title="t", description="d", file="other.c", line=1),
            source=Source(path="s"),
            recipe=CRecipe(module_file="dup.c", function="dup_n"),
        )


def test_smart_union_routes_c_and_python_without_a_declared_discriminator() -> None:
    c_json = _case(CRecipe(module_file="dup.c", function="dup_n")).model_dump_json()
    py = PythonRecipe(module_file="t.py", function="read_file", payload_parameter="path")
    py_case = Case(
        case_id="py-case",
        finding=Finding(title="t", description="d", file="t.py", line=1),
        source=Source(path="s"),
        recipe=py,
    )
    py_json = py_case.model_dump_json()
    assert isinstance(Case.model_validate_json(c_json).recipe, CRecipe)
    assert isinstance(Case.model_validate_json(py_json).recipe, PythonRecipe)


def test_frozen_python_fixture_without_kind_still_routes_to_python() -> None:
    # The pre-tag Python fixtures omit "kind"; the smart union must keep accepting them
    # so their pinned dataset digests never need to change.
    raw = json.loads(Path("evals/fixtures/case01/request.json").read_bytes())
    assert "kind" not in raw["case"]["recipe"]
    request = InvestigationRequest.model_validate(raw)
    assert isinstance(request.case.recipe, PythonRecipe)
