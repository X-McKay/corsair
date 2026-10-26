"""Offline contract tests for the Ruby recipe, the recipe union, and image selection.

These validate schema, discriminated-union routing, and recipe-kind image resolution
without Docker; they are not native qualification. The real Ruby sandbox gates live in
tests/integration/test_docker_ruby.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.contracts import Case, Finding, PythonRecipe, RubyRecipe, Source
from corsair.settings import Settings


def _ruby_recipe(**overrides) -> RubyRecipe:
    base = {
        "module_file": "lib/attachments.rb",
        "receiver": "Attachments",
        "function": "read",
        "payload_parameter": "name",
        "fixed_kwargs": {"root": "/fixtures/allowed"},
        "public_files": {"readme.txt": "stored attachment"},
        "expected_control": "stored attachment",
        "allowed_exceptions": ["ArgumentError"],
    }
    base.update(overrides)
    # model_validate runs full field/model validation, so the rejection cases still raise.
    return RubyRecipe.model_validate(base)


def test_ruby_recipe_defaults_its_kind_and_binds_a_namespaced_receiver() -> None:
    recipe = _ruby_recipe(receiver="Billing::Attachments")
    assert recipe.kind == "ruby.secret_disclosure/1"
    assert recipe.receiver == "Billing::Attachments"


@pytest.mark.parametrize(
    "overrides",
    [
        {"module_file": "lib/attachments.py"},  # not a Ruby file
        {"receiver": "attachments"},  # not a constant
        {"function": "_private"},  # not public
        {"payload_parameter": "Name"},  # not a keyword name
        {"allowed_exceptions": ["not a class"]},  # not a Ruby class name
        {"fixed_kwargs": {"root": "/fixtures/allowed"}, "payload_parameter": "root"},
    ],
)
def test_ruby_recipe_rejects_unsafe_shapes(overrides) -> None:
    with pytest.raises(ValidationError):
        _ruby_recipe(**overrides)


def test_case_recipe_union_routes_by_kind() -> None:
    finding = Finding(title="t", description="d", file="lib/attachments.rb", line=4)
    case = Case(case_id="ruby", finding=finding, source=Source(path="src"), recipe=_ruby_recipe())
    restored = Case.model_validate_json(case.model_dump_json())
    assert isinstance(restored.recipe, RubyRecipe)


def test_case_recipe_union_defaults_a_kindless_recipe_to_python() -> None:
    # A frozen request authored before the union omits ``kind`` and must still bind to
    # the original PythonRecipe member, keeping its digest and admission unchanged.
    case = Case.model_validate(
        {
            "case_id": "legacy",
            "finding": {"title": "t", "description": "d", "file": "target.py", "line": 4},
            "source": {"path": "src"},
            "recipe": {"module_file": "target.py", "function": "f", "payload_parameter": "p"},
        }
    )
    assert isinstance(case.recipe, PythonRecipe)


class _StubImage:
    id = "sha256:" + "e" * 64


class _StubImages:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def get(self, tag: str) -> _StubImage:
        self.requested.append(tag)
        return _StubImage()


class _StubClient:
    def __init__(self) -> None:
        self.images = _StubImages()


def test_image_is_resolved_per_recipe_kind() -> None:
    client = _StubClient()
    sandbox = DockerSandbox(Settings(), client=client)  # ty: ignore[invalid-argument-type]
    assert sandbox.image_id_for("ruby.secret_disclosure/1") == _StubImage.id
    assert sandbox.image_id_for("python.secret_disclosure/1") == _StubImage.id
    assert client.images.requested == ["corsair-ruby:0.1", "corsair-python:0.1"]


def test_unlisted_recipe_kind_falls_back_to_the_python_default_image() -> None:
    client = _StubClient()
    sandbox = DockerSandbox(Settings(), client=client)  # ty: ignore[invalid-argument-type]
    sandbox.image_id_for("unknown.kind/9")
    assert client.images.requested == ["corsair-python:0.1"]
