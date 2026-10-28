"""Concrete recipe ABI/admission tests; no target code executes on the host."""

import pytest
from pydantic import ValidationError

from corsair.contracts import Case, Finding, JavaRecipe, JavaScriptRecipe, PythonRecipe, Source
from corsair.settings import Settings


def test_concrete_recipes_roundtrip_in_one_discriminated_case():
    recipes = [
        PythonRecipe(module_file="target.py", function="read", payload_parameter="path"),
        JavaScriptRecipe(
            module_file="target.mjs", function="read", fixed_args=["/fixtures/allowed"]
        ),
        JavaRecipe(module_file="Target.java", class_name="Target", function="read"),
    ]
    for recipe in recipes:
        case = Case(
            case_id="case",
            finding=Finding(title="finding", description="scope", file=recipe.module_file),
            source=Source(path="."),
            recipe=recipe,
        )
        assert Case.model_validate_json(case.model_dump_json()) == case
        assert type(Case.model_validate_json(case.model_dump_json()).recipe) is type(recipe)


@pytest.mark.parametrize("module_file", ["target.js", "target.ts", "../target.mjs", "/target.mjs"])
def test_node_requires_admitted_esm_file(module_file):
    with pytest.raises(ValidationError):
        JavaScriptRecipe(module_file=module_file, function="read")


@pytest.mark.parametrize("args,index", [([], 1), (["root"], 2), (["root"] * 17, 0)])
def test_positional_payload_cannot_replace_fixed_arguments(args, index):
    with pytest.raises(ValidationError):
        JavaScriptRecipe(
            module_file="target.mjs", function="read", fixed_args=args, payload_index=index
        )


@pytest.mark.parametrize(
    "change",
    [
        {"class_name": "Other"},
        {"class_name": "bad/name"},
        {"module_file": "Target.class"},
        {"fixed_args": [1]},
        {"expected_control": {"value": "hello"}},
        {"allowed_exceptions": ["Throwable"]},
    ],
)
def test_java_rejects_unsupported_abi(change):
    value = {"module_file": "Target.java", "class_name": "Target", "function": "read", **change}
    with pytest.raises(ValidationError):
        JavaRecipe.model_validate(value)


def test_recipe_defaults_do_not_allow_target_exceptions():
    assert JavaScriptRecipe(module_file="target.mjs", function="read").allowed_exceptions == []
    assert (
        JavaRecipe(
            module_file="Target.java", class_name="Target", function="read"
        ).allowed_exceptions
        == []
    )


def test_settings_select_only_explicit_recipe_images():
    settings = Settings(image="python-id", node_image="node-id", java_image="java-id")
    assert (
        settings.image_for_recipe(
            PythonRecipe(module_file="target.py", function="read", payload_parameter="p")
        )
        == "python-id"
    )
    assert (
        settings.image_for_recipe(JavaScriptRecipe(module_file="target.mjs", function="read"))
        == "node-id"
    )
    assert (
        settings.image_for_recipe(
            JavaRecipe(module_file="Target.java", class_name="Target", function="read")
        )
        == "java-id"
    )
    assert Settings(node_image="different").identity != Settings().identity


def test_original_operator_packet_can_omit_python_kind():
    value = {
        "case_id": "case",
        "finding": {"file": "target.py", "title": "finding", "description": "scope"},
        "source": {"path": "."},
        "recipe": {"module_file": "target.py", "function": "read", "payload_parameter": "p"},
    }
    assert isinstance(Case.model_validate(value).recipe, PythonRecipe)
    value["recipe"] = {"module_file": "target.mjs", "function": "read"}
    with pytest.raises(ValidationError, match="union_tag_not_found"):
        Case.model_validate(value)


def test_node_exception_configuration_matches_the_concrete_native_abi():
    with pytest.raises(ValueError):
        JavaScriptRecipe.model_validate(
            {"module_file": "reader.mjs", "function": "read", "allowed_exceptions": ["CustomError"]}
        )
    with pytest.raises(ValueError):
        JavaScriptRecipe(
            module_file="reader.mjs", function="read", allowed_exceptions=["Error", "Error"]
        )
