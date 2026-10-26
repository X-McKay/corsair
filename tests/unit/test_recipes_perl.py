"""Offline contract tests for the Perl html-injection recipe's markup baseline.

These validate the operator-owned recipe schema without Docker; they are not native
qualification. The real Perl sandbox gates live in tests/integration/test_docker_perl.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corsair.contracts import PerlRecipe


def _perl_recipe(**overrides: object) -> PerlRecipe:
    base: dict[str, object] = {
        "module_file": "lib/Renderer.pm",
        "package": "Renderer",
        "function": "render",
    }
    base.update(overrides)
    return PerlRecipe.model_validate(base)


def test_default_baseline_matches_the_default_expected_control() -> None:
    recipe = _perl_recipe()
    assert recipe.expected_control == "<div class='comment'>hello</div>"
    assert recipe.baseline_markup_chars == 4


@pytest.mark.parametrize(
    "control,count",
    [("plain text", 0), ("<p>hello</p>", 4), ("<a href='x'>y</a><br>", 6)],
)
def test_omitted_baseline_is_derived_from_a_string_control(control: str, count: int) -> None:
    assert _perl_recipe(expected_control=control).baseline_markup_chars == count


def test_explicit_consistent_baseline_is_accepted() -> None:
    assert _perl_recipe(baseline_markup_chars=4).baseline_markup_chars == 4


@pytest.mark.parametrize("baseline", [0, 3, 5])
def test_explicit_baseline_inconsistent_with_the_control_is_rejected(baseline: int) -> None:
    # The driver requires the exact benign return and this count, so any other value
    # would make every control INVALID.
    with pytest.raises(ValidationError, match="markup count of expected_control"):
        _perl_recipe(baseline_markup_chars=baseline)


def test_non_string_control_requires_an_explicit_baseline() -> None:
    with pytest.raises(ValidationError, match="baseline_markup_chars is required"):
        _perl_recipe(expected_control=7)
    assert _perl_recipe(expected_control=7, baseline_markup_chars=0).baseline_markup_chars == 0


def test_round_trip_keeps_the_derived_baseline() -> None:
    recipe = _perl_recipe(expected_control="<b>x</b>")
    assert PerlRecipe.model_validate_json(recipe.model_dump_json()) == recipe
